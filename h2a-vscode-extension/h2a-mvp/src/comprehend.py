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
    return (Path(__file__).resolve().parent / "prompts" / "comprehend.txt").read_text(encoding="utf-8")


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
        java_source = slim_java(raw)[0] if _slim_on(config) else raw
        prompt = _load_prompt_template().format(
            java_source=java_source,
            class_name=name,
            layer=layer,
            methods=_format_methods(class_info.get("methods", [])),
            referenced_types=", ".join(class_info.get("referenced_types", []) or []) or "(none)",
        )
        result = call_structured(
            f"comprehend_{name}", prompt, COMPREHENSION_SCHEMA, max_tokens,
            offline=offline, effort=effort, model=model,
        )
        understanding = result.get("parsed") or _fallback_understanding(class_info)
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
        understanding.setdefault(key, [])
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
