"""
salesforce_target.py — Salesforce as a *target*.

Thin by design, for the same reason as the source adapter. Note `has_oracle = True`: this
target can be compiled by an authority that is not us, which is what lets a run claim
*proven to run* rather than *generated*. The Hybris target will set it False until a
licensed platform is available — and the sign-off contract reads that flag rather than
assuming.
"""

from __future__ import annotations


class SalesforceTarget:
    platform = "salesforce"
    label = "Salesforce (Apex · LWC · metadata)"
    has_oracle = True                      # `sf project deploy --dry-run`
    code_language = "Apex"                 # what generated code is called, in reports

    def plan(self, units: list, config: dict) -> list:
        """What Salesforce builds from these source units: Selectors, Services, LWC…

        Delegates to the same `plan_targets` the v1 path calls, so routing through the
        adapter cannot change what gets planned. Accepts either IR units or the plain
        dicts the pipeline passes today.
        """
        from src.generate import plan_targets
        return plan_targets([u.to_dict() if hasattr(u, "to_dict") else u
                             for u in (units or [])])

    def emit(self, output_dir: str, artifacts: list, data_model, config: dict) -> list:
        """The SFDX layout: force-app/main/default/{classes,lwc,objects} + sfdx-project.json.

        Delegates to the same `write_outputs` the v1 path calls, so routing through the
        adapter cannot change what lands on disk.
        """
        from src.generate import write_outputs, _load_mappings
        from src.schema import build_schema
        types = list(getattr(data_model, "types", None) or [])
        # Built from the same DataModel the metadata comes from, so MAPPING.md reports
        # the fields that were actually emitted rather than a second guess at them. [1.31]
        schema = build_schema(types,
                              list(getattr(data_model, "relations", None) or []),
                              list(getattr(data_model, "enums", None) or []))
        return write_outputs(output_dir, artifacts, types, _load_mappings(), schema)

    def validate(self, code: str, filename: str, schema: dict, config: dict) -> list:
        """Governor limits, structural checks, and SOQL grounded in the SObject schema.

        Delegates to the same `validate_all` the v1 path calls, so routing through the
        adapter cannot change which issues are found.
        """
        from src.validate import validate_all
        return validate_all(code, filename, schema)

    def verify(self, request, config: dict, log=print) -> dict:
        """Validate-only deploy to a real org, reading real compiler errors and healing.

        This is what lets a run say *proven to run* rather than *looks right*, and it is
        only possible because Salesforce lends us a free hosted compiler. Delegates to the
        same `deploy_and_heal` the v1 path calls.
        """
        from src.verify import deploy_and_heal, sf_available
        vcfg = (config or {}).get("verify", {}) or {}
        if not sf_available():
            return {"ran": False, "success": False,
                    "message": "Salesforce CLI not on PATH — nothing was deploy-verified"}
        return deploy_and_heal(
            request.output_dir, request.artifacts,
            schema=request.schema, signatures=request.signatures,
            offline=request.offline,
            target_org=vcfg.get("target_org") or None,
            run_tests=vcfg.get("run_tests", False),
            auto_repair=vcfg.get("auto_repair", True),
            max_attempts=vcfg.get("max_deploy_attempts",
                                  (config or {}).get("max_repair_attempts", 2)),
            source_corpus=request.source_corpus,
            coverage_threshold=vcfg.get("coverage_threshold", 75.0),
            log=log,
        )

    # ── characterization: recorded facts → replayable Apex ────────────────────
    # The neutral layer decides which behaviours are worth replaying; these four say
    # what a replay looks like in Apex. See adapters/apex_characterization.py.

    def find_method(self, code: str, name: str) -> dict | None:
        from src.adapters import apex_characterization as ac
        return ac.find_method(code, name)

    def emit_characterization(self, runnable_by_target: dict) -> dict:
        from src.adapters import apex_characterization as ac
        return ac.emit(runnable_by_target)

    def literal(self, value: dict | None) -> str | None:
        from src.adapters import apex_characterization as ac
        return ac.literal(value)

    def bridge_request(self, target: str, code: str, rows: list) -> dict:
        from src.adapters import apex_characterization as ac
        return ac.bridge_request(target, code, rows)

ADAPTER = SalesforceTarget()
