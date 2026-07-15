"""
builders.py — the Builder and Verifier agents.

These are deliberately thin: they reuse the proven Phase-0 stage functions
(generate_apex / validate_all / repair / deploy_and_heal) rather than
reimplementing codegen. The agentic value is in coordination and review
(Planner + Critic + Orchestrator), not in a second code generator.
"""

from __future__ import annotations

from src.agentic.blackboard import Artifact
from src.generate import generate_apex, extract_method_signatures, clean_java_artifacts
from src.validate import validate_all, repair


class BuilderAgent:
    """Generates one target's Apex, then repairs objective (governor/schema) issues."""
    name = "Builder"

    def build(self, plan_item, bb, scoped_sigs: list, mappings: dict,
              max_repair: int, log=print, retriever=None) -> Artifact:
        target = {"target_name": plan_item.target_name, "layer": plan_item.layer,
                  "source_classes": plan_item.source_classes}
        grounding = ""
        if retriever is not None:
            rules = []
            for c in plan_item.source_classes:
                rules += bb.comprehensions.get(c["class_name"], {}).get("business_rules", []) or []
            grounding = retriever.grounding_block(
                f"{plan_item.apex_pattern} apex fflib governor limits SOQL DML security "
                f"bulkification testing {' '.join(rules)}")
        gen = generate_apex(target, bb.comprehensions, scoped_sigs,
                            offline=bb.offline, schema=bb.schema, mappings=mappings,
                            grounding=grounding)

        rules = []
        for c in plan_item.source_classes:
            rules += bb.comprehensions.get(c["class_name"], {}).get("business_rules", []) or []

        art = Artifact(
            target_name=plan_item.target_name, layer=plan_item.layer,
            apex_pattern=plan_item.apex_pattern,
            main_class=gen.get("main_class", ""), test_class=gen.get("test_class", ""),
            mapping_notes=gen.get("mapping_notes", ""), sobject_refs=gen.get("sobject_refs", []),
            business_rules=rules,
            source_classes=[{"class_name": c["class_name"], "layer": c.get("layer", ""),
                             "source": c.get("source", "")} for c in plan_item.source_classes],
            status="generated",
        )
        self._repair_objective(art, bb.schema, max_repair, scoped_sigs, bb.offline, log)
        return art

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
        generated = bb.generated_dicts()
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
