"""
builders.py — the Builder and Verifier agents.

These are deliberately thin: they reuse the proven Phase-0 stage functions
(generate_apex / validate / repair / deploy_and_heal) rather than
reimplementing codegen. The agentic value is in coordination and review
(Planner + Critic + Orchestrator), not in a second code generator.
"""

from __future__ import annotations

from src.agentic.blackboard import Artifact
from src.generate import (generate_apex, extract_method_signatures, clean_java_artifacts,
                          prepend_review_flag)
from src.validate import repair
from src.pipeline import validate_artifact


def _derived_queries(source_classes: list) -> str:
    """Translated queries for these sources, from the running source platform's analyser.

    Asked of the pipeline rather than imported directly: a Magento source has collections
    and raw SQL, not FlexibleSearch, and its own analyser is what would answer here. A
    platform with nothing to contribute returns nothing rather than erroring. [1.23b]
    """
    try:
        from src.adapters.hybris_flexsearch import grounding_for
        from src import pipeline, runctx

        pipeline.ensure_registered()
        pid = runctx.pipeline_id()
        p = pipeline.get(pid) if pid else pipeline.default_pipeline()
        if p.source_platform != "hybris":
            return ""
        return grounding_for([c.get("source", "") for c in (source_classes or [])])
    except Exception:
        return ""


def _transaction_shapes(source_classes: list) -> str:
    """What each `@Transactional` method becomes, decided rather than generated. [1.21c]

    Left to the model, "translate @Transactional" reliably produces a savepoint. That is
    right for a method that catches and continues, and wasteful for one that only throws —
    and the second is the common shape.
    """
    try:
        from src import pipeline, runctx
        from src.adapters.java_transactions import grounding_for

        pipeline.ensure_registered()
        pid = runctx.pipeline_id()
        p = pipeline.get(pid) if pid else pipeline.default_pipeline()
        if p.source_platform != "hybris":
            return ""
        return grounding_for([c.get("source", "") for c in (source_classes or [])])
    except Exception:
        return ""


def _data_model_notes(bb) -> str:
    """Modelling decisions the source does not settle, for the Builder's prompt. [1.43]

    Generated code that quietly picks a value for an unknown enum, or treats a suspected
    foreign key as a number, is a guess wearing the same clothes as a fact. Telling the
    model which calls are open is cheaper than reviewing what it invented.
    """
    try:
        from src.adapters.magento_modelling import grounding_for
        return grounding_for(getattr(bb, "modelling", None) or [])
    except Exception:
        return ""


def _rest_shapes(source_classes: list) -> str:
    """How many endpoints share a verb, and whether the path can be declared. [1.25]

    Left to the model, a controller with two `GET` mappings becomes a class with two
    `@HttpGet` methods, which does not compile — and a path with a variable in the middle
    becomes a `urlMapping` that never matches, which does.
    """
    try:
        from src import pipeline, runctx
        from src.adapters.rest_surface import grounding_for

        pipeline.ensure_registered()
        pid = runctx.pipeline_id()
        p = pipeline.get(pid) if pid else pipeline.default_pipeline()
        if p.source_platform != "hybris":
            return ""
        return grounding_for([c.get("source", "") for c in (source_classes or [])])
    except Exception:
        return ""


def _angular_gaps(component: dict) -> str:
    """Constructs with no LWC equivalent, for the generator's prompt. [1.24]

    Decided from the source rather than left to the model, which reaches for `@wire`
    because that is the answer to the question it is asked most often — and the wrong one
    for a poll, which `@wire` cannot do at all.
    """
    if not component:
        return ""
    from src.adapters.angular_gaps import grounding_for
    return grounding_for(component)


class BuilderAgent:
    """Generates one target's Apex, then repairs objective (governor/schema) issues."""
    name = "Builder"

    def build(self, plan_item, bb, scoped_sigs: list, mappings: dict,
              max_repair: int, log=print, retriever=None) -> Artifact:
        if plan_item.layer == "Component":
            return self._build_lwc(plan_item, bb, retriever)
        target = {"target_name": plan_item.target_name, "layer": plan_item.layer,
                  "source_classes": plan_item.source_classes}
        grounding = ""
        if retriever is not None:
            rules = []
            for c in plan_item.source_classes:
                rules += bb.comprehensions.get(c.get("class_name", ""), {}).get("business_rules", []) or []
            grounding = retriever.grounding_block(
                f"{plan_item.apex_pattern} apex fflib governor limits SOQL DML security "
                f"bulkification testing {' '.join(rules)}")

        # Queries this target's own source contains, already translated. Derived, not
        # generated — and a query that can be derived should never be generated. [1.23b]
        for block in (_derived_queries(plan_item.source_classes),
                      _transaction_shapes(plan_item.source_classes),
                      _rest_shapes(plan_item.source_classes),
                      _data_model_notes(bb)):
            if block:
                grounding = (grounding + "\n\n" + block) if grounding else block
        gen = generate_apex(target, bb.comprehensions, scoped_sigs,
                            offline=bb.offline, schema=bb.schema, mappings=mappings,
                            grounding=grounding)

        rules = []
        for c in plan_item.source_classes:
            rules += bb.comprehensions.get(c.get("class_name", ""), {}).get("business_rules", []) or []

        art = Artifact(
            target_name=plan_item.target_name, layer=plan_item.layer,
            apex_pattern=plan_item.apex_pattern,
            main_class=gen.get("main_class", ""), test_class=gen.get("test_class", ""),
            mapping_notes=gen.get("mapping_notes", ""), sobject_refs=gen.get("sobject_refs", []),
            business_rules=rules,
            # `file` is carried deliberately: downstream consumers (triage, provenance,
            # the ledger) key on it, and rebuilding this dict without it silently broke
            # the hazard-to-artifact mapping.
            source_classes=[{"class_name": c.get("class_name", ""), "layer": c.get("layer", ""),
                             "file": c.get("file", ""),
                             "source": c.get("source", "")} for c in plan_item.source_classes],
            status="generated",
        )
        self._repair_objective(art, bb.schema, max_repair, scoped_sigs, bb.offline, log)

        # Completeness policy: a native-product fit never suppresses conversion — the
        # logic is fully built above; here we only flag it for human review.
        native_alt = getattr(plan_item, "native_recommendation", "")
        if native_alt:
            art.review_flags.append(
                f"Consider {native_alt} as a better long-term home for this logic "
                f"(converted in full for completeness).")
            art.main_class = prepend_review_flag(art.main_class, native_alt, plan_item.rationale)
        return art

    def _build_lwc(self, plan_item, bb, retriever=None) -> Artifact:
        """Frontend target: translate an Angular component into an LWC bundle
        (+ optional @AuraEnabled Apex controller)."""
        from src.generate_lwc import generate_lwc
        component = plan_item.source_classes[0] if plan_item.source_classes else {}
        grounding = ""
        if retriever is not None:
            grounding = retriever.grounding_block(
                "LWC lightning web component api wire apex CustomEvent for:each if:true "
                "getter template data binding accessibility")
        gaps = _angular_gaps(component)
        if gaps:
            grounding = (grounding + "\n\n" + gaps) if grounding else gaps
        gen = generate_lwc(
            {"target_name": plan_item.target_name, "component": component},
            bb.comprehensions, bb.schema, offline=bb.offline, grounding=grounding)
        return Artifact(
            target_name=plan_item.target_name, layer="Component", apex_pattern="Component",
            lwc_bundle=gen.get("lwc_bundle", {}),
            apex_controller=gen.get("apex_controller", {}),
            mapping_notes=gen.get("mapping_notes", ""),
            sobject_refs=gen.get("sobject_refs", []),
            source_classes=[{"class_name": component.get("class_name", ""), "layer": "Component",
                             "source": component.get("source", "")}],
            status="generated",
        )

    def _repair_objective(self, art, schema, max_repair, sigs, offline, log) -> None:
        for field_name in ("main_class", "test_class"):
            is_test = field_name == "test_class"
            filename = f"{art.target_name}{'Test' if is_test else ''}.cls"
            code = getattr(art, field_name)
            issues = validate_artifact(code, filename, schema)
            attempt = 1
            while issues and attempt <= max_repair:
                repaired = repair(code, issues, attempt=attempt, offline=offline,
                                  signatures=sigs, schema=schema)
                new_issues = validate_artifact(repaired, filename, schema)
                if not new_issues or len(new_issues) < len(issues):
                    code, issues = repaired, new_issues
                attempt += 1
            setattr(art, field_name, code)

    def apply_critic_repair(self, art, findings, schema, sigs, offline, max_repair, log=print) -> bool:
        """Feed ERROR-level Critic findings back into one bounded repair round."""
        errors = [f for f in findings if f.get("severity") == "ERROR"]
        if not errors:
            return False
        # .get() everywhere, not just on `category` — critic.py now normalises its own
        # output, but this stays defensive in case a caller ever hands in raw findings
        # from somewhere else. A finding worth repairing must never crash the repair step.
        issues = [{"rule": f.get("category", "critic"),
                   "message": f.get("message") or "(unspecified issue)",
                   "severity": "ERROR"} for f in errors]
        repaired = repair(art.main_class, issues, attempt=1, offline=offline,
                          signatures=sigs, schema=schema)
        if repaired and repaired.strip() and repaired != art.main_class:
            art.main_class = clean_java_artifacts(repaired)
            return True
        return False

    def rework(self, art, feedback: str, bb, scoped_sigs: list, log=print):
        """Human-in-the-loop: re-generate an artifact to address a reviewer's feedback.
        For Apex the feedback goes through the repair loop; for LWC the bundle is
        regenerated with the feedback as grounding. (Mock exercises the flow; a real
        provider actually changes the output based on the note.)"""
        if art.is_lwc:
            from src.generate_lwc import generate_lwc
            component = art.source_classes[0] if art.source_classes else {}
            gen = generate_lwc({"target_name": art.target_name, "component": component},
                               bb.comprehensions, bb.schema, offline=bb.offline,
                               grounding="Reviewer feedback (must address): " + feedback)
            if gen.get("lwc_bundle"):
                art.lwc_bundle = gen["lwc_bundle"]
                art.apex_controller = gen.get("apex_controller", art.apex_controller)
        else:
            issues = [{"rule": "reviewer_feedback", "message": feedback, "severity": "ERROR"}]
            repaired = repair(art.main_class, issues, attempt=1, offline=bb.offline,
                              signatures=scoped_sigs, schema=bb.schema)
            if repaired and repaired.strip():
                art.main_class = clean_java_artifacts(repaired)
        art.status = "reworked"
        return art

    @staticmethod
    def signatures(art) -> list:
        return extract_method_signatures(art.main_class, art.target_name)


class VerifierAgent:
    """Owns the org: deploy + self-heal (metadata / Apex / coverage). Reuses deploy_and_heal."""
    name = "Verifier"

    def run(self, bb, config: dict, log=print) -> dict | None:
        all_sigs = []
        for a in bb.artifacts:
            all_sigs += extract_method_signatures(a.main_class, a.target_name)
        # LWC bundles are already on disk and deploy as-is; only Apex feeds the
        # code-healing loop (which rewrites .cls files from these dicts).
        generated = [g for g in bb.generated_dicts() if g.get("layer") != "Component"]

        # Whether an oracle exists at all is a property of the target platform, not of
        # this agent. Salesforce has a free hosted compiler; SAP does not. The agent
        # still owns the loop around it — collecting signatures, mirroring healed code
        # back onto the artifacts — because that part is platform-neutral.
        from src.pipeline import VerifyRequest, current_target
        request = VerifyRequest(
            output_dir=bb.output_dir, artifacts=generated, schema=bb.schema,
            signatures=all_sigs, source_corpus=bb.source_corpus, offline=bb.offline)

        target = current_target()
        if target is not None:
            result = target.verify(request, config, log=log)
        else:
            from src.adapters.salesforce_target import ADAPTER as _sf
            result = _sf.verify(request, config, log=log)
        # deploy_and_heal mutates the generated dicts in place; mirror back to artifacts.
        by_name = {g["target_name"]: g for g in generated}
        for a in bb.artifacts:
            g = by_name.get(a.target_name)
            if g:
                a.main_class, a.test_class = g["main_class"], g["test_class"]
        return result
