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
        types = list(getattr(data_model, "types", None) or [])
        return write_outputs(output_dir, artifacts, types, _load_mappings())

    def validate(self, code: str, filename: str, schema: dict, config: dict) -> list:
        """Governor limits, structural checks, and SOQL grounded in the SObject schema.

        Delegates to the same `validate_all` the v1 path calls, so routing through the
        adapter cannot change which issues are found.
        """
        from src.validate import validate_all
        return validate_all(code, filename, schema)

    def verify(self, output_dir: str, config: dict) -> dict:
        from src.verify import sf_available
        if not sf_available():
            return {"ran": False, "success": False,
                    "message": "Salesforce CLI not on PATH — nothing was deploy-verified"}
        # The full deploy+self-heal loop is owned by VerifierAgent, which needs the whole
        # Blackboard. This reports reachability; the agent remains the caller.
        return {"ran": False, "success": False,
                "message": "deploy verification runs through VerifierAgent"}


ADAPTER = SalesforceTarget()
