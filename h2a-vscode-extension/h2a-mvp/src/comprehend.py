"""
comprehend.py — LLM-based class comprehension via structured outputs.

One call per class produces a validated JSON analysis:
  { purpose, inputs, outputs, side_effects, queries, business_rules }
"""

from __future__ import annotations

from pathlib import Path

from src.llm import call_structured, _load_config

COMPREHENSION_SCHEMA = {
    "type": "object",
    "properties": {
        "purpose": {"type": "string"},
        "inputs": {"type": "array", "items": {"type": "string"}},
        "outputs": {"type": "array", "items": {"type": "string"}},
        "side_effects": {"type": "array", "items": {"type": "string"}},
        "queries": {"type": "array", "items": {"type": "string"}},
        "business_rules": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["purpose", "inputs", "outputs", "side_effects", "queries", "business_rules"],
    "additionalProperties": False,
}


def _load_prompt_template() -> str:
    return (Path(__file__).resolve().parent / "prompts" / "comprehend.txt").read_text(encoding="utf-8")


def _format_methods(methods: list) -> str:
    lines = []
    for m in methods:
        params = ", ".join(f"{p['type']} {p['name']}" for p in m.get("parameters", []))
        lines.append(f"  {m['return_type']} {m['name']}({params})")
    return "\n".join(lines) if lines else "  (none)"


def comprehend_class(class_info: dict, *, offline: bool = False,
                     model: str | None = None) -> dict:
    """Produce a structured JSON understanding of one Java class."""
    config = _load_config()
    max_tokens = config.get("max_tokens", {}).get("comprehend", 800)
    effort = config.get("effort", {}).get("comprehend", "low")

    prompt = _load_prompt_template().format(
        java_source=class_info["source"],
        class_name=class_info["class_name"],
        layer=class_info["layer"],
        methods=_format_methods(class_info["methods"]),
        referenced_types=", ".join(class_info.get("referenced_types", [])) or "(none)",
    )

    result = call_structured(
        f"comprehend_{class_info['class_name']}",
        prompt,
        COMPREHENSION_SCHEMA,
        max_tokens,
        offline=offline,
        effort=effort,
        model=model,
    )

    understanding = result.get("parsed") or _fallback_understanding(class_info)
    for key in ["purpose", "inputs", "outputs", "side_effects", "queries", "business_rules"]:
        understanding.setdefault(key, [] if key != "purpose" else f"{class_info['layer']} class")
    return understanding


def _fallback_understanding(class_info: dict) -> dict:
    return {
        "purpose": f"{class_info['layer']} class: {class_info['class_name']}",
        "inputs": [m["name"] for m in class_info.get("methods", [])],
        "outputs": [m["return_type"] for m in class_info.get("methods", [])],
        "side_effects": [],
        "queries": [],
        "business_rules": [],
    }
