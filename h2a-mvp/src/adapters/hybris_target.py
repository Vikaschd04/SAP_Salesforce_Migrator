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
    #: The target assembles a whole extension — skeleton, items.xml, services, DAOs,
    #: jobs, decorators, interceptors, event listeners, configuration and wiring — and
    #: checks it at the `static` rung: every file parses and every type it names resolves.
    #:
    #: This was false until 1.34, for two reasons that have both been answered. The first
    #: was the prompt pack (3.8), without which method bodies would all have been
    #: `UnsupportedOperationException`; that shipped. The second was that three kinds had
    #: no emitter, so a run converted a third of its units — which the ledger reported
    #: honestly, but a truthful thin migration is still a thin migration.
    #:
    #: What it still does not do is *verify*. See `has_oracle`: an Adobe→Hybris run is
    #: statically checked, never compiled, and the sign-off says so in those words. That
    #: is a property of the platform, not a gap in this flag — and `implemented` means
    #: "can run a migration", not "can prove one".
    implemented = True

    #: No free compile oracle. See the module docstring — this is honest, not pending.
    has_oracle = False
    code_language = "Java"
    #: See `SalesforceTarget.retrieval_terms`. These name what the Adobe→Hybris
    #: pack actually documents: the type system, the query language, the two hook
    #: mechanisms and the scheduler. [1.48]
    def contract_for(self, plan_item, source_units: list) -> str:
        """What the emitter will write for this target, for the Builder's prompt.

        On the adapter because it is knowledge about *this platform's* class shapes,
        and the Builder must stay ignorant of which platform it is building for.
        [1.51]
        """
        methods = []
        for u in source_units or []:
            methods += list(getattr(u, "methods", None) or [])
        return target_contract(getattr(plan_item, "kind", ""),
                               getattr(plan_item, "target_name", ""), methods)

    retrieval_terms = ("hybris service layer spring bean flexiblesearch interceptor "
                       "decorator cronjob performable items.xml model impex")

    #: Nothing to query before generating — an extension is built from source. [1.33]
    has_org = False

    def plan(self, units: list, config: dict) -> list:
        """What Hybris builds from these units, with the reason for each choice. [3.2b]

        `config["wiring"]` carries the di.xml reading when there is one; without it a
        plugin cannot be classified and routes to the safe superset. See hybris_plan.

        The protocol passes units as *dicts* — the wire format the pipeline uses — while
        `hybris_plan` reads them as objects. That mismatch made the whole pipeline
        unrunnable at the Planner, so normalise here exactly as the Salesforce target
        normalises in the other direction. [1.33]
        """
        from src.adapters.hybris_plan import plan_targets
        from src.ir import SourceUnit
        units = [u if hasattr(u, "name") else SourceUnit.from_dict(u)
                 for u in (units or [])]
        return plan_targets(units, (config or {}).get("wiring"),
                            (config or {}).get("routes"))

    def schema(self, item_types: list, relations: list, enum_types: list) -> dict:
        """The `items.xml` type model, in the shape everything downstream reads. [1.33]

        Objects with fields — the one shape both platforms share — so the same prompt
        grounding, the same validation and the same reports work without knowing which
        platform produced it. The Java types here are what `items.xml` will declare, so a
        model grounded on this schema is grounded on what is actually emitted.
        """
        from src.adapters.hybris_extension import java_type, pascal

        out: dict = {}
        for dt in (item_types or []):
            d = dt.to_dict() if hasattr(dt, "to_dict") else dict(dt or {})
            code = d.get("code") or d.get("name")
            if not code:
                continue
            fields = {}
            for a in (d.get("attributes") or d.get("fields") or []):
                a = a if isinstance(a, dict) else {}
                nm = a.get("name")
                if not nm:
                    continue
                fields[pascal(nm)] = java_type(a.get("type") or "")
            out[code] = {"code": code, "fields": fields, "picklists": {},
                         "open_picklists": set(), "name_notes": [], "localized": set(),
                         "field_api": {}, "required": set(), "unique": set(),
                         "defaults": {}}
        return out

    def reconcile(self, schema: dict, prelim: dict, corpus: str) -> tuple:
        """No reconciliation without a compiler. [1.33]

        The Salesforce path mines *validation failures* for field references that must
        exist, and those come from a real deploy. Static parsing cannot tell a missing
        field from a field on a platform type this extension does not declare, so
        inventing attributes from generated Java would add to `items.xml` on a guess.
        Returns the schema untouched, and says that is what happened rather than
        reporting a clean reconciliation that never ran.
        """
        return schema, {"added_fields": [], "added_objects": [], "ran": False,
                        "note": ("No schema reconciliation: it needs a compiler's view of "
                                 "which references fail, and this target has none until "
                                 "item 3.11.")}

    def emit_schema(self, output_dir: str, schema: dict) -> list:
        """Nothing separate to write — `items.xml` is part of the extension. [1.33]

        `emit` already wrote it via `hybris_extension.build_extension`. Writing it again
        here would produce a second, competing copy of the data model.
        """
        return []

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

        # `plan` arrives as PlanItem objects; `hybris_emit` reads the dict rows this
        # adapter's own `plan()` produced. Same normalisation as `plan()`, in the other
        # direction. [1.33]
        plan_rows = []
        for item in (cfg.get("plan") or []):
            if isinstance(item, dict):
                plan_rows.append(item)
                continue
            plan_rows.append({
                "target_name": getattr(item, "target_name", ""),
                "kind": getattr(item, "kind", "") or "",
                "layer": getattr(item, "layer", ""),
                "rationale": getattr(item, "rationale", ""),
                "source_classes": list(getattr(item, "source_classes", []) or []),
            })

        # The Builder's Java, keyed the way the plan names targets. `emit()` has always
        # received these and, until 1.48, passed none of them on. [1.48]
        generated = {}
        for a in artifacts or []:
            row = a if isinstance(a, dict) else getattr(a, "to_generated_dict", dict)()
            if row.get("target_name") and row.get("main_class"):
                generated[row["target_name"]] = row["main_class"]

        result = emit_extension(
            output_dir,
            name=cfg.get("extension_name", "migrated"),
            package=cfg.get("package", "com.migrated"),
            source_model=source_model,
            targets=plan_rows,
            generated=generated,
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


def target_contract(kind: str, target_name: str, source_methods: list) -> str:
    """The class and methods the emitter will write, told to the Builder. [1.51]

    The merge that lands generated logic in the emitted file is keyed by method name, and
    for three runs it matched almost nothing — because nobody had told the model what to
    name anything. It was asked to migrate a PHP class and left to guess the target's
    shape, so a job came back with `execute`, a listener with `perform`, an interceptor
    with `onValidate` where the emitter had derived `onPrepare`. Real logic, written well,
    discarded on arrival for wearing the wrong name.

    Guessing was never the model's job. The emitter *knows* the answer — it is about to
    write the file — and had simply never said so. Everything below is derived from the
    same helpers the emitters call, so the contract cannot drift from what is emitted.
    """
    from src.adapters import hybris_hooks
    from src.adapters.hybris_plan import (CONTROLLER, DECORATOR, EVENT_LISTENER,
                                          INTERCEPTOR, JOB, SERVICE)
    from src.adapters.hybris_service import _camel

    names = [getattr(m, "name", "") for m in (source_methods or [])
             if getattr(m, "name", "")]

    if kind == JOB:
        body = [f"- Write `public class {target_name} extends "
                "AbstractJobPerformable<CronJobModel>`.",
                "- Put the logic in `public PerformResult perform(final CronJobModel "
                "cronJob)`. That is the platform's entry point and the only method that "
                "runs; a method named after the PHP one will never be called.",
                "- Return `new PerformResult(CronJobResult.SUCCESS, "
                "CronJobStatus.FINISHED)` on success."]
    elif kind == EVENT_LISTENER:
        body = [f"- Write `public class {target_name} extends AbstractEventListener<E>`, "
                "where `E` is the event type.",
                "- Put the logic in `protected void onEvent(final E event)`. That is the "
                "platform's entry point — a method named after the PHP observer will "
                "never be called."]
    elif kind == INTERCEPTOR:
        # Derived by the same function the emitter uses, from the same method names, so
        # the contract cannot name a hook the emitted class does not declare.
        shim = type("U", (), {"methods": list(source_methods or [])})()
        hook = hybris_hooks.interceptor_hook(shim)
        kindname = hybris_hooks._interceptor_shape(shim)[0]
        body = [f"- Write `public class {target_name} implements {kindname}`.",
                f"- Put the logic in `public void {hook}(final Object model, final "
                "InterceptorContext ctx) throws InterceptorException`.",
                f"- Use `{hook}` and no other hook. Which one this is was derived from "
                "the plugin's own prefix; moving logic to a different hook changes when "
                "it runs and whether it can reject the model."]
    elif kind == DECORATOR:
        emitted = [hybris_hooks.wrapped_method(n) for n in names]
        body = [f"- Write `public class {target_name}`.",
                "- One method per plugin method, named exactly: "
                + (", ".join(f"`{e}`" for e in emitted) or "(none)") + ".",
                "- Each takes `(final Object... args)` and returns `Object`."]
    elif kind == CONTROLLER:
        body = [f"- Write `public class {target_name}` — an OCC REST controller.",
                "- One method, named for the action, taking "
                "`(@PathVariable String baseSiteId, @RequestParam String code)` and "
                "returning the `WsDTO` named in the file.",
                "- The route, the HTTP verb and the class name are already decided and "
                "written; do not restate them.",
                "- Translate what the Magento action *did* — the reads, the writes, the "
                "validation. It ended by rendering a page, and this returns a DTO "
                "instead: map what the page would have shown, and say in a comment where "
                "you had to choose."]
    elif kind == SERVICE:
        emitted = [_camel(n) for n in names]
        body = [f"- Write the **implementation**, `public class {target_name}`. The "
                "interface is derived from the source and you do not need to write it.",
                "- Implement exactly these methods: "
                + (", ".join(f"`{e}`" for e in emitted) or "(none)") + ".",
                "- Keep the parameter order; the types are fixed by the interface."]
    else:
        return ""

    return "\n".join([
        "## The class this becomes",
        "",
        "The migration writes this file and merges your method bodies into it **by "
        "method name**. A body under a name that is not listed here is discarded — not "
        "because it is wrong, but because there is nowhere for it to go.",
        "", *body,
        "",
        "Anything you cannot migrate faithfully: say so in a comment and leave the "
        "method unfinished. An honest gap is reviewable; an invented one is not.",
    ])
