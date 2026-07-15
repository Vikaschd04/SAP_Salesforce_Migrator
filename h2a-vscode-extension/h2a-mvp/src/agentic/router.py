"""
router.py — per-task model routing.

The cheapest way to cut cost without losing quality is to stop paying frontier
prices for easy work. Comprehension and planning are classification-ish and do
fine on a small/fast model; generation, repair, and critique are where reasoning
quality matters and earn a frontier model.

Routing only applies to the `anthropic` provider (the model ids are Claude ids);
for `openrouter`/`mock` the router returns None and the configured model is used.

config.yaml:
    agentic:
      routing:
        enabled: true
        models: {cheap: claude-haiku-4-5-20251001, frontier: claude-opus-4-8}
        tiers:  {comprehend: cheap, plan: cheap, generate: frontier,
                 repair: frontier, critic: frontier, strengthen: frontier, parity: frontier}
"""

from __future__ import annotations

# Stage-name prefix -> task family, so "generate_OrderSelector" maps to "generate".
_STAGE_FAMILIES = ("comprehend", "plan", "generate", "repair", "critic",
                   "strengthen", "parity")

_DEFAULT_TIERS = {
    "comprehend": "cheap", "plan": "cheap", "generate": "frontier",
    "repair": "frontier", "critic": "frontier", "strengthen": "frontier",
    "parity": "frontier",
}


def _family(stage: str) -> str:
    for fam in _STAGE_FAMILIES:
        if stage.startswith(fam):
            return fam
    return "generate"  # unknown -> treat as reasoning-heavy


def route_model(config: dict, stage: str) -> str | None:
    """Return the model id to use for `stage`, or None to use the default model."""
    routing = (config.get("agentic") or {}).get("routing") or {}
    if not routing.get("enabled", False):
        return None
    models = routing.get("models") or {}
    tiers = {**_DEFAULT_TIERS, **(routing.get("tiers") or {})}
    tier = tiers.get(_family(stage), "frontier")
    return models.get(tier)  # None if that tier isn't configured -> default model
