"""Angular constructs LWC has no equivalent for, and what each one costs. [1.24, D1-D4]

The frontend path refuses more honestly than the backend one did, but it still carried a
blanket instruction in the generator's system prompt:

    RxJS Observable/subscribe -> reactive property / @wire

That is confidently wrong in the two cases that matter. `@wire` is push-based but it is
*not composable* — you cannot combine two wires into a third — and it cannot be driven by
a timer at all. A component that polls with `interval().pipe(switchMap(...))` translated
to `@wire` compiles, deploys, renders, and never polls. Nothing in the output says so.

The same shape as the `TRANSACTIONAL` rule removed in 1.21c: one mapping given for a
construct that has several, and the common case getting the wrong one.

This module decides per construct. It reports what does not survive, and grounds the
generator so the model is told rather than left to guess. Three things drive the cost:

**Cancellation.** `switchMap` cancels the request in flight when a new value arrives. An
imperative Apex call in LWC returns a promise nobody can cancel, so responses race and a
slow earlier one lands on top of a fast later one.

**Teardown.** An Angular subscription ends with the component. A `setInterval` does not —
it keeps calling Apex after the component is gone, and in LWC a component is destroyed on
every navigation.

**Composition.** `combineLatest`, `forkJoin` and named slot selectors are all ways of
assembling something out of parts, and LWC's equivalents are not assemblable in the same
way. These need a different shape, not a translation.
"""

from __future__ import annotations

import re

#: RxJS operators and what each one is actually doing for the component. The `fix` is the
#: shape that preserves the behaviour, not the shape that merely compiles.
_RX = {
    "switchMap": ("high",
        "`switchMap` cancels the request in flight when a new value arrives. An imperative "
        "Apex call in LWC returns a promise that cannot be cancelled, so a slow earlier "
        "response can resolve after a fast later one and overwrite fresher data with "
        "staler data — intermittently, and usually not on the developer's machine.",
        "Guard the assignment with a sequence token: `const seq = ++this._seq;` before the "
        "call, and `if (seq === this._seq)` inside `.then()` before assigning. The request "
        "still completes — nothing can stop it — but its result is discarded."),
    "mergeMap": ("medium",
        "`mergeMap` runs requests concurrently and lets every result through, in whatever "
        "order they return. Nothing about that is preserved by awaiting one call.",
        "Fire the calls together and gather them with `Promise.all` if all results are "
        "wanted, and add a sequence guard if only the newest is."),
    "flatMap": ("medium",
        "`flatMap` is `mergeMap` under its older name: concurrent, unordered, uncancelled.",
        "Fire the calls together and gather them with `Promise.all`, or add a sequence "
        "guard if only the newest result should be shown."),
    "concatMap": ("medium",
        "`concatMap` queues requests and preserves their order. Concurrent promises do not "
        "queue, so results can be applied out of the order they were requested.",
        "Chain the promises deliberately — `this._chain = this._chain.then(...)` — or await "
        "each call before starting the next."),
    "exhaustMap": ("medium",
        "`exhaustMap` ignores new values while a request is in flight. That is what stops a "
        "double-click submitting twice; a plain call handler does not.",
        "Keep an `_inFlight` flag, return early while it is set, and clear it in a "
        "`finally`."),
    "combineLatest": ("high",
        "`combineLatest` emits whenever *either* source emits, using the latest of both. "
        "`@wire` is push-based but not composable — two wires cannot be combined into a "
        "third — so this has no direct translation.",
        "Prefer one Apex method returning the combined shape: it is one round trip instead "
        "of two and the coordination disappears. If both must stay separate, assign each "
        "to its own property and compute the result in a getter that returns undefined "
        "until both have arrived."),
    "forkJoin": ("medium",
        "`forkJoin` waits for every source to complete and emits once. A `@wire` never "
        "completes, so there is nothing to join.",
        "Call the methods imperatively and use `Promise.all`, which is the same shape."),
    "withLatestFrom": ("medium",
        "`withLatestFrom` samples another stream's most recent value at the moment this one "
        "emits. There is no LWC equivalent because there is no stream to sample.",
        "Keep the other value in a property as it arrives and read the property at the "
        "point the first call resolves."),
    "zip": ("medium",
        "`zip` pairs emissions by index, waiting for both. Promises have no index to pair on.",
        "Use `Promise.all` if the pairing is really 'wait for both', or restructure so one "
        "Apex call returns the pair."),
    "debounceTime": ("high",
        "`debounceTime` is what stops a keystroke handler calling the server on every "
        "letter. Dropped, the component still works and quietly multiplies its callout "
        "count — against a governor limit, and against the user's own typing speed.",
        "`clearTimeout(this._t); this._t = setTimeout(() => ..., ms);` in the handler, and "
        "`clearTimeout(this._t)` in `disconnectedCallback`."),
    "throttleTime": ("medium",
        "`throttleTime` caps how often the handler runs. Dropped, it runs every time.",
        "Record the last-run timestamp and return early inside the window."),
    "distinctUntilChanged": ("medium",
        "`distinctUntilChanged` suppresses a repeat of the same value, so an unchanged "
        "input does not trigger another call.",
        "Compare against the previous value and return early when it is unchanged. This "
        "matters more in LWC, where a setter can fire for an identical value."),
    "shareReplay": ("medium",
        "`shareReplay` gives every subscriber one shared request and replays its result. "
        "Without it each consumer calls the server again.",
        "Cache the promise itself in a property and return the same promise to every "
        "caller, or use `@wire(...)` with `cacheable=true` so the platform caches it."),
    "interval": ("high",
        "`interval` polls. `@wire` cannot be driven by a timer and will not poll, so a "
        "component translated to `@wire` renders once, looks correct, and never updates. "
        "The timer also has to be torn down: in LWC a component is destroyed on every "
        "navigation, and a surviving `setInterval` keeps calling Apex for the rest of the "
        "session.",
        "`this._timer = setInterval(...)` in `connectedCallback`, and "
        "`clearInterval(this._timer)` in `disconnectedCallback`. The teardown is not "
        "optional."),
    "timer": ("high",
        "`timer` schedules work, and like any timer in LWC it outlives the component unless "
        "it is cleared — a component is destroyed on every navigation.",
        "`setTimeout`/`setInterval` in `connectedCallback`, cleared in "
        "`disconnectedCallback`."),
    "retry": ("medium",
        "`retry` re-subscribes on failure, which re-issues the request. A rejected promise "
        "does not retry itself.",
        "Wrap the call in a function and re-invoke it from `.catch()` with a bounded "
        "attempt count — and remember each attempt spends a callout."),
    "retryWhen": ("medium",
        "`retryWhen` re-issues the request on a schedule the stream defines.",
        "Re-invoke the call from `.catch()` with an explicit attempt count and delay."),
    "catchError": ("high",
        "`catchError` returning `of(value)` is not an error path — it substitutes a value "
        "and the stream continues, so the component renders the fallback. Translated as a "
        "thrown error, the component shows an error state where Angular showed data.",
        "`.catch(() => { /* assign the same fallback */ })`. Read what the operator "
        "returns: `of(null)` means the template's null branch, not an error banner."),
    "takeUntil": ("medium",
        "`takeUntil(destroy$)` is the teardown idiom — it ends every subscription when the "
        "component goes away.",
        "Whatever it was ending (timers, listeners) must be undone in "
        "`disconnectedCallback` instead."),
}

_RX_RE = {name: re.compile(rf"\b{name}\s*\(") for name in _RX}

#: Angular template pipes. LWC has no pipe syntax at all, and the generator's standing
#: instruction — lift it into a getter — is right for `uppercase` and quietly wrong for
#: anything locale-aware, where a getter returns an unformatted value that still renders.
_PIPES = {
    "async": ("high",
        "`| async` subscribes to an observable and renders its value. LWC has no async "
        "pipe. Bound literally, `{breakdown$}` renders the object itself.",
        "Resolve the value in JS and bind a plain property the template can read; assign it "
        "when the promise settles."),
    "currency": ("high",
        "`| currency` formats money for the active locale. A getter returning the raw "
        "number still renders — as `1234.5` where the shopper expects `$1,234.50`.",
        "`<lightning-formatted-number format-type=\"currency\" currency-code=\"USD\" "
        "value={x}>`. The currency code was implicit in Angular's LOCALE_ID and has to "
        "come from somewhere explicit now."),
    "date": ("high",
        "`| date` formats for the active locale and time zone. A raw getter renders an ISO "
        "string, or a Unix number, without failing.",
        "`<lightning-formatted-date-time value={x}>`, which uses the running user's locale "
        "and time zone."),
    "number": ("medium",
        "`| number` applies digit grouping and precision. Dropped, the value still renders, "
        "ungrouped and at full precision.",
        "`<lightning-formatted-number value={x}>`."),
    "percent": ("medium",
        "`| percent` multiplies by 100 and appends the sign. A getter that only formats "
        "will be out by a factor of 100.",
        "`<lightning-formatted-number format-type=\"percent\" value={x}>`."),
    "json": ("medium",
        "`| json` is a debugging pipe. If it reached production markup it is worth asking "
        "whether the binding was ever finished.",
        "Bind the specific fields the template needs."),
    "uppercase": ("medium",
        "`| uppercase` has no LWC equivalent, but it is safe in a getter or in CSS.",
        "A getter returning `x.toUpperCase()`, or `text-transform: uppercase` in the CSS."),
    "lowercase": ("medium",
        "`| lowercase` has no LWC equivalent, but it is safe in a getter or in CSS.",
        "A getter returning `x.toLowerCase()`, or `text-transform: lowercase` in the CSS."),
    "titlecase": ("medium",
        "`| titlecase` has no LWC equivalent and no CSS equivalent that matches its rules.",
        "A getter that applies the same casing rules explicitly."),
    "slice": ("medium",
        "`| slice` truncates in the template, where LWC allows no expressions.",
        "A getter returning the sliced value."),
}

_PIPE_RE = re.compile(r"\|\s*(" + "|".join(_PIPES) + r")\b")

# `<ng-content select="...">` — LWC named slots match on a `slot` attribute, never a
# CSS selector, so this cannot be expressed at all without changing every consumer.
_NG_CONTENT_SELECT = re.compile(r"<ng-content[^>]*\bselect\s*=\s*[\"']([^\"']+)[\"']")

# `*ngIf="c; else tpl"` and the `<ng-template #tpl>` it names.
_NGIF_ELSE = re.compile(r"\*ngIf\s*=\s*[\"'][^\"']*;\s*else\s+(\w+)")

# Two-way binding. [D1]
_NGMODEL = re.compile(r"\[\(ngModel\)\]")

# CMS-driven instantiation. [D4]
_CMS = {
    "cmsComponents": "Spartacus resolves a component from a CMS type name at runtime.",
    "ComponentMapping": "Spartacus resolves a component from a CMS type name at runtime.",
    "ComponentFactoryResolver": "Angular builds a component type chosen at runtime.",
    "ViewContainerRef": "Angular inserts a component chosen at runtime into a view.",
    "createComponent": "Angular instantiates a component chosen at runtime.",
}
_CMS_RE = {name: re.compile(rf"\b{name}\b") for name in _CMS}

_CMS_HAZARD = (
    "LWC has no general runtime instantiation. `lwc:component` with `lwc:is` still needs a "
    "constructor that was imported statically, so a type name arriving from the CMS cannot "
    "be resolved to a module. The set of components is fixed when the bundle is built — "
    "which is the opposite of what a CMS is for."
)
_CMS_FIX = (
    "Build an explicit registry mapping each CMS type name to a statically imported "
    "constructor, and render through `lwc:component`/`lwc:is`. Every type the CMS may "
    "return has to be in that registry at build time; anything else renders nothing. "
    "Decide up front which types are in scope and say so — this is the one place where a "
    "faithful port is not available and the design has to change."
)

# Calling a lifecycle hook by hand. Legal in Angular, a defect in LWC.
_MANUAL_HOOK = re.compile(r"\bthis\.(ngOnInit|ngOnDestroy|ngAfterViewInit|ngOnChanges)\s*\(")


def _lines(text: str) -> list[str]:
    return (text or "").splitlines()


def _hit(kind, name, severity, hazard, fix, line, snippet, origin) -> dict:
    """`origin` is which file the line number belongs to — the component's TypeScript or
    its template. Without it a template finding is reported at that line of the `.ts`,
    which points at whatever happens to be there."""
    return {"kind": kind, "construct": name, "severity": severity, "hazard": hazard,
            "fix": fix, "line": line, "origin": origin,
            "snippet": (snippet or "").strip()[:120]}


def analyse(source: str, template: str = "") -> list[dict]:
    """Every construct in this component that LWC cannot carry across as written.

    `source` is the component's TypeScript, `template` its HTML. Each row is
    `{kind, construct, severity, hazard, fix, line, snippet}`.
    """
    out: list[dict] = []

    for n, line in enumerate(_lines(source), 1):
        for name, rx in _RX_RE.items():
            if rx.search(line):
                sev, hazard, fix = _RX[name]
                out.append(_hit("rxjs", name, sev, hazard, fix, n, line, "source"))
        for name, rx in _CMS_RE.items():
            if rx.search(line):
                out.append(_hit("cms", name, "high", f"{_CMS[name]} {_CMS_HAZARD}",
                                _CMS_FIX, n, line, "source"))
        m = _MANUAL_HOOK.search(line)
        if m:
            hook = m.group(1)
            out.append(_hit(
                "lifecycle", hook, "medium",
                f"`{hook}()` is called by hand. Angular tolerates it; LWC's "
                "`connectedCallback` is meant to run once, and re-running it re-registers "
                "whatever it set up — listeners, timers, in-flight calls — with nothing "
                "removing the previous registration.",
                "Move the body into a named method and call that from both the lifecycle "
                "hook and the place that wants to re-run it.", n, line, "source"))

    for n, line in enumerate(_lines(template), 1):
        for name in set(_PIPE_RE.findall(line)):
            sev, hazard, fix = _PIPES[name]
            out.append(_hit("pipe", name, sev, hazard, fix, n, line, "template"))
        for sel in _NG_CONTENT_SELECT.findall(line):
            out.append(_hit(
                "slot", sel, "high",
                f"`<ng-content select=\"{sel}\">` projects whichever children match a CSS "
                "selector. LWC named slots match only on a `slot` attribute the consumer "
                "puts on the child, so this selector has no equivalent — and the failure "
                "is silent: the slot simply renders empty.",
                f"`<slot name=\"{re.sub(r'[^A-Za-z0-9]+', '-', sel).strip('-') or 'content'}\">`, "
                "and every consumer of this component must add the matching `slot=` "
                "attribute to its children. The consumers change too, so find them before "
                "this is called done.", n, line, "template"))
        for tpl in _NGIF_ELSE.findall(line):
            out.append(_hit(
                "control-flow", tpl, "medium",
                f"`*ngIf` with an `else {tpl}` branch renders a named `<ng-template>`. LWC "
                "has no template references.",
                "`<template lwc:if={c}>` followed by `<template lwc:else>` holding what "
                f"`{tpl}` held. Both branches must be inlined where they are used.",
                n, line, "template"))
        if _NGMODEL.search(line):
            out.append(_hit(
                "binding", "ngModel", "high",
                "`[(ngModel)]` is two-way. LWC has no two-way binding: the value flows down "
                "and nothing carries it back, so the field renders, accepts typing, and "
                "never updates the property behind it.",
                "`value={x}` plus `onchange={handleX}`, where the handler assigns "
                "`this.x = event.target.value`. Without the handler this fails silently.",
                n, line, "template"))

    return out


def findings(source: str, template: str, rel: str, cls: str,
             template_rel: str = "") -> list[dict]:
    """Report rows, in the shape the radar uses for the backend. [1.24]

    One row per construct per file, not per occurrence. Six `currency` pipes in one
    template are one decision to make and one fix to apply; listing them six times pads
    the report and buries the rest.
    """
    rows: dict[tuple, dict] = {}
    for g in analyse(source, template):
        where = template_rel or rel if g["origin"] == "template" else rel
        key = (g["kind"], g["construct"], where)
        if key in rows:
            rows[key]["occurrences"] += 1
            continue
        rows[key] = {
            "rule": f"NG_{g['kind'].upper().replace('-', '_')}", "severity": g["severity"],
            "file": where, "line": g["line"], "source_class": cls,
            "hazard": g["hazard"], "fix": g["fix"], "snippet": g["snippet"],
            "occurrences": 1,
        }
    out = []
    for row in rows.values():
        n = row.pop("occurrences")
        if n > 1:
            row["hazard"] = (f"{row['hazard']} Found {n} times in this file; the fix is the "
                             "same for each.")
        out.append(row)
    return out


def grounding_for(component: dict) -> str:
    """What the generator must be told before it writes this component. [1.24]

    Same argument as the derived queries in 1.23b and the transaction shapes in 1.21c:
    this is decidable from the source, and a decidable thing should not be generated. Left
    to its own devices the model reaches for `@wire`, because that is the answer to the
    question it was asked most often — and it is the wrong answer for a poll.
    """
    gaps = analyse(component.get("source", "") or "", component.get("template", "") or "")
    if not gaps:
        return ""

    seen, rows = set(), []
    for g in gaps:
        key = (g["kind"], g["construct"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(g)

    out = ["## Angular constructs with no LWC equivalent — already decided", "",
           "Each of these was found in the source below. Do not translate them by "
           "analogy; use the stated shape. `@wire` is **not** the answer for any of them "
           "— it cannot be driven by a timer and it does not compose.", ""]
    for g in rows:
        out.append(f"- **`{g['construct']}`** ({g['kind']}, line {g['line']}). "
                   f"{g['hazard']} → {g['fix']}")
    return "\n".join(out)


def summary(gaps: list[dict]) -> dict:
    """Counts by severity, for a report header."""
    out = {"high": 0, "medium": 0, "total": len(gaps)}
    for g in gaps:
        if g["severity"] in out:
            out[g["severity"]] += 1
    return out
