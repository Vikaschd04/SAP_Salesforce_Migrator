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
    #: Headings for the generated system prompt. They used to be hardcoded Salesforce
    #: *for every pipeline*, so an Adobe→Hybris prompt said "never emit Salesforce Apex"
    #: and then, two sections later, "Target SObject schema (write SOQL only against
    #: these objects/fields)". The model resolved the contradiction the way anyone would
    #: — in favour of the concrete instruction — and wrote Apex into a Hybris
    #: migration. [1.56]
    #: How the response schema describes each field. A description is the most binding
    #: instruction in a structured request, and these were hardcoded Apex for every
    #: pipeline. [1.58]
    schema_text = {
        "main_class": "Complete Apex main class source.",
        "test_class": "Complete @isTest Apex class source.",
        "refs": "Custom objects (X__c) referenced by the main class.",
    }
    prompt_sections = {
        "types": "Java -> Salesforce type mappings",
        "schema": "Target SObject schema (write SOQL only against these objects/fields)",
    }
    retrieval_terms = ("apex fflib governor limits SOQL DML security bulkification "
                       "testing")
    #: This platform's source-file extension. The agents hardcoded `.cls` for both
    #: pipelines, so a Hybris run reported its findings against `PricingService.cls`.
    code_extension = ".cls"
    #: Globs matching the code this target writes, relative to the output directory.
    #: Shared code that needs to know "has anything been generated here already?" — the
    #: checkpoint's resume warning, for one — hardcoded `force-app/**/*.cls`, so the
    #: warning could never fire for a run that writes a SAP Commerce extension. [4.6]
    output_globs = ("force-app/**/*.cls",)
    #: Can this target's generated tests be strengthened in place after the run?
    #:
    #: `parity.close_parity_gaps` rewrites a test class to assert the business rules it
    #: does not yet cover, and both halves of it are Salesforce's: the prompt asks for an
    #: `@isTest` class using `Test.startTest()`, and the result is written to
    #: `force-app/main/default/classes`. It ran on *both* pipelines whenever a real
    #: provider was in use — so a real Adobe→Hybris run spent frontier-tier calls turning
    #: JUnit tests into Apex, found no `force-app` to write them to, and kept them in
    #: memory anyway, where the reports and the final validation then described them.
    #: Never seen in tests, because the stage is skipped under `mock`. [4.6]
    strengthens_tests = True
    #: What an adversarial reviewer should look for, in this platform's own terms.
    #:
    #: The Critic's review prompt was hardcoded Salesforce and ran on *both* pipelines —
    #: so every generated Java class in an Adobe→Hybris run was reviewed as "generated
    #: Apex", against fflib layering, FLS via `Security.stripInaccessible`, `with sharing`
    #: and governor limits. None of those exist on the target it was actually building
    #: for, and the findings drove a real repair loop. The Builder's prompt was given to
    #: the target in 1.48 and 1.56; the Critic's was missed. [4.6]
    review_criteria = (
        "  2. SECURITY — FLS via Security.stripInaccessible, correct 'with sharing'\n"
        "  3. FFLIB — Selector owns SOQL, Service stateless/bulkified, Controller thin\n"
        "  4. GOVERNOR — no SOQL/DML in loops, bulk-safe collections")
    #: Retrieval terms for the Critic specifically — it is reviewing, not generating.
    review_terms = ("security FLS sharing governor limits bulkification fflib review")

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
