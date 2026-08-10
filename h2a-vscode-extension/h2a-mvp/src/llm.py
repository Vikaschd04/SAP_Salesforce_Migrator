"""
llm.py — LLM gateway for the Hybris→Apex pipeline.

Design goals (production rework):
  - Anthropic Claude via the official SDK (frontier quality for code translation).
  - Prompt caching: the large, stable prefix (mapping rules, constraints, type
    table, SObject schema, few-shot examples) is sent as a cached system prompt,
    so every class in a repo reuses it at ~0.1x cost instead of re-billing it.
  - Structured outputs: callers can request a JSON schema and get guaranteed-
    parseable results instead of scraping `===MARKER===` blocks.
  - Provider abstraction:
        anthropic  → real Claude calls (needs ANTHROPIC_API_KEY)
        mock       → deterministic local stub, clearly labelled, for CI / dry
                     runs with no key. It is NOT a hidden fixture set: every
                     response is generated from the request and the report/logs
                     record `provider=mock` so mock output is never mistaken for
                     a real migration.
  - Disk cache keyed on (stage, provider, model, full prompt) so re-runs and
    `--offline` replay are free and deterministic.
  - Honest token + cache accounting.

The previous OpenRouter multi-model fallback and the giant hardcoded `_PREBAKED`
dictionary have been removed. Retries/backoff are handled by the Anthropic SDK.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import random
import re
import threading
from pathlib import Path
from typing import Any

# Guards shared mutable state so the agentic orchestrator can run stages concurrently:
# token accounting (read-modify-write) and lazy client construction.
_STATE_LOCK = threading.Lock()

import yaml

logger_prefix = "h2a.llm"

# ── Accounting ────────────────────────────────────────────────────────────────

_accounting = {
    "requests": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "providers": {},        # provider -> request count
    "models": {},           # model -> per-model usage (drives cost, see src/pricing.py)
    "retries": 0,           # transient failures retried (see _with_retry)
}


def get_accounting() -> dict:
    """Return a copy of the current token/request accounting."""
    return json.loads(json.dumps(_accounting))


def reset_accounting():
    """Reset accounting counters to zero."""
    global _accounting
    _accounting = {
        "requests": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "providers": {},
        "models": {},
        "retries": 0,
    }


# ── Transient-failure retry ───────────────────────────────────────────────────

# Provider-agnostic: match by exception class name and HTTP status rather than
# importing SDK error types (the SDKs are imported lazily, and both providers
# expose the same shapes).
_TRANSIENT_EXC = {
    "RateLimitError", "APIConnectionError", "APITimeoutError", "APIConnectionTimeoutError",
    "InternalServerError", "OverloadedError", "ServiceUnavailableError", "Timeout",
}
_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}


def _is_transient(exc: Exception) -> bool:
    """True when retrying could plausibly succeed (rate limit, overload, network)."""
    if type(exc).__name__ in _TRANSIENT_EXC:
        return True
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status in _TRANSIENT_STATUS


def _retry_cfg(config: dict) -> dict:
    r = (config or {}).get("resilience") or {}
    return {
        "max_attempts": max(1, int(r.get("max_attempts", 4) or 1)),
        "base_delay": float(r.get("base_delay", 2.0) or 2.0),
        "max_delay": float(r.get("max_delay", 60.0) or 60.0),
    }


def _with_retry(fn, *, stage: str, config: dict):
    """Run fn(), retrying transient failures with jittered exponential backoff.

    This sits *on top of* the provider SDK's own retries: the SDK handles the
    common case, and this catches the rarer one where it exhausts its budget —
    which stops being rare across the ~900 calls a large repo needs."""
    cfg = _retry_cfg(config)
    last = None
    for attempt in range(cfg["max_attempts"]):
        try:
            return fn()
        except Exception as exc:                       # noqa: BLE001 — re-raised below
            last = exc
            if attempt == cfg["max_attempts"] - 1 or not _is_transient(exc):
                raise
            # Full jitter: spreads concurrent workers instead of retrying in lockstep.
            delay = min(cfg["max_delay"], cfg["base_delay"] * (2 ** attempt))
            delay *= 0.5 + random.random()
            with _STATE_LOCK:
                _accounting["retries"] = _accounting.get("retries", 0) + 1
            print(f"    ⟳ {stage}: {type(exc).__name__} — retry "
                  f"{attempt + 1}/{cfg['max_attempts'] - 1} in {delay:.1f}s")
            time.sleep(delay)
    raise last                                          # pragma: no cover


def _record(provider: str, prompt_tokens: int, completion_tokens: int,
            cache_read: int = 0, cache_write: int = 0, model: str = ""):
    # Read-modify-write on shared counters — must be atomic when stages run concurrently,
    # or the reported request/token totals silently undercount.
    with _STATE_LOCK:
        _accounting["requests"] += 1
        _accounting["prompt_tokens"] += prompt_tokens
        _accounting["completion_tokens"] += completion_tokens
        _accounting["cache_read_tokens"] += cache_read
        _accounting["cache_write_tokens"] += cache_write
        _accounting["providers"][provider] = _accounting["providers"].get(provider, 0) + 1
        # Per-model breakdown — with routing on, a run mixes tiers, and cost can only
        # be computed if we know which model spent which tokens.
        if model:
            m = _accounting["models"].setdefault(
                model, {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
                        "cache_read_tokens": 0, "cache_write_tokens": 0})
            m["requests"] += 1
            m["prompt_tokens"] += prompt_tokens
            m["completion_tokens"] += completion_tokens
            m["cache_read_tokens"] += cache_read
            m["cache_write_tokens"] += cache_write


# ── Config ────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_config() -> dict:
    """Load config.yaml from the project root."""
    with open(_PROJECT_ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
_KEY_PLACEHOLDERS = {
    "your-key-here", "sk-ant-your-key-here", "sk-or-v1-your-key-here",
}


def _get_provider(config: dict) -> str:
    """Per-run override wins, then the environment, then config.yaml.

    The override exists so concurrent web runs can each choose a provider without
    writing to os.environ, which they share. CLI/extension set no override and are
    unaffected."""
    from src.runctx import provider_override
    return (provider_override() or os.environ.get("H2A_PROVIDER")
            or config.get("provider") or "anthropic").lower()


def _get_model(config: dict, provider: str = "anthropic") -> str:
    """Resolve the model for the active provider (H2A_CUSTOM_MODEL always wins)."""
    from src.runctx import model_override
    custom = model_override() or os.environ.get("H2A_CUSTOM_MODEL")
    if custom:
        return custom
    if provider == "openrouter":
        return (config.get("openrouter") or {}).get("model") or _DEFAULT_OPENROUTER_MODEL
    return config.get("model") or "claude-opus-4-8"


def _get_api_key(var_name: str) -> str | None:
    """Load an API key. A per-run override (a tenant's own credential) wins over the
    server's environment, so concurrent runs bill their own accounts."""
    from src.runctx import api_key_override
    key = api_key_override() or os.environ.get(var_name)
    if key:
        return key
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{var_name}=") and not line.startswith("#"):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val and val not in _KEY_PLACEHOLDERS:
                    return val
    return None


# ── Disk cache ────────────────────────────────────────────────────────────────

# ── call ledger ───────────────────────────────────────────────────────────────
# Every call is already keyed by a hash of (stage, model, prompt). Recording those keys
# turns the cache from an optimisation into an audit trail: "prove why the AI did that in
# March" is a procurement requirement in regulated enterprises, and the answer is a
# deterministic replay from the same key rather than a re-run that might differ.
#
# The prompt itself is NOT stored — it contains the customer's source code, and copying
# that into a second place on disk is a liability, not a feature. The hash identifies the
# call; the cache already holds the response.
_calls: list[dict] = []


def reset_call_log() -> None:
    with _STATE_LOCK:
        _calls.clear()


def get_call_log() -> list[dict]:
    with _STATE_LOCK:
        return list(_calls)


def _log_call(stage: str, provider: str, model: str, key: str, *, cached: bool,
              prompt_chars: int, effort: str | None = None, attempts: int = 1) -> None:
    with _STATE_LOCK:
        _calls.append({
            "seq": len(_calls) + 1, "stage": stage, "provider": provider, "model": model,
            "cache_key": key, "cached": cached, "prompt_chars": prompt_chars,
            "effort": effort or "", "attempts": attempts, "at": round(time.time(), 3),
        })


def _cache_key(stage: str, model: str, prompt: str) -> str:
    """SHA-256 cache key from stage + model + prompt (kept for API stability)."""
    raw = f"{stage}|{model}|{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_dir(config: dict) -> Path:
    d = Path(config.get("cache_dir", "cache/"))
    if not d.is_absolute():
        d = _PROJECT_ROOT / d
    return d


def _read_cache(cache_dir: Path, key: str) -> dict | None:
    path = cache_dir / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _write_cache(cache_dir: Path, key: str, data: dict):
    # Atomic: write to a unique temp file then rename, so a concurrent reader never
    # sees a half-written cache entry (and two writers can't interleave content).
    cache_dir.mkdir(parents=True, exist_ok=True)
    final = cache_dir / f"{key}.json"
    tmp = cache_dir / f".{key}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, final)          # atomic on POSIX and Windows
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


# ── Anthropic backend ─────────────────────────────────────────────────────────

_client = None


def _anthropic_client(api_key: str):
    """Lazily build (and reuse) the SDK client. Double-checked locking so concurrent
    stages share one client instead of racing to construct several."""
    global _client
    if _client is not None:
        return _client
    with _STATE_LOCK:
        if _client is None:
            import anthropic  # imported lazily so `mock` runs need no SDK/network
            # Optional Anthropic-compatible gateway (self-hosted proxy, LiteLLM,
            # corporate gateway, etc.) via ANTHROPIC_BASE_URL. NOTE: a third-party
            # gateway sees all prompts/source you send and may override the model or
            # inject its own context — only point this at an endpoint you trust.
            base_url = _get_api_key("ANTHROPIC_BASE_URL")
            # The SDK does correct exponential backoff on 408/409/429/5xx and
            # connection errors — its default budget (2) is thin for a repo-scale
            # run, so raise it and bound each request. _with_retry sits on top.
            r = (_load_config().get("resilience") or {})
            opts = {"max_retries": int(r.get("sdk_max_retries", 3) or 3),
                    "timeout": float(r.get("request_timeout", 600) or 600)}
            if base_url:
                _client = anthropic.Anthropic(api_key=api_key, base_url=base_url, **opts)
            else:
                _client = anthropic.Anthropic(api_key=api_key, **opts)
    return _client


def _call_anthropic(
    *,
    model: str,
    system_prompt: str,
    prompt: str,
    max_tokens: int,
    json_schema: dict | None,
    effort: str | None,
    cache_system: bool,
) -> dict:
    api_key = _get_api_key("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY not found. Set it in the environment or .env, "
            "get a key at https://console.anthropic.com/, or run with provider=mock "
            "(H2A_PROVIDER=mock) for a keyless dry run."
        )
    client = _anthropic_client(api_key)

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }

    # Stable prefix as a cached system prompt (prefix caching → ~0.1x on reuse).
    if system_prompt:
        block: dict[str, Any] = {"type": "text", "text": system_prompt}
        if cache_system:
            block["cache_control"] = {"type": "ephemeral"}
        kwargs["system"] = [block]

    # Adaptive thinking + effort for the hard reasoning stages (Claude 4.6+).
    if effort:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": effort}

    if json_schema is not None:
        oc = kwargs.setdefault("output_config", {})
        oc["format"] = {"type": "json_schema", "schema": json_schema}

    resp = client.messages.create(**kwargs)

    content = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    usage = resp.usage
    return {
        "content": content,
        "prompt_tokens": getattr(usage, "input_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }


# ── OpenRouter backend (OpenAI-compatible; free models for dev/testing) ───────

_or_client = None


def _openrouter_client(api_key: str, base_url: str):
    global _or_client
    if _or_client is not None:
        return _or_client
    with _STATE_LOCK:                        # double-checked, as above
        if _or_client is None:
            from openai import OpenAI  # lazy — only needed for provider=openrouter
            r = (_load_config().get("resilience") or {})
            _or_client = OpenAI(base_url=base_url, api_key=api_key,
                                max_retries=int(r.get("sdk_max_retries", 3) or 3),
                                timeout=float(r.get("request_timeout", 600) or 600))
    return _or_client


def _schema_directive(json_schema: dict) -> str:
    """
    Translate a JSON schema into a plain-text instruction, so providers without
    native structured-output support (OpenRouter free models) still return the
    same JSON shape. The core prompt templates are unchanged — this is a
    provider-adapter concern appended only for such providers.
    """
    props = (json_schema or {}).get("properties", {})
    if not props:
        return ""
    keys = ", ".join(f"{k} ({v.get('type', 'string')})" for k, v in props.items())
    return (
        "\n\nReturn ONLY a single valid JSON object (no markdown fences, no prose) "
        f"with exactly these keys: {keys}. String values must be properly JSON-escaped."
    )


def _call_openrouter(
    *,
    model: str,
    system_prompt: str,
    prompt: str,
    max_tokens: int,
    json_schema: dict | None,
    base_url: str,
    api_key: str,
) -> dict:
    client = _openrouter_client(api_key, base_url)

    user_content = prompt + (_schema_directive(json_schema) if json_schema is not None else "")
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    content = resp.choices[0].message.content or ""
    usage = getattr(resp, "usage", None)
    return {
        "content": content,
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }


# ── Mock backend (deterministic; explicitly labelled) ─────────────────────────

def _mock_target_name(stage: str, prompt: str) -> str:
    # generate_<TargetName>
    m = re.match(r"generate_(\w+)", stage)
    if m:
        return m.group(1)
    m = re.search(r"target_class_name[\"']?\s*[:=]\s*[\"']?(\w+)", prompt)
    if m:
        return m.group(1)
    return "GeneratedClass"


def _call_mock(*, stage: str, prompt: str, json_schema: dict | None) -> dict:
    """
    Deterministic stub used for keyless dry-runs and CI. Produces *structurally
    valid* Apex (with sharing, @isTest, an assertion, no SOQL/DML in loops) so the
    deterministic pipeline can be exercised — but it does NOT attempt real business
    logic. Callers surface `provider=mock` so this is never confused with a real run.
    """
    if stage == "ping":
        return {"content": "pong (mock)", "prompt_tokens": 0, "completion_tokens": 0,
                "cache_read_tokens": 0, "cache_write_tokens": 0}

    if stage.startswith("comprehend"):
        payload = {
            "purpose": "[mock] Deterministic stub comprehension.",
            "inputs": [],
            "outputs": [],
            "side_effects": [],
            "queries": [],
            "business_rules": [],
        }
        content = json.dumps(payload)
        return {"content": content, "prompt_tokens": 0, "completion_tokens": 0,
                "cache_read_tokens": 0, "cache_write_tokens": 0}

    # generate / repair stages
    name = _mock_target_name(stage, prompt)
    main_class = (
        f"public with sharing class {name} {{\n"
        f"    // [mock] deterministic stub — replace by running with a real provider.\n"
        f"    public static List<Object> execute(List<Object> records) {{\n"
        f"        if (records == null) {{ return new List<Object>(); }}\n"
        f"        return records;\n"
        f"    }}\n"
        f"}}"
    )
    test_class = (
        f"@isTest\n"
        f"private class {name}Test {{\n"
        f"    @isTest\n"
        f"    static void testExecute() {{\n"
        f"        List<Object> result = {name}.execute(new List<Object>());\n"
        f"        System.assertEquals(0, result.size(), 'mock stub returns input list');\n"
        f"    }}\n"
        f"}}"
    )
    if json_schema is not None:
        content = json.dumps({
            "main_class": main_class,
            "test_class": test_class,
            "sobject_refs": [],
            "mapping_notes": "[mock] Deterministic stub output (provider=mock).",
        })
    else:
        content = (
            "===MAIN_CLASS===\n" + main_class + "\n===END_MAIN_CLASS===\n\n"
            "===TEST_CLASS===\n" + test_class + "\n===END_TEST_CLASS===\n\n"
            "===MAPPING_NOTES===\n[mock] Deterministic stub output.\n===END_MAPPING_NOTES==="
        )
    return {"content": content, "prompt_tokens": 0, "completion_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0}


# ── Public API ────────────────────────────────────────────────────────────────

def call_llm(
    stage: str,
    prompt: str,
    max_tokens: int,
    *,
    offline: bool = False,
    system_prompt: str = "",
    cache_system: bool = True,
    json_schema: dict | None = None,
    effort: str | None = None,
    model: str | None = None,
) -> dict:
    """
    Call the configured LLM provider with disk caching and accounting.

    Returns a dict with:
        content            : str  (raw text; JSON string when json_schema is set)
        parsed             : dict | None  (json.loads(content) when json_schema set)
        prompt_tokens, completion_tokens, cache_read_tokens, cache_write_tokens
        cached             : bool (served from the disk cache)
        provider, model    : str
    """
    config = _load_config()
    provider = _get_provider(config)
    # Model routing: an explicit override (from the agentic router) wins, but only
    # for the anthropic provider — routed model ids are Claude ids and would be
    # meaningless slugs for openrouter/mock.
    model = model if (model and provider == "anthropic") else _get_model(config, provider)
    cache_dir = _cache_dir(config)

    full_prompt = f"{system_prompt}\n---\n{prompt}"
    if json_schema is not None:
        full_prompt += "\n---schema---\n" + json.dumps(json_schema, sort_keys=True)
    key = _cache_key(stage, f"{provider}:{model}", full_prompt)

    # Disk cache first (free replay for both providers).
    cached = _read_cache(cache_dir, key)
    if cached:
        out = dict(cached)
        out["cached"] = True
        out["provider"] = cached.get("provider", provider)
        out["model"] = cached.get("model", model)
        out["parsed"] = _try_parse(out.get("content", ""), json_schema)
        _log_call(stage, out["provider"], out["model"], key, cached=True,
                  prompt_chars=len(full_prompt), effort=effort)
        return out

    if offline:
        raise RuntimeError(
            f"Offline mode: no cached response for stage={stage}. "
            f"Run once online (or with H2A_PROVIDER=mock) to populate the cache."
        )

    if provider == "mock":
        result = _call_mock(stage=stage, prompt=prompt, json_schema=json_schema)
    elif provider == "anthropic":
        result = _with_retry(lambda: _call_anthropic(
            model=model, system_prompt=system_prompt, prompt=prompt,
            max_tokens=max_tokens, json_schema=json_schema, effort=effort,
            cache_system=cache_system,
        ), stage=stage, config=config)
    elif provider == "openrouter":
        orcfg = config.get("openrouter") or {}
        api_key = _get_api_key("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENROUTER_API_KEY not found. Set it in the environment or .env, "
                "get a key at https://openrouter.ai/keys, or use provider=anthropic / mock."
            )
        result = _with_retry(lambda: _call_openrouter(
            model=model, system_prompt=system_prompt, prompt=prompt,
            max_tokens=max_tokens, json_schema=json_schema,
            base_url=orcfg.get("base_url", "https://openrouter.ai/api/v1"),
            api_key=api_key,
        ), stage=stage, config=config)
    else:
        raise ValueError(f"Unknown provider '{provider}'. Use 'anthropic', 'openrouter', or 'mock'.")

    _record(
        provider,
        result.get("prompt_tokens", 0),
        result.get("completion_tokens", 0),
        result.get("cache_read_tokens", 0),
        result.get("cache_write_tokens", 0),
        # Attribute usage to the model that actually ran. The mock provider borrows the
        # configured model id, so record it as "mock" — otherwise a free deterministic
        # run would report real Anthropic dollar costs.
        model=("mock" if provider == "mock" else result.get("model", model)),
    )

    to_cache = {
        "content": result["content"],
        "prompt_tokens": result.get("prompt_tokens", 0),
        "completion_tokens": result.get("completion_tokens", 0),
        "cache_read_tokens": result.get("cache_read_tokens", 0),
        "cache_write_tokens": result.get("cache_write_tokens", 0),
        "provider": provider,
        "model": model,
    }
    _write_cache(cache_dir, key, to_cache)
    _log_call(stage, result.get("provider", provider), result.get("model", model), key,
              cached=False, prompt_chars=len(full_prompt), effort=effort)

    out = dict(to_cache)
    out["cached"] = False
    out["parsed"] = _try_parse(out["content"], json_schema)
    return out


def call_structured(
    stage: str,
    prompt: str,
    schema: dict,
    max_tokens: int,
    *,
    offline: bool = False,
    system_prompt: str = "",
    effort: str | None = None,
    model: str | None = None,
) -> dict:
    """Convenience wrapper that always requests a JSON schema and returns `parsed`."""
    result = call_llm(
        stage, prompt, max_tokens, offline=offline,
        system_prompt=system_prompt, json_schema=schema, effort=effort, model=model,
    )
    if result.get("parsed") is None:
        # Structured outputs guarantee valid JSON, but be defensive for mock/legacy.
        result["parsed"] = _extract_json(result.get("content", "")) or {}
    return result


def _try_parse(content: str, json_schema: dict | None) -> dict | None:
    if json_schema is None:
        return None
    return _extract_json(content)


def _extract_json(content: str) -> dict | None:
    content = (content or "").strip()
    if not content:
        return None
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0]
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}") + 1
        if 0 <= start < end:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                return None
    return None


def ping() -> dict:
    """Test connectivity to the configured provider."""
    config = _load_config()
    provider = _get_provider(config)
    model = _get_model(config, provider)
    result = call_llm(
        "ping",
        "Reply with the single word: pong",
        max_tokens=16,
    )
    return {
        "reply": (result.get("content") or "").strip(),
        "provider": provider,
        "model": model,
        "requests": _accounting["requests"],
        "prompt_tokens": _accounting["prompt_tokens"],
        "completion_tokens": _accounting["completion_tokens"],
        "cached": result.get("cached", False),
    }
