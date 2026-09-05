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
    #: Terms that retrieve this platform's knowledge from the pack. The Builder used
    #: to hardcode these, so a run on the *other* pipeline searched a shelf of Hybris
    #: documents for "apex fflib governor limits" and was handed whatever matched
    #: worst — under a heading that called it a Salesforce reference. [1.48]
    retrieval_terms = ("apex fflib governor limits SOQL DML security bulkification "
                       "testing")

    #: An org can be queried before generating, and its contents can collide with the
    #: plan. See `orgfit`. [1.33]
    has_org = True

    def schema(self, item_types: list, relations: list, enum_types: list) -> dict:
        """SObjects, exactly as the shipped path builds them.

        Delegates to the same `build_schema` the orchestrator called directly, so routing
        through the adapter cannot change a single field. [1.33]
        """
        from src.schema import build_schema
        return build_schema(item_types, relations, enum_types)

    def reconcile(self, schema: dict, prelim: dict, corpus: str) -> tuple:
        """Add fields the generated Apex proves must exist. Unchanged behaviour. [1.33]"""
        from src.schema import reconcile_schema
        return reconcile_schema(schema, prelim, corpus)

    def emit_schema(self, output_dir: str, schema: dict) -> list:
        """One file per object and field, under `force-app`. Unchanged behaviour. [1.33]"""
        from src.metadata_generator import write_schema_metadata
        return write_schema_metadata(output_dir, schema)

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
        result = deploy_and_heal(
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
        # A dry-run deploy is a compile. Running the generated tests is a rung higher,
        # and only that rung may be described as behaviour having been checked. [3.9]
        from src import assurance
        ran_tests = bool(vcfg.get("run_tests", False)) and result.get("success")
        result["rung"] = (assurance.REPLAYED if ran_tests
                          else assurance.COMPILED if result.get("success")
                          else assurance.NONE)
        return result

    # ── characterization: recorded facts → replayable Apex ────────────────────
    # The neutral layer decides which behaviours are worth replaying; these four say
    # what a replay looks like in Apex. See adapters/apex_characterization.py.

    def symbols(self, code: str) -> list:
        """Apex method declarations, for provenance. Apex is Java-shaped. [2.11]"""
        from src.adapters.braced_symbols import symbols as _s
        return _s(code)

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
