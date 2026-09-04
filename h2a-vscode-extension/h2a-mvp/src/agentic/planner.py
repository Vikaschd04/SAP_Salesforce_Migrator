"""
planner.py — the Planner / Architect agent.

Replaces a hard-coded structural mapping with a decision-maker. It still derives the
*structural* targets deterministically (so target names stay stable and testable), then —
with a real LLM — annotates each one:

    Convert → translate its logic fully (the default for almost everything). If a native
              product on the target platform (Salesforce CPQ, Flow, Approval Process…)
              might be a better long-term home, the logic is STILL converted and the
              product is recorded in `native_recommendation` as a review suggestion.
    Skip    → only for code with no business logic to preserve (pure DTOs, framework
              glue, provably dead code), always with a justification.

The guiding principle is COMPLETENESS: never drop business logic just because a
native product overlaps with it — convert it and flag the suggestion instead.
With `mock`/offline it falls back to "convert everything", so the pipeline stays
deterministic and keyless.

**The Planner does not know what platform it is targeting.** Candidate targets come from
the pipeline's target adapter (see `_candidate_targets`), so the same agent plans Apex for
a Salesforce target and Java services for a Hybris one. What it *does* own is the
judgement on top — Convert vs Skip, and the native-product flag — which is the same
question whatever the destination.
"""

from __future__ import annotations

from src.agentic.blackboard import PlanItem
from src.agentic.router import route_model
from src.llm import call_structured, _load_config, _get_provider

_LAYER_TO_PATTERN = {
    "DAO": "Selector", "Service": "Service", "Controller": "Controller",
    "Utility": "Utility", "Component": "Component",
}

PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "target_kind": {"type": "string", "enum": ["Convert", "Skip"]},
                    "rationale": {"type": "string"},
                    "native_recommendation": {"type": "string"},
                },
                "required": ["target_name", "target_kind", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["decisions"],
    "additionalProperties": False,
}


def _candidate_targets(bb, classes: list) -> list:
    """What the target platform would build from this slice of source classes.

    v1 calls `generate.plan_targets` — which knows about Apex, Selectors and LWC — so the
    Planner was hard-wired to one target platform. v2 asks the pipeline's target adapter
    instead, so the same Planner produces Java services for a Hybris target and Apex for a
    Salesforce one without knowing either exists.

    `bb.pipeline_id` is set only on the v2 path, so it doubles as the switch: one source of
    truth for which engine is running, rather than a second flag that could disagree with it.
    """
    if bb.pipeline_id:
        # ensure_registered() is idempotent, and calling it here means the Planner does not
        # depend on the orchestrator having registered first — the lookup would otherwise
        # raise KeyError in any entry point that reaches the Planner by another route.
        from src.pipeline import ensure_registered, get as get_pipeline
        from src.llm import _load_config
        ensure_registered()
        return get_pipeline(bb.pipeline_id).target.plan(classes, _load_config())
    from src.generate import plan_targets
    return plan_targets(classes)


class PlannerAgent:
    name = "Planner"

    def run(self, bb) -> None:
        # 1. Structural targets, deterministically, per domain (stable + testable).
        base = []
        for domain in bb.schedule:
            domain_class_names = {c["class_name"] for c in bb.domains.get(domain, [])}
            domain_classes = [c for c in bb.all_classes if c["class_name"] in domain_class_names]
            for t in _candidate_targets(bb, domain_classes):
                base.append(PlanItem(
                    target_name=t["target_name"], layer=t["layer"], domain=domain,
                    source_classes=t["source_classes"],
                    apex_pattern=_LAYER_TO_PATTERN.get(t["layer"], "Utility"),
                    # The target adapter already decided what this becomes and why.
                    # Both were being dropped here. [1.33]
                    kind=t.get("kind", ""),
                    rationale=t.get("rationale", ""),
                ))

        # 2. Annotate with Apex/Native/Skip judgment (LLM), or default to Apex.
        provider = _get_provider(_load_config())
        if base and provider != "mock" and not bb.offline:
            self._annotate_with_llm(bb, base)
        else:
            for p in base:
                # Only where the adapter gave no reason. Overwriting one it did give
                # replaces a real explanation with a placeholder. [1.33]
                if not p.rationale:
                    p.rationale = "deterministic default (mock/offline): converted as Apex"

        bb.plan = base
        n_convert = sum(1 for p in base if p.target_kind == "Convert")
        n_flagged = sum(1 for p in base if p.target_kind == "Convert" and p.native_recommendation)
        n_skip = sum(1 for p in base if p.target_kind == "Skip")
        bb.record(self.name, "planned",
                  f"{len(base)} targets → {n_convert} converted "
                  f"({n_flagged} with a native-product review flag), {n_skip} skipped")
        for p in base:
            if p.target_kind == "Convert" and p.native_recommendation:
                bb.ask(self.name, f"{p.target_name}: converted in full; consider "
                                   f"{p.native_recommendation} as a better long-term home — {p.rationale}")
            elif p.target_kind == "Skip":
                bb.ask(self.name, f"{p.target_name}: skipped (no business logic to preserve) — {p.rationale}")

    def _annotate_with_llm(self, bb, base: list) -> None:
        config = _load_config()
        catalog = []
        for p in base:
            rules = []
            for c in p.source_classes:
                rules += bb.comprehensions.get(c["class_name"], {}).get("business_rules", []) or []
            snippet = "; ".join(c["class_name"] for c in p.source_classes)
            catalog.append(f"- {p.target_name} (from {snippet}, layer={p.layer}); "
                           f"rules: {', '.join(rules) or 'n/a'}")
        prompt = (
            "You are the migration architect. Your PRIMARY DUTY is COMPLETENESS: every piece "
            "of business logic must be CONVERTED to Apex. Never drop logic just because "
            "Salesforce ships a product that overlaps with it.\n\n"
            "For each proposed Salesforce target below, choose:\n"
            "  Convert = translate its logic fully to Apex. This is the default and applies to "
            "almost everything — including pricing, promotions, discounts, approvals, tax, "
            "inventory rules, etc. If a standard Salesforce product (CPQ, Flow, Approval "
            "Process, OmniStudio…) might be a better long-term home, STILL choose Convert AND "
            "set native_recommendation to that product's name. We convert the logic now and "
            "flag that suggestion for the team to evaluate later — we do NOT skip it.\n"
            "  Skip = ONLY for code that carries no business logic to preserve: pure "
            "DTOs / getters-setters, framework glue / boilerplate, or provably dead code. "
            "Every Skip MUST be justified in the rationale.\n\n"
            "When in doubt, choose Convert. Give a one-line rationale for each; for a "
            "native_recommendation, name the specific product.\n\n"
            "Targets:\n" + "\n".join(catalog)
        )
        try:
            result = call_structured(
                "plan_repo", prompt, PLANNER_SCHEMA,
                config.get("max_tokens", {}).get("comprehend", 800),
                offline=bb.offline, effort=config.get("effort", {}).get("comprehend", "low"),
                model=route_model(config, "plan_repo"),
            )
            decisions = {d["target_name"]: d for d in (result.get("parsed") or {}).get("decisions", [])}
        except Exception as ex:  # planning must never abort the run
            bb.record(self.name, "llm_planning_failed", f"{str(ex)[:120]} — defaulting all to Apex")
            decisions = {}

        for p in base:
            d = decisions.get(p.target_name)
            if not d:
                p.rationale = "default: converted as Apex (no explicit planner decision)"
                continue
            kind = d.get("target_kind", "Convert")
            p.target_kind = kind if kind in ("Convert", "Skip") else "Convert"
            p.rationale = d.get("rationale", "")
            p.native_recommendation = d.get("native_recommendation", "")
