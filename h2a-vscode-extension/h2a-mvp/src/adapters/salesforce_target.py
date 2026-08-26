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

    def plan(self, model, config: dict) -> list:
        from src.generate import plan_targets
        units = [u.to_dict() for u in getattr(model, "units", [])]
        return plan_targets(units)

    def emit(self, output_dir: str, artifacts: list, model, config: dict) -> list:
        from src.generate import write_outputs, _load_mappings
        item_types = list(getattr(getattr(model, "data_model", None), "types", []) or [])
        return write_outputs(output_dir, artifacts, item_types, _load_mappings())

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
