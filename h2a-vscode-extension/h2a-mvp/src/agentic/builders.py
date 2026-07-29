"""
builders.py — the Builder and Verifier agents.

These are deliberately thin: they reuse the proven Phase-0 stage functions
(generate_apex / validate_all / repair / deploy_and_heal) rather than
reimplementing codegen. The agentic value is in coordination and review
(Planner + Critic + Orchestrator), not in a second code generator.
"""

from __future__ import annotations

from src.agentic.blackboard import Artifact
from src.generate import (generate_apex, extract_method_signatures, clean_java_artifacts,
                          prepend_review_flag)
from src.validate import validate_all, repair


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
            source_classes=[{"class_name": c.get("class_name", ""), "layer": c.get("layer", ""),
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
            issues = validate_all(code, filename, schema)
            attempt = 1
            while issues and attempt <= max_repair:
                repaired = repair(code, issues, attempt=attempt, offline=offline,
                                  signatures=sigs, schema=schema)
                new_issues = validate_all(repaired, filename, schema)
                if not new_issues or len(new_issues) < len(issues):
                    code, issues = repaired, new_issues
                attempt += 1
            setattr(art, field_name, code)

    def apply_critic_repair(self, art, findings, schema, sigs, offline, max_repair, log=print) -> bool:
        """Feed ERROR-level Critic findings back into one bounded repair round."""
        errors = [f for f in findings if f.get("severity") == "ERROR"]
        if not errors:
            return False
        issues = [{"rule": f.get("category", "critic"), "message": f["message"],
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
        from src.verify import deploy_and_heal
        vcfg = config.get("verify", {})
        all_sigs = []
        for a in bb.artifacts:
            all_sigs += extract_method_signatures(a.main_class, a.target_name)
        # LWC bundles are already on disk and deploy as-is; only Apex feeds the
        # code-healing loop (which rewrites .cls files from these dicts).
        generated = [g for g in bb.generated_dicts() if g.get("layer") != "Component"]
        result = deploy_and_heal(
            bb.output_dir, generated,
            schema=bb.schema, signatures=all_sigs, offline=bb.offline,
            target_org=vcfg.get("target_org") or None,
            run_tests=vcfg.get("run_tests", False),
            auto_repair=vcfg.get("auto_repair", True),
            max_attempts=vcfg.get("max_deploy_attempts", config.get("max_repair_attempts", 2)),
            source_corpus=bb.source_corpus,
            coverage_threshold=vcfg.get("coverage_threshold", 75.0),
            log=log,
        )
        # deploy_and_heal mutates the generated dicts in place; mirror back to artifacts.
        by_name = {g["target_name"]: g for g in generated}
        for a in bb.artifacts:
            g = by_name.get(a.target_name)
            if g:
                a.main_class, a.test_class = g["main_class"], g["test_class"]
        return result
