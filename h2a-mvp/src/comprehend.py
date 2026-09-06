"""
comprehend.py — LLM-based class comprehension via structured outputs.

One call per class produces a validated JSON analysis:
  { purpose, inputs, outputs, side_effects, queries, business_rules }
"""

from __future__ import annotations

from pathlib import Path

from src.llm import call_structured, ProviderAuthError, _load_config

COMPREHENSION_SCHEMA = {
    "type": "object",
    "properties": {
        "purpose": {"type": "string"},
        "inputs": {"type": "array", "items": {"type": "string"}},
        "outputs": {"type": "array", "items": {"type": "string"}},
        "side_effects": {"type": "array", "items": {"type": "string"}},
        "queries": {"type": "array", "items": {"type": "string"}},
        "business_rules": {"type": "array", "items": {"type": "string"}},
        # Deeper analysis that makes downstream planning/building/review smarter:
        # what this class depends on, what could go wrong in the port, and how hard it is.
        "dependencies": {"type": "array", "items": {"type": "string"}},
        "migration_risks": {"type": "array", "items": {"type": "string"}},
        "complexity": {"type": "string", "enum": ["Low", "Medium", "High"]},
    },
    "required": ["purpose", "inputs", "outputs", "side_effects", "queries",
                 "business_rules", "dependencies", "migration_risks", "complexity"],
    "additionalProperties": False,
}


def _load_prompt_template() -> str:
    from src.packs import prompt
    return prompt("comprehend")


def _format_methods(methods: list) -> str:
    # Defensive: real-world classes have constructors (no return_type), varargs,
    # generics, etc. — a missing key must never crash comprehension.
    lines = []
    for m in (methods or []):
        params = ", ".join(f"{p.get('type', '')} {p.get('name', '')}".strip()
                           for p in (m.get("parameters", []) or []))
        sig = f"  {m.get('return_type', '')} {m.get('name', '')}({params})"
        lines.append(" ".join(sig.split()) or "  (method)")
    return "\n".join(lines) if lines else "  (none)"


#: Fields a model uses when it answers a "list of strings" schema with objects instead.
#: Ordered by how likely each is to be the *rule* rather than a label for it.
_RULE_FIELDS = ("rule", "description", "text", "statement", "detail", "summary",
                "condition", "name", "title")


def _as_strings(value) -> list:
    """Coerce a schema-declared list-of-strings into one, whatever the model returned.

    The schema asks for strings and one model answered `business_rules` with a list of
    objects. Nothing validated it, so the dicts travelled as far as the Planner's
    `", ".join(rules)` and took the whole migration down with a `TypeError` — after ten
    minutes of comprehension work, on a corpus that had just cost eight API calls.

    Swappable providers is a promise this project makes on its front page, and it is only
    as true as the narrowest assumption between here and the report. A model that answers
    a little differently should cost accuracy at worst, never the run. So the content is
    kept — the most rule-shaped field of an object, or a compact rendering of the whole
    thing — rather than dropped for not being the expected shape. [1.49]
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value.decode() if isinstance(value, bytes) else value]
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return [str(value)]

    out = []
    for item in value:
        if item is None:
            continue                    # `str(None)` is the word "None", not a rule
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = next((str(item[f]) for f in _RULE_FIELDS
                         if isinstance(item.get(f), (str, int, float)) and str(item[f]).strip()),
                        "")
            if not text:
                # No field we recognise: keep the whole object rather than lose the rule.
                text = "; ".join(f"{k}: {v}" for k, v in item.items() if v not in (None, "", []))
        elif isinstance(item, (list, tuple)):
            text = " ".join(str(x) for x in item)
        else:
            text = str(item)
        text = text.strip()
        if text:
            out.append(text)
    return out


def comprehend_class(class_info: dict, *, offline: bool = False,
                     model: str | None = None) -> dict:
    """Produce a structured JSON understanding of one Java class.

    A class that can't be analyzed (odd shape, malformed methods, a transient provider
    error) falls back to a deterministic understanding, so a single class can never abort
    the whole migration. Credentials the provider rejects are the exception and propagate:
    that failure applies to every class, and a fallback for all of them would report an
    estate with no business rules rather than a run that never started."""
    config = _load_config()
    max_tokens = config.get("max_tokens", {}).get("comprehend", 800)
    effort = config.get("effort", {}).get("comprehend", "low")
    name = class_info.get("class_name", "UnknownClass")
    layer = class_info.get("layer", "")

    try:
        from src.slim import slim_java, enabled as _slim_on
        raw = class_info.get("source", "")
        source_code = slim_java(raw)[0] if _slim_on(config) else raw
        template = _load_prompt_template()
        common = {
            "class_name": name,
            "layer": layer,
            "methods": _format_methods(class_info.get("methods", [])),
            "referenced_types": ", ".join(class_info.get("referenced_types", []) or [])
                                or "(none)",
        }

        # A class larger than the model can read used to be sent whole: the provider
        # rejected it, the resilience layer retried four times, and the unit landed as
        # "conversion failed" — four requests spent on something that could not succeed,
        # and the wrong reason reported. Comprehension chunks instead, because an
        # understanding merges: a rule found in either half is a rule the class holds. [1.28]
        from src import oversized
        chunks = ([source_code] if oversized.fits(source_code, model or "", max_tokens)
                  else oversized.split_source(source_code, model or "", max_tokens))

        parts = []
        for i, chunk in enumerate(chunks):
            result = call_structured(
                f"comprehend_{name}" + (f"_part{i + 1}" if len(chunks) > 1 else ""),
                template.format(source_code=chunk, **common),
                COMPREHENSION_SCHEMA, max_tokens,
                offline=offline, effort=effort, model=model,
            )
            if result.get("parsed"):
                parts.append(result["parsed"])

        understanding = (oversized.merge_understandings(parts) if parts
                         else _fallback_understanding(class_info))
        if len(chunks) > 1:
            print(f"    · {name} read in {len(chunks)} parts — too large for one call")
    except ProviderAuthError:
        # Containment is right for a class we cannot parse and wrong for credentials that
        # do not work: falling back here would report "no business rules" for every class
        # in the codebase, which reads exactly like a codebase that has none.
        raise
    except Exception:
        understanding = _fallback_understanding(class_info)

    if not isinstance(understanding, dict):
        understanding = _fallback_understanding(class_info)
    for key in ["inputs", "outputs", "side_effects", "queries", "business_rules",
                "dependencies", "migration_risks"]:
        understanding[key] = _as_strings(understanding.get(key))
    understanding.setdefault("purpose", f"{layer} class" if layer else str(name))
    understanding.setdefault("complexity", "Medium")
    return understanding


def _fallback_understanding(class_info: dict) -> dict:
    # Also fully defensive — this is the safety net, so it must not raise either.
    methods = class_info.get("methods", []) or []
    refs = class_info.get("referenced_types", []) or []
    name = class_info.get("class_name", "UnknownClass")
    layer = class_info.get("layer", "")
    return {
        "purpose": f"{layer} class: {name}" if layer else str(name),
        "inputs": [m.get("name", "") for m in methods if m.get("name")],
        "outputs": [m.get("return_type", "") for m in methods if m.get("return_type")],
        "side_effects": [],
        "queries": [],
        "business_rules": [],
        "dependencies": list(refs),
        "migration_risks": [],
        "complexity": "High" if len(methods) > 8 else "Medium",
    }
