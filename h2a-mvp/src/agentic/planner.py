"""
planner.py — the Planner / Architect agent.

Replaces the hard-coded `plan_targets()` mapping with a decision-maker. It still
derives the *structural* targets deterministically (so target names stay stable
and testable), then — with a real LLM — annotates each one with the judgment that
a fixed function can't make:

    Apex   → build it as custom Apex (Selector / Service / Controller / Utility)
    Native → recommend a Salesforce product instead (CPQ, Flow, Approval Process…)
    Skip   → don't migrate (dead code, framework glue, etc.)

The "Native / Skip" calls are the single most valuable output — knowing what
*not* to hand-translate is what separates a migration platform from a code
translator. With `mock`/offline it falls back to "everything is Apex", so the
pipeline stays deterministic and keyless.
"""

from __future__ import annotations

from src.agentic.blackboard import PlanItem
from src.agentic.router import route_model
from src.generate import plan_targets
from src.llm import call_structured, _load_config, _get_provider

_LAYER_TO_PATTERN = {
    "DAO": "Selector", "Service": "Service", "Controller": "Controller",
    "Utility": "Utility",
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
                    "target_kind": {"type": "string", "enum": ["Apex", "Native", "Skip"]},
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
                p.rationale = "deterministic default (mock/offline: all targets built as Apex)"

        bb.plan = base
        n_apex = sum(1 for p in base if p.target_kind == "Apex")
        n_native = sum(1 for p in base if p.target_kind == "Native")
        n_skip = sum(1 for p in base if p.target_kind == "Skip")
        bb.record(self.name, "planned",
                  f"{len(base)} targets → {n_apex} Apex, {n_native} native-recommended, {n_skip} skipped")
        for p in base:
            if p.target_kind == "Native":
                bb.ask(self.name, f"{p.target_name}: consider {p.native_recommendation or 'a native Salesforce feature'} "
                                   f"instead of custom Apex — {p.rationale}")
            elif p.target_kind == "Skip":
                bb.ask(self.name, f"{p.target_name}: recommended skip — {p.rationale}")

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
            "You are the migration architect. For each proposed Salesforce target below, "
            "decide the BEST home for its logic:\n"
            "  Apex   = build as custom Apex (default for genuine data-access / service / REST logic)\n"
            "  Native = a standard Salesforce product fits far better (pricing/promotions → CPQ; "
            "approvals/workflow → Flow or Approval Process; simple field automation → Flow)\n"
            "  Skip   = don't migrate (framework glue, dead code, pure DTOs)\n\n"
            "Prefer Apex unless there is a clear, specific native fit. Give a one-line rationale, "
            "and for Native, name the product.\n\n"
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
                p.rationale = "default: built as Apex (no explicit planner decision)"
                continue
            kind = d.get("target_kind", "Apex")
            p.target_kind = kind if kind in ("Apex", "Native", "Skip") else "Apex"
            p.rationale = d.get("rationale", "")
            p.native_recommendation = d.get("native_recommendation", "")
