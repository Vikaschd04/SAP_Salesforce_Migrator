"""
planner.py — the Planner / Architect agent.

Replaces the hard-coded `plan_targets()` mapping with a decision-maker. It still
derives the *structural* targets deterministically (so target names stay stable
and testable), then — with a real LLM — annotates each one:

    Convert → translate its logic fully to Apex (the default for almost everything).
              If a native Salesforce product (CPQ, Flow, Approval Process…) might be
              a better long-term home, the logic is STILL converted and the product
              is recorded in `native_recommendation` as a review suggestion.
    Skip    → only for code with no business logic to preserve (pure DTOs, framework
              glue, provably dead code), always with a justification.

The guiding principle is COMPLETENESS: never drop business logic just because a
native product overlaps with it — convert it and flag the suggestion instead.
With `mock`/offline it falls back to "convert everything as Apex", so the pipeline
stays deterministic and keyless.
"""

from __future__ import annotations

from src.agentic.blackboard import PlanItem
from src.agentic.router import route_model
from src.generate import plan_targets
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


class PlannerAgent:
    name = "Planner"

    def run(self, bb) -> None:
        # 1. Structural targets, deterministically, per domain (stable + testable).
        base = []
        for domain in bb.schedule:
            domain_class_names = {c["class_name"] for c in bb.domains.get(domain, [])}
            domain_classes = [c for c in bb.all_classes if c["class_name"] in domain_class_names]
            for t in plan_targets(domain_classes):
                base.append(PlanItem(
                    target_name=t["target_name"], layer=t["layer"], domain=domain,
                    source_classes=t["source_classes"],
                    apex_pattern=_LAYER_TO_PATTERN.get(t["layer"], "Utility"),
                ))

        # 2. Annotate with Apex/Native/Skip judgment (LLM), or default to Apex.
        provider = _get_provider(_load_config())
        if base and provider != "mock" and not bb.offline:
            self._annotate_with_llm(bb, base)
        else:
            for p in base:
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
