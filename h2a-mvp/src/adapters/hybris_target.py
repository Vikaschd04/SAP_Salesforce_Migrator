"""
hybris_target.py — SAP Hybris as a *target*.

**Scaffold. Not implemented.** Same reasoning as the Adobe source adapter: methods that
returned plausible empty values would produce a migration that reports success and emits
nothing, which is worse than one that refuses to start.

One field here is real and load-bearing today: `has_oracle = False`.

Salesforce lends us a free hosted compiler — `sf project deploy --dry-run` — which is what
lets a run claim *proven to run* rather than *generated*. SAP lends us nothing equivalent:
compiling generated Java needs a licensed multi-gigabyte SAP Commerce distribution present
wherever the migration runs. Until item 3.11 supplies one, an Adobe→Hybris run is
**statically checked, not verified**, and the sign-off contract reads this flag rather than
assuming. Setting it True to make the reports look better would be the exact overclaim the
product is built not to make.

Implementation is Phase 3 — see docs/V2_DELIVERY_PLAN.md items 3.1–3.12.
"""

from __future__ import annotations

from src.adapters.adobe_source import NotImplementedYet


class HybrisTarget:
    platform = "hybris"
    label = "SAP Hybris (Java · Spring · items.xml)"
    implemented = False

    #: No free compile oracle. See the module docstring — this is honest, not pending.
    has_oracle = False

    def plan(self, units: list, config: dict) -> list:
        raise NotImplementedYet("Planning Hybris targets", "3.2")

    def emit(self, output_dir: str, artifacts: list, data_model, config: dict) -> list:
        raise NotImplementedYet("Emitting a Hybris extension", "3.1–3.7")

    def validate(self, code: str, filename: str, schema: dict, config: dict) -> list:
        raise NotImplementedYet("Validating generated Java", "3.10")

    def verify(self, output_dir: str, config: dict) -> dict:
        """No oracle yet. Reports that plainly rather than claiming a clean verification."""
        return {
            "ran": False,
            "success": False,
            "message": ("SAP Commerce has no hosted compile oracle. Generated Java is "
                        "statically checked, not verified, until a licensed platform is "
                        "available (items 3.10–3.12)."),
        }


ADAPTER = HybrisTarget()
