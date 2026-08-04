"""
pricing.py — turn token counts into dollars.

A migration's cost has to be visible *before* someone approves a 300-class run,
and *while* it happens. This module holds the price table and the arithmetic;
the engine records per-model token usage and asks here for the number.

Prices are USD per 1,000,000 tokens (Anthropic first-party list prices, cached
2026-06-24). They are also overridable from config.yaml (`pricing.models`) so a
rate change — or a negotiated/partner rate — never means editing code:

    pricing:
      models:
        claude-opus-5: {input: 5.00, output: 25.00}

Unknown models (e.g. an arbitrary OpenRouter slug) are reported as *unpriced*
rather than guessed — a wrong cost estimate is worse than an honest "unknown".
"""

from __future__ import annotations

# model id -> (USD per 1M input tokens, USD per 1M output tokens)
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5":    (10.00, 50.00),
    "claude-mythos-5":   (10.00, 50.00),
    "claude-opus-5":     (5.00, 25.00),
    "claude-opus-4-8":   (5.00, 25.00),
    "claude-opus-4-7":   (5.00, 25.00),
    "claude-opus-4-6":   (5.00, 25.00),
    "claude-opus-4-5":   (5.00, 25.00),
    "claude-sonnet-5":   (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5":  (1.00, 5.00),
}

# Cached input is billed at ~0.1x the base input rate; writing to the cache costs
# ~1.25x (5-minute TTL). Both are applied on top of the model's input price.
CACHE_READ_MULTIPLIER = 0.10
CACHE_WRITE_MULTIPLIER = 1.25

_FREE = ("mock",)                      # deterministic stub — never billed


def normalise(model: str) -> str:
    """Map a concrete model string onto a price-table key: strips a provider
    prefix (`anthropic/…`, `anthropic.…`) and a dated snapshot suffix, so
    `anthropic/claude-haiku-4-5-20251001` prices as `claude-haiku-4-5`."""
    m = (model or "").strip()
    for sep in ("/", "."):
        if sep in m and m.split(sep, 1)[0] in ("anthropic", "us", "eu"):
            m = m.split(sep, 1)[1]
    if m in PRICES:
        return m
    # dated snapshot: claude-haiku-4-5-20251001 -> claude-haiku-4-5
    parts = m.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and parts[0] in PRICES:
        return parts[0]
    return m


def rates(model: str, config: dict | None = None) -> tuple[float, float] | None:
    """(input, output) USD per 1M tokens, or None when the model isn't priced."""
    key = normalise(model)
    override = ((config or {}).get("pricing") or {}).get("models") or {}
    if key in override or model in override:
        entry = override.get(key) or override.get(model) or {}
        try:
            return float(entry.get("input", 0)), float(entry.get("output", 0))
        except (TypeError, ValueError):
            return None
    return PRICES.get(key)


def cost_of(model: str, *, prompt_tokens: int = 0, completion_tokens: int = 0,
            cache_read_tokens: int = 0, cache_write_tokens: int = 0,
            config: dict | None = None) -> float | None:
    """USD for one model's usage, or None if the model has no known price."""
    r = rates(model, config)
    if r is None:
        return None
    in_rate, out_rate = r
    return (
        prompt_tokens * in_rate
        + completion_tokens * out_rate
        + cache_read_tokens * in_rate * CACHE_READ_MULTIPLIER
        + cache_write_tokens * in_rate * CACHE_WRITE_MULTIPLIER
    ) / 1_000_000


def summarise(by_model: dict, config: dict | None = None) -> dict:
    """Roll per-model usage into a cost report.

    Returns {total_usd, priced, by_model:[{model, requests, tokens, usd}], unpriced:[...]}.
    `priced` is False when at least one model used has no known rate — the caller
    should present the total as a floor ("at least $X"), not the whole story."""
    rows, total, unpriced = [], 0.0, []
    for model, u in sorted((by_model or {}).items()):
        usd = cost_of(model,
                      prompt_tokens=u.get("prompt_tokens", 0),
                      completion_tokens=u.get("completion_tokens", 0),
                      cache_read_tokens=u.get("cache_read_tokens", 0),
                      cache_write_tokens=u.get("cache_write_tokens", 0),
                      config=config)
        free = normalise(model) in _FREE or model in _FREE
        if usd is None and not free:
            unpriced.append(model)
        total += usd or 0.0
        rows.append({
            "model": model, "requests": u.get("requests", 0),
            "input_tokens": u.get("prompt_tokens", 0),
            "output_tokens": u.get("completion_tokens", 0),
            "usd": round(usd, 6) if usd is not None else None,
        })
    return {"total_usd": round(total, 6), "priced": not unpriced,
            "by_model": rows, "unpriced": unpriced}


def fmt(usd: float | None) -> str:
    """Human-readable dollars — small runs shouldn't render as '$0.00'."""
    if usd is None:
        return "n/a"
    if usd == 0:
        return "$0.00"
    return f"${usd:.4f}" if usd < 0.01 else f"${usd:,.2f}"
