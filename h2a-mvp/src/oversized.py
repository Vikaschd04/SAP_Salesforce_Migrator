"""
oversized.py — source too large for the model to read in one call. [1.28]

The delivery plan called this "silent truncation — output looks complete". It is not, and
the real behaviour is worth stating because it shaped the fix: nothing caps the source, so
an oversized class is sent whole, the provider rejects the request, the resilience layer
treats that like any other failure and retries it four times, and the unit finally lands as
`status: error` reading "conversion failed".

Not silent. Wrong in a different way — four requests spent on something that could never
succeed, and a customer told their class failed to convert when what happened is that it
was too big to send.

**The two stages need opposite answers, and that is the whole design.**

Comprehension reads a class and returns an understanding: a purpose, a list of business
rules, dependencies, risks. Those merge. Reading half a class and then the other half
yields the union of what each half contained, and a rule found in either half is a rule.
So comprehension chunks.

Generation writes the class. There is no union of two half-migrations, and stitching two
independently generated halves produces a file whose two ends were written by callers that
could not see each other. So generation refuses, with the real reason, and the unit goes
to manual migration where a human can split it deliberately.

Chunking uses the *source adapter's* own symbol reader (item 2.11), so a PHP class chunks
at PHP method boundaries and a Java class at Java ones. Splitting on line count would cut
through the middle of a method, which is the one place a chunk boundary must not fall.
"""

from __future__ import annotations

#: Context windows, in tokens. Conservative on purpose: a model absent from this table
#: gets the smallest window rather than the largest, because guessing high sends a request
#: that fails and guessing low sends one that works.
CONTEXT = {
    "claude-opus-4-8": 200_000,
    "claude-opus-4-7": 200_000,
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
}
DEFAULT_CONTEXT = 100_000

#: Room left for the response and for the parts of a prompt this module cannot see —
#: the system prompt, the retrieved knowledge chunks, the schema directive.
_PROMPT_OVERHEAD = 8_000


def model_for_stage(stage: str) -> str:
    """The model a stage will actually be sent to, from routing and config.

    Asked rather than passed, because the budget has to be measured against the model that
    receives the prompt — and `generate_apex` never took a model parameter. Referring to
    one that was not in scope raised NameError, the caller treated it as a failed
    conversion, and the run emitted nothing at all.
    """
    from src import runctx
    from src.llm import _load_config

    override = runctx.model_override()
    if override:
        return override
    cfg = _load_config() or {}
    routing = ((cfg.get("agentic") or {}).get("routing") or {})
    if routing.get("enabled"):
        tier = (routing.get("tiers") or {}).get(stage, "frontier")
        got = (routing.get("models") or {}).get(tier)
        if got:
            return got
    return cfg.get("model", "")


def context_for(model: str) -> int:
    return CONTEXT.get((model or "").strip(), DEFAULT_CONTEXT)


def _chars_per_token() -> float:
    """From the running pipeline's forecast profile — PHP is denser than Java. [4.3]"""
    try:
        from src.forecast import profile_for
        return float(profile_for().chars_per_token) or 4.0
    except Exception:
        return 4.0


def estimate_tokens(text: str) -> int:
    return int(len(text or "") / _chars_per_token())


def input_budget(model: str, max_output: int) -> int:
    """Tokens available for the source itself."""
    return max(1_000, context_for(model) - int(max_output or 0) - _PROMPT_OVERHEAD)


def fits(text: str, model: str, max_output: int) -> bool:
    return estimate_tokens(text) <= input_budget(model, max_output)


def too_large_reason(text: str, model: str, max_output: int) -> str:
    """Why this will not be sent, in terms the reader can act on."""
    return (f"{estimate_tokens(text):,} estimated tokens of source against a "
            f"{input_budget(model, max_output):,}-token budget for "
            f"`{model or 'the configured model'}` "
            f"({context_for(model):,}-token context, less the response and prompt "
            "overhead). This was never going to be sent successfully.")


def split_source(source: str, model: str, max_output: int) -> list:
    """Split a class into chunks that fit, cutting only at method boundaries.

    Everything above the first method — package, imports, class declaration, fields — is
    the *preamble*, and everything after the last is the *epilogue*. Both go on every
    chunk, so each one is a syntactically whole class holding a subset of the methods.
    Without the preamble a chunk is a bag of method bodies with no statement of what class
    they belong to; without the epilogue the class is never closed, and a model reading it
    remarks on the truncation instead of the logic.

    A single method that does not fit on its own is returned whole and oversized rather
    than cut: chunking inside a method body is how you get an understanding of half an
    algorithm reported as an understanding.
    """
    lines = (source or "").splitlines(keepends=True)
    if not lines:
        return []

    try:
        from src import pipeline, runctx
        pipeline.ensure_registered()
        src_adapter = pipeline.active_or_shipped().source
        methods = sorted(src_adapter.symbols(source) or [],
                         key=lambda m: m.get("line_start", 0))
    except Exception:
        methods = []

    if not methods:
        # Nothing readable to cut at. One chunk, oversized, and the caller decides —
        # inventing a boundary here would put one in the middle of something.
        return [source]

    preamble = "".join(lines[: max(0, methods[0].get("line_start", 1) - 1)])
    epilogue = "".join(lines[max(m.get("line_end", 0) for m in methods):])
    budget_chars = int(input_budget(model, max_output) * _chars_per_token())
    room = max(1, budget_chars - len(preamble) - len(epilogue))

    chunks, current = [], []
    size = 0
    for m in methods:
        body = "".join(lines[m.get("line_start", 1) - 1: m.get("line_end", 1)])
        if current and size + len(body) > room:
            chunks.append(preamble + "".join(current) + epilogue)
            current, size = [], 0
        current.append(body)
        size += len(body)
    if current:
        chunks.append(preamble + "".join(current) + epilogue)
    return chunks


#: Fields of a comprehension that are *lists of findings*: reading two halves of a class
#: gives the union, because a rule found in either half is a rule the class contains.
_MERGEABLE = ("business_rules", "dependencies", "migration_risks", "queries",
              "side_effects", "inputs", "outputs")


def merge_understandings(parts: list) -> dict:
    """Fold per-chunk understandings into one.

    Only the list fields merge. `purpose` is a statement about the whole class and each
    chunk saw a fraction of it, so the longest is kept and the rest are recorded as
    partial views rather than averaged into something no chunk actually said.
    """
    parts = [p for p in (parts or []) if isinstance(p, dict)]
    if not parts:
        return {}
    if len(parts) == 1:
        return dict(parts[0])

    out = dict(parts[0])
    for field in _MERGEABLE:
        seen, merged = set(), []
        for p in parts:
            for item in (p.get(field) or []):
                key = item if isinstance(item, str) else repr(item)
                if key not in seen:
                    seen.add(key)
                    merged.append(item)
        if merged:
            out[field] = merged

    purposes = [str(p.get("purpose") or "").strip() for p in parts]
    out["purpose"] = max(purposes, key=len) if any(purposes) else out.get("purpose", "")
    out["partial_views"] = [p for p in purposes if p and p != out["purpose"]]
    out["chunked"] = len(parts)
    return out
