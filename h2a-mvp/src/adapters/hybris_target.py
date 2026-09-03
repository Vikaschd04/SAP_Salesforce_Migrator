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
    #: The target can now scaffold a whole extension — skeleton, items.xml, services,
    #: DAOs, jobs, configuration and wiring — and check it at the `static` rung. What it
    #: cannot yet do is *fill method bodies*: that needs a Hybris prompt pack (3.8), so a
    #: run would produce an extension whose logic is all `UnsupportedOperationException`.
    #: Claiming `implemented` for that would be the success-shaped failure this product is
    #: arranged against, so it stays false until 3.8.
    implemented = False

    #: No free compile oracle. See the module docstring — this is honest, not pending.
    has_oracle = False
    code_language = "Java"

    def plan(self, units: list, config: dict) -> list:
        """What Hybris builds from these units, with the reason for each choice. [3.2b]

        `config["wiring"]` carries the di.xml reading when there is one; without it a
        plugin cannot be classified and routes to the safe superset. See hybris_plan.
        """
        from src.adapters.hybris_plan import plan_targets
        return plan_targets(units or [], (config or {}).get("wiring"))

    def emit(self, output_dir: str, artifacts: list, data_model, config: dict) -> list:
        """Assemble the extension. [3.1–3.6]

        `config` carries what the target list cannot: `source_model` for the jobs and the
        data model, and `plan` for the kind each unit was routed to. Without a source
        model this refuses rather than writing a skeleton — an extension with a data model
        and no services reads as a finished migration of a codebase that had no logic.
        """
        cfg = config or {}
        source_model = cfg.get("source_model")
        if source_model is None:
            raise NotImplementedYet(
                "Emitting a Hybris extension needs the SourceModel (config['source_model'])"
                " — the jobs and the data model are not derivable from the artifact list",
                "3.1–3.6")

        from src.adapters.hybris_emit import emit_extension

        result = emit_extension(
            output_dir,
            name=cfg.get("extension_name", "migrated"),
            package=cfg.get("package", "com.migrated"),
            source_model=source_model,
            targets=cfg.get("plan") or [],
        )
        # Kept for the caller: what was written, what was planned and deliberately not
        # written, and how strongly the result was checked.
        self.last_emit = result
        return result["created"]

    def validate(self, code: str, filename: str, schema: dict, config: dict) -> list:
        """Parse, and resolve every named type. [3.10]

        The strongest check available without a licensed platform, and it says so: a type
        mismatch or a missing override needs real type checking, which is rung 3.11.
        """
        from src.adapters.java_static_check import check
        return check(code, filename,
                     emitted=(config or {}).get("emitted_types"),
                     items_xml=(config or {}).get("items_xml", ""))

    def verify(self, request, config: dict, log=print) -> dict:
        """No oracle yet. Reports that plainly rather than claiming a clean verification."""
        from src import assurance

        # With an output directory to read, the static rung is a real result rather
        # than an absence — it parsed and resolved, or it did not. [3.10]
        out_dir = getattr(request, "output_dir", "") if request is not None else ""
        if out_dir:
            from src.adapters.java_static_check import check_tree
            got = check_tree(out_dir)
            if got["files"]:
                ok = not got["issues"]
                return {
                    "ran": True, "success": ok, "rung": got["rung"],
                    "issues": got["issues"],
                    "message": (f"{got['files']} generated Java file(s) parse and every "
                                "type resolves. No compiler ran — a licensed SAP "
                                "Commerce platform is item 3.11."
                                if ok else
                                f"{len(got['issues'])} static problem(s) in "
                                f"{got['files']} generated Java file(s)."),
                }

        return {
            "ran": False,
            "success": False,
            # Not "we did not verify" — "verification is not available here". The rung
            # ladder exists so those two stop sharing a word. [3.9]
            "rung": assurance.NONE,
            "message": ("SAP Commerce has no hosted compile oracle. Generated Java is "
                        "statically checked, not verified, until a licensed platform is "
                        "available (items 3.10–3.12)."),
        }

    def symbols(self, code: str) -> list:
        """Generated Java method declarations, for provenance. [2.11]"""
        from src.adapters.braced_symbols import symbols as _s
        return _s(code)

    def find_method(self, code: str, name: str) -> dict | None:
        raise NotImplementedYet("Locating a method in generated Java", "3.11")

    def emit_characterization(self, runnable_by_target: dict) -> dict:
        raise NotImplementedYet("Emitting JUnit characterization tests", "3.11")

    def literal(self, value: dict | None) -> str | None:
        raise NotImplementedYet("Rendering a recorded value as a Java literal", "3.11")

    def bridge_request(self, target: str, code: str, rows: list) -> dict:
        raise NotImplementedYet("Bridging reshaped calls onto Java", "3.11")

ADAPTER = HybrisTarget()
