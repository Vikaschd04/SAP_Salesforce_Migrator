"""
hybris_plan.py — what each Magento unit becomes on SAP Hybris. [3.2b]

The routing decision, made once and recorded with its reason. Until this existed every
unit rendered as a service, which is right for a Model and wrong for everything Magento
uses to *intercept* behaviour — and a plugin quietly emitted as a service is a plugin that
never runs.

**The decision this module exists for.** A Magento `around` plugin may decline to call
`$proceed`, so the original method never executes. A Hybris interceptor cannot do that: it
runs alongside an operation, it cannot replace one. So an around plugin that can skip must
become a **decorator bean** — a Spring bean registered in place of the original, which owns
the decision to delegate.

Getting it wrong produces code that always calls through. It compiles, it deploys, nothing
in review looks odd, and a business rule that used to be able to short-circuit an order
total silently stops being able to.

**When we cannot tell, we choose the superset.** A decorator can express everything an
interceptor can *and* skipping; an interceptor cannot express skipping. So an unclassified
plugin routes to a decorator with the reason recorded, because the failure directions are
not symmetric: an unnecessary decorator is more ceremony than needed, and a missing one is
a rule that stopped working.
"""

from __future__ import annotations

from src.adapters.hybris_extension import pascal
from src.adapters.hybris_service import service_name

#: Hybris artifact kinds this planner routes to.
SERVICE = "service"
DAO = "dao"
INTERCEPTOR = "interceptor"
DECORATOR = "decorator"
EVENT_LISTENER = "event-listener"
JOB = "job"
DATA = "data"
MANUAL = "manual"

#: Magento layer → (kind, reason). Layers needing a *decision* are not in here; they are
#: handled below where the decision can be explained.
_BY_LAYER = {
    "Model": (SERVICE, "a Magento model holds business logic; on Hybris that is a "
                       "Spring service with an interface and a Default implementation"),
    "Api": (SERVICE, "an interface in Magento's Api/ is the published contract, which is "
                     "exactly what a Hybris service interface is"),
    "DAO": (DAO, "a ResourceModel is data access; on Hybris that is a DAO issuing "
                 "FlexibleSearch"),
    "Helper": (SERVICE, "a helper is logic without a home; a service gives it one"),
    "Cron": (JOB, "a crontab job becomes an AbstractJobPerformable plus a cron trigger — "
                  "and Hybris needs explicit node affinity, because a Magento job runs "
                  "once per cluster and a Hybris one runs per node"),
    "Observer": (EVENT_LISTENER, "an observer becomes an event listener — but Magento "
                                 "dispatches synchronously and in order and Hybris "
                                 "EventService does neither by default, so the listener "
                                 "has to be made synchronous explicitly or the ordering "
                                 "has to stop mattering"),
    "Setup": (DATA, "a data patch is data, not code: EAV attributes become items.xml "
                    "declarations and seed rows become ImpEx"),
    "Trait": (MANUAL, "a trait mixes implementation into a class; Java has single "
                      "inheritance and no equivalent, so this is composition or a base "
                      "class, and which one is a judgement"),
    "View": (MANUAL, "Magento layout and templates have no Hybris equivalent that can be "
                     "derived — Spartacus composes pages from CMS components"),
    "Controller": (SERVICE, "a controller's logic moves to a service; the endpoint itself "
                            "is a separate decision about the storefront"),
}

#: Never planned. Each is a positive statement, not an omission.
_NOT_PLANNED = {
    "Test": "held aside as recorded behaviour for characterization, never migrated",
    "Script": "no class in the file — registration or configuration, not migratable code",
}


def _plugin_route(unit, wiring: dict | None) -> tuple:
    """An around plugin that can skip `$proceed` needs a decorator, not an interceptor."""
    plugins = (wiring or {}).get("plugins") or []
    fqn = (getattr(unit, "extra", None) or {}).get("fqn", "")
    mine = [p for p in plugins
            if p.get("type") == fqn or p.get("type", "").endswith(f"\\{unit.name}")]

    if any(p.get("can_skip_original") is True for p in mine):
        return DECORATOR, ("this `around` plugin returns without calling $proceed on at "
                           "least one path. A Hybris interceptor runs alongside an "
                           "operation and cannot replace one, so an interceptor here "
                           "would always call through and silently lose the "
                           "short-circuit. A decorator bean owns that decision")
    if mine and all(p.get("can_skip_original") is False for p in mine):
        return INTERCEPTOR, ("this plugin always proceeds, so an interceptor expresses "
                             "it — before/after map onto Prepare and Validate")
    return DECORATOR, ("this plugin could not be classified — its class was not readable, "
                       "or no di.xml wiring was supplied. A decorator is the safe choice: "
                       "it can express everything an interceptor can and also skipping, "
                       "while an interceptor cannot express skipping, so the two failure "
                       "directions are not symmetric")


def plan_targets(units: list, wiring: dict | None = None) -> list:
    """`[{target_name, kind, layer, rationale, source_classes}]`, one per unit.

    Every unit that is not planned is returned in `skipped` by `plan_report`, with a
    reason — a unit that appears in neither list is a unit lost, which is the thing the
    completeness ledger exists to make impossible.
    """
    out = []
    for u in units or []:
        layer = getattr(u, "layer", "") or ""
        if layer in _NOT_PLANNED:
            continue

        if layer == "Plugin":
            kind, why = _plugin_route(u, wiring)
        elif layer in _BY_LAYER:
            kind, why = _BY_LAYER[layer]
        else:
            kind, why = (MANUAL, "no layer could be inferred from the file's location, so "
                                 "what this unit *is* was never established — guessing a "
                                 "target from its name would be a guess about behaviour")

        out.append({
            "target_name": _name_for(u, kind),
            "kind": kind,
            "layer": layer,
            "rationale": why,
            "source_classes": [{"class_name": u.name, "layer": layer,
                                "source": getattr(u, "source", ""),
                                "file": getattr(u, "file", ""),
                                # Two classes with the same short name are only telling
                                # apart by where they live. [1.40]
                                "namespace": (getattr(u, "extra", None) or {})
                                .get("namespace", "")}],
        })
    return _merge(out)


def _merge(targets: list) -> list:
    """Fold targets that name the same artifact, keeping every source class.

    A dropped half is how a contract and its implementation get separated: the interface
    would be planned, the class would not, and the ledger would carry an `unaccounted`
    row for a perfectly ordinary pairing. The Salesforce planner learned this the same
    way, on Hybris facades.
    """
    by_key: dict = {}
    for t in targets:
        key = (t["target_name"], t["kind"])
        if key in by_key:
            existing = by_key[key]
            existing["source_classes"] += t["source_classes"]
            if t["rationale"] not in existing["rationale"]:
                existing["rationale"] += f"; also {t['rationale']}"
        else:
            by_key[key] = t
    return _disambiguate(list(by_key.values()))


def _disambiguate(targets: list) -> list:
    """Two source classes with the *same short name* are not the same class. [1.40]

    Folding is right for `PricingServiceInterface` and `PricingService`: one contract in
    two files, which is how Magento spells what Hybris spells as an interface plus a
    Default implementation. Those have *different* names that collapse to one target, and
    they stay folded.

    It is wrong for `Controller\\Adminhtml\\Index\\Index`, `Controller\\Customer\\Index` and
    `Controller\\Index\\Index` — three unrelated controllers all literally called `Index`,
    which a real third-party module has and a hand-written fixture does not. Folded, all
    three were reported as converted into one `IndexService` and two of them were not in
    it.

    So the discriminator is not the namespace — the interface and its implementation live
    in different namespaces too — but whether the short names are *identical*. Where they
    are, the extra ones are split out and named for the namespace segment that tells them
    apart.
    """
    out = []
    for t in targets:
        classes = t.get("source_classes", []) or []
        seen: dict = {}
        for c in classes:
            seen.setdefault(c.get("class_name", ""), []).append(c)
        duplicated = {n for n, group in seen.items() if len(group) > 1}
        if not duplicated:
            out.append(t)
            continue

        # The first of each duplicated name keeps the plain target; the rest are split
        # out. Anything not duplicated stays with the first, so an interface and its
        # implementation are never separated by this.
        namespaces = [c.get("namespace", "") for n in duplicated for c in seen[n]]
        primary, extras = [], []
        for name, group in seen.items():
            if name in duplicated:
                primary.append(group[0])
                extras.extend(group[1:])
            else:
                primary.extend(group)

        head = dict(t)
        head["source_classes"] = primary
        out.append(head)

        taken = {t["target_name"]}
        for c in extras:
            qualifier = _distinguishing_segment(c.get("namespace", ""), namespaces)
            copy = dict(t)
            copy["source_classes"] = [c]
            # `...\\Controller\\Index` yields the qualifier `Index`, and `IndexService`
            # already starts with it — so the "already qualified" shortcut handed back
            # the primary's own name and the two re-folded downstream, putting us back
            # where we started. Uniqueness is checked, not assumed. [1.40]
            candidate = (f"{pascal(qualifier)}{t['target_name']}"
                         if qualifier and not t["target_name"].startswith(pascal(qualifier))
                         else t["target_name"])
            if candidate in taken:
                segments = [s for s in (c.get("namespace", "") or "").split("\\") if s]
                candidate = f"{''.join(pascal(s) for s in segments[-2:])}{t['target_name']}"
            taken.add(candidate)
            copy["target_name"] = candidate
            copy["rationale"] = (
                t["rationale"] + f"; named for `{qualifier}`, because more than one source "
                "class is called this and they are different classes")
            out.append(copy)
    return out


def _distinguishing_segment(ns: str, all_ns: list) -> str:
    """The first namespace segment that tells `ns` apart from its siblings.

    The *last* segment is not it: `...\\Controller\\Adminhtml\\Index` and
    `...\\Controller\\Index` both end in `Index`, so naming by it would leave the
    collision exactly where it was.
    """
    parts = [n.split("\\") for n in all_ns if n]
    mine = ns.split("\\") if ns else []
    if not mine:
        return ""
    if len(parts) < 2:
        return mine[-1]
    common = 0
    for i in range(min(len(p) for p in parts)):
        if len({p[i] for p in parts}) == 1:
            common = i + 1
        else:
            break
    return mine[common] if common < len(mine) else mine[-1]


def _name_for(unit, kind: str) -> str:
    # Magento's `PricingServiceInterface` and its `PricingService` implementation are one
    # contract in two files. Hybris spells that pair `PricingService` + the Default impl,
    # so both source units name the *same* target — and `_merge` folds them together.
    # Left alone they produced `PricingServiceInterfaceService` beside `PricingService`:
    # two services for one logical service, with the contract in the wrong one.
    base = unit.name
    if base.endswith("Interface") and len(base) > len("Interface"):
        base = base[: -len("Interface")]
    n = pascal(base)
    if kind == SERVICE:
        # `service_name` strips the suffix itself now, so both this and the emitters
        # derive the same name from the same input rather than agreeing by luck. [1.38]
        return service_name(unit.name)
    if kind == DAO:
        return f"{n}Dao"
    if kind == INTERCEPTOR:
        return f"{n}Interceptor" if not n.endswith("Interceptor") else n
    if kind == DECORATOR:
        return f"{n}Decorator" if not n.endswith("Decorator") else n
    if kind == EVENT_LISTENER:
        return f"{n}Listener" if not n.endswith("Listener") else n
    if kind == JOB:
        return f"{n}JobPerformable"
    return n


def plan_report(units: list, wiring: dict | None = None) -> dict:
    """Planned targets *and* what was deliberately not planned, with reasons."""
    planned = plan_targets(units, wiring)
    skipped = [{"source": u.name, "layer": getattr(u, "layer", ""),
                "reason": _NOT_PLANNED[getattr(u, "layer", "")]}
               for u in (units or []) if getattr(u, "layer", "") in _NOT_PLANNED]
    # Count *source units represented*, not targets. Merging an interface with its
    # implementation makes one target from two units, so counting targets understated the
    # total and would have reported a complete plan as incomplete — or, with a different
    # merge, an incomplete one as complete.
    represented = {c["class_name"] for t in planned for c in t["source_classes"]}
    represented |= {s["source"] for s in skipped}
    return {"targets": planned, "skipped": skipped,
            "accounted": len(represented),
            "unaccounted": sorted({getattr(u, "name", "") for u in (units or [])}
                                  - represented)}
