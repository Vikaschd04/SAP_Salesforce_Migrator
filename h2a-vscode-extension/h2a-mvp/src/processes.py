"""
processes.py — Hybris business processes, which used to be invisible.

A Hybris business process is a state machine defined in XML: `<action>` nodes bound to
Java beans, wired together by named `<transition>`s, with waits, splits, joins and end
states. Order fulfilment, returns, and customer registration are all typically processes.

**The bug this fixes was a silent one.** `ingest` reads `.java` and `items.xml` and nothing
else, so a `*-process.xml` was never opened. The action classes converted fine — they are
ordinary Java — so the *pieces* appeared in the output while the *wiring* disappeared. And
because the completeness ledger accounts for ingested classes, a file that was never
ingested could not be reported as dropped, skipped or unaccounted. It simply did not exist
as far as the run was concerned: the one category of loss the ledger structurally could
not see.

This does not convert processes yet. It reads them, resolves each action to the Java class
that implements it, and reports the whole thing as **awaiting manual migration** — with the
actions that did convert listed beside the ones that did not, so a reviewer knows exactly
what they are holding and what is missing. A known gap that is reported is a different
thing from a gap nobody can see, and it is worth shipping on its own.

Parsed deterministically. No model calls, so this is available at the Discovery gate —
before anyone has spent anything on a migration that was always going to be incomplete.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from src.textio import read_text_or_empty

# Nodes that carry behaviour worth reporting. `wait`/`split`/`join` shape the flow but
# have no bean of their own, and are counted rather than listed.
_ACTION_TAGS = {"action", "scriptAction"}
_FLOW_TAGS = {"wait", "split", "join", "notify"}


def _localname(tag: str) -> str:
    """ElementTree keeps the namespace on the tag; process XML is always namespaced."""
    return tag.rsplit("}", 1)[-1]


def _is_process_xml(path: Path) -> bool:
    """Identify by root element, not filename.

    The convention is `*-process.xml`, but it is only a convention — teams rename these,
    and an items.xml in a folder called `process` would match a filename test. Reading the
    root element is cheap and cannot be fooled by either.
    """
    if path.suffix.lower() != ".xml":
        return False
    head = read_text_or_empty(str(path))[:4000]
    return bool(re.search(r"<\s*process\b", head))


def _bean_to_class(bean: str, class_names: set[str]) -> str:
    """Resolve an action's bean id to an ingested class name where we can.

    Hybris wires actions by Spring bean id. Conventionally the id is the class name with a
    lowercase first letter (`sendOrderConfirmationAction` → `SendOrderConfirmationAction`),
    and often the bean is defined in a spring XML we do not parse. So this is a best-effort
    match, reported as such: an unresolved bean is listed by its id rather than guessed at.
    """
    if not bean:
        return ""
    cand = bean[0].upper() + bean[1:]
    if cand in class_names:
        return cand
    # `acmecore.sendOrderConfirmationAction` and similar qualified ids.
    tail = bean.rsplit(".", 1)[-1]
    cand = tail[0].upper() + tail[1:] if tail else ""
    return cand if cand in class_names else ""


def parse_process(path: str, class_names: set[str] | None = None) -> dict | None:
    """One process definition, or None if the file will not parse."""
    class_names = class_names or set()
    text = read_text_or_empty(path)
    if not text.strip():
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        # Reported rather than skipped — an unparseable process is still a process.
        return {"name": Path(path).stem, "file": path, "unreadable": str(e),
                "actions": [], "flow_nodes": 0, "transitions": 0, "end_states": []}

    if _localname(root.tag) != "process":
        return None

    actions, flow, transitions, ends = [], [], 0, []
    for node in root.iter():
        tag = _localname(node.tag)
        if tag in _ACTION_TAGS:
            bean = node.get("bean", "") or node.get("class", "")
            # Names as well as targets: a Hybris transition name (OK / NOK / DECLINED) is
            # the value the action returns, so it is the condition a Salesforce Flow
            # decision has to compare against. Dropping it would leave the branch
            # untranslatable.
            edges = [{"name": t.get("name", ""), "to": t.get("to", "")}
                     for t in node if _localname(t.tag) == "transition"]
            transitions += len(edges)
            actions.append({
                "id": node.get("id", ""),
                "bean": bean,
                "implemented_by": _bean_to_class(bean, class_names),
                "transitions": edges,
                "transitions_to": [e["to"] for e in edges if e["to"]],
            })
        elif tag in _FLOW_TAGS:
            # `then` and a timeout's `then` are edges in the state machine as much as a
            # named transition is. Counting only <transition> elements undercounts how
            # much orchestration there is to rebuild — the wrong direction to be wrong in
            # for a report whose whole job is to say what is missing.
            outs = [node.get("then", "")]
            timeout = next((c for c in node if _localname(c.tag) == "timeout"), None)
            event = next((c for c in node if _localname(c.tag) == "event"), None)
            if timeout is not None:
                outs.append(timeout.get("then", ""))
            outs += [t.get("to", "") for t in node if _localname(t.tag) == "transition"]
            outs = [o for o in outs if o]
            transitions += len(outs)
            flow.append({
                "id": node.get("id", ""),
                "kind": tag,
                "transitions_to": outs,
                "event": (event.text or "").strip() if event is not None else "",
                "timeout": (timeout.get("delay", "") if timeout is not None else ""),
            })
        elif tag == "end":
            ends.append({"id": node.get("id", ""), "state": node.get("state", "")})

    return {
        "name": root.get("name") or Path(path).stem,
        "file": path,
        "start": root.get("start", ""),
        "process_class": root.get("processClass", ""),
        "on_error": root.get("onError", ""),
        "actions": actions,
        "flow": flow,
        "flow_nodes": len(flow),
        "transitions": transitions,
        "end_states": ends,
        "unreadable": "",
    }


def discover(input_dir: str, class_names: set[str] | None = None) -> list[dict]:
    """Every business process under a codebase, deterministically."""
    found = []
    for root, _, files in os.walk(input_dir):
        for f in files:
            p = Path(root) / f
            try:
                if not _is_process_xml(p):
                    continue
            except OSError:
                continue
            rec = parse_process(str(p), class_names)
            if rec:
                found.append(rec)
    return sorted(found, key=lambda r: r["name"])


def summarise(processes: list[dict]) -> dict:
    acts = [a for p in processes for a in p["actions"]]
    resolved = [a for a in acts if a["implemented_by"]]
    gen = [p.get("generated_flow") for p in processes if p.get("generated_flow")]
    return {
        "processes": len(processes),
        "actions": len(acts),
        "actions_resolved": len(resolved),
        "unreadable": sum(1 for p in processes if p.get("unreadable")),
        "transitions": sum(p.get("transitions", 0) for p in processes),
        "scaffolded": len(gen),
        "wired": sum((g.get("coverage") or {}).get("wired", 0) for g in gen),
        "review_items": sum(len(g.get("review_notes") or []) for g in gen),
    }


def _plural(n: int, one: str, many: str = "") -> str:
    """Customer-facing counts read badly as `1 process(es)`."""
    return f"{n} {one if n == 1 else (many or one + 's')}"


def headline(s: dict) -> str:
    if not s.get("processes"):
        return "No Hybris business processes found."
    base = (f"{_plural(s['processes'], 'business process', 'business processes')} found — "
            f"{_plural(s['actions'], 'action')}, "
            f"{_plural(s['transitions'], 'transition')}")
    if s.get("scaffolded"):
        return (f"{base}. {_plural(s['scaffolded'], 'Flow')} generated as a Draft "
                f"scaffold — {s.get('wired', 0)}/{s['actions']} steps wired to converted "
                "Apex; the rest need finishing by hand.")
    return (f"{base}. Not migrated: the action classes convert, the orchestration that "
            "sequences them does not.")


def covered_classes(processes: list[dict]) -> set[str]:
    """Java classes that an action points at — they convert, but only as loose pieces."""
    return {a["implemented_by"] for p in processes for a in p["actions"]
            if a["implemented_by"]}


def ledger_rows(processes: list[dict], converted: set[str] | None = None) -> list[dict]:
    """Ledger entries so a process cannot vanish without trace.

    Deliberately shaped like the class rows around them: one row per process, outcome
    `manual`, and a note that names what *did* convert so the reviewer can see they are
    holding the pieces without the wiring.
    """
    converted = converted or set()
    rows = []
    for p in processes:
        if p.get("unreadable"):
            rows.append({"source": p["name"], "layer": "Process", "outcome": "unreadable",
                         "target": "—",
                         "note": f"could not parse ({p['unreadable']}) — migrate by hand"})
            continue
        acts = p["actions"]
        built = [a["implemented_by"] for a in acts
                 if a["implemented_by"] and a["implemented_by"] in converted]
        gen = p.get("generated_flow")
        if gen:
            cov = gen.get("coverage", {})
            wired, total = cov.get("wired", 0), cov.get("actions", len(acts))
            # `scaffolded`, not `converted`. The topology is faithful and it deploys, but
            # unwired steps and inferred outcome names mean calling it converted would be
            # the overclaim this ledger exists to prevent.
            note = (f"Flow `{gen['api_name']}` generated (Draft) — topology faithful, "
                    f"{wired}/{total} steps wired to converted Apex, "
                    f"{_plural(len(gen.get('review_notes') or []), 'item')} needing "
                    "review. See BUSINESS_PROCESSES.md.")
            rows.append({"source": p["name"], "layer": "Process",
                         "outcome": "scaffolded",
                         "target": f"flows/{gen['api_name']}", "note": note})
            continue
        note = (f"{_plural(len(acts), 'action')}, "
                f"{_plural(p.get('transitions', 0), 'transition')}. "
                f"{_plural(len(built), 'action class', 'action classes')} converted to "
                "Apex; the process that sequences them did not — rebuild it as a Flow or "
                "an Apex state machine.")
        rows.append({"source": p["name"], "layer": "Process", "outcome": "manual",
                     "target": "—", "note": note})
    return rows


def write_processes_md(output_dir: str, processes: list[dict]) -> str:
    s = summarise(processes)
    scaffolded = bool(s.get("scaffolded"))
    title = ("# Business Processes — translated to Flow, needs finishing" if scaffolded
             else "# Business Processes — not migrated")
    out = [title, "",
           "Hybris business processes are state machines: actions wired together by named "
           "transitions, with waits and error paths. The action classes inside them are "
           "ordinary Java and were converted to Apex.", "",
           f"**{headline(s)}**", ""]

    if scaffolded:
        out += ["> ⚠️ **This is a scaffold, not a finished migration.** The *topology* is a "
                "faithful translation — every step, branch, wait and end state is in the "
                "generated Flow, in the right order. Two things are inferred and need a "
                "human:", "",
                "> 1. **Outcome names.** A Hybris transition is named (`OK`, `DECLINED`) "
                "and the action returns it. Each Flow decision compares against that name, "
                "which holds only if the converted Apex kept the same vocabulary.",
                "> 2. **What passes between steps.** Hybris hands each action a process "
                "model; the Flow passes a record id. Anything else an action read from the "
                "process — retry counters, flags — is not wired.", "",
                "> Every generated Flow is deployed as **Draft** on purpose: an unreviewed "
                "translation of an order pipeline must not become activatable through an "
                "accidental deploy.", ""]
    else:
        out += ["> ⚠️ **You are holding the pieces without the wiring.** Each action below "
                "has an Apex counterpart where its class was resolved, but nothing "
                "reproduces the order they run in, the conditions between them, or the "
                "error paths. Rebuild each process as a Salesforce **Flow**, or as an "
                "Apex state machine where Flow cannot express it.", ""]

    for p in processes:
        out += [f"## `{p['name']}`", "", f"<sub>{p['file']}</sub>", ""]
        if p.get("unreadable"):
            out += [f"> Could not parse this file: {p['unreadable']}", ""]
            continue
        meta = []
        if p.get("start"):
            meta.append(f"starts at `{p['start']}`")
        if p.get("on_error"):
            meta.append(f"on error → `{p['on_error']}`")
        if p.get("process_class"):
            meta.append(f"process class `{p['process_class']}`")
        if meta:
            out += ["- " + " · ".join(meta), ""]

        if p["actions"] or p.get("flow"):
            out += ["| Step | Bean | Implemented by | Goes to |", "|---|---|---|---|"]
            for a in p["actions"]:
                impl = f"`{a['implemented_by']}`" if a["implemented_by"] else \
                       "_unresolved — check your Spring config_"
                nxt = ", ".join(f"`{t}`" for t in a["transitions_to"]) or "—"
                out.append(f"| `{a['id'] or '—'}` | `{a['bean'] or '—'}` | {impl} | {nxt} |")
            for w in p.get("flow", []):
                detail = w["kind"]
                if w.get("event"):
                    detail += f" on `{w['event']}`"
                if w.get("timeout"):
                    detail += f", timeout {w['timeout']}"
                nxt = ", ".join(f"`{t}`" for t in w["transitions_to"]) or "—"
                out.append(f"| `{w['id'] or '—'}` | _{detail}_ | "
                           f"**no class — pure orchestration** | {nxt} |")
            out.append("")
        if p["end_states"]:
            out += ["**End states:** " + ", ".join(
                f"`{e['id']}`" + (f" ({e['state']})" if e["state"] else "")
                for e in p["end_states"]), ""]

        gen = p.get("generated_flow")
        if gen:
            cov = gen.get("coverage") or {}
            out += ["", f"### Generated Flow — `{gen['api_name']}`", "",
                    f"`force-app/main/default/flows/{gen['api_name']}.flow-meta.xml` · "
                    f"**Draft** · {cov.get('wired', 0)}/{cov.get('actions', 0)} steps "
                    f"wired to converted Apex · {cov.get('waits', 0)} wait(s) · "
                    f"{cov.get('ends', 0)} end state(s)", ""]
            notes = gen.get("review_notes") or []
            if notes:
                out += [f"**{_plural(len(notes), 'item')} to finish before this Flow does "
                        "what the Hybris process did:**", ""]
                out += [f"{i}. {n}" for i, n in enumerate(notes, 1)]
                out.append("")

    out += ["---", "",
            "> **Why this file exists.** These definitions were once never read at all, so "
            "a process could not even be reported as missing — it was absent from the "
            "completeness ledger rather than listed in it. It is now parsed, translated "
            "into a Flow whose shape you can check against the table above, and listed "
            "with everything that still needs a human. A loss nobody can see is the one "
            "that reaches production; a scaffold you can read and finish is not a loss."]

    path = Path(output_dir) / "BUSINESS_PROCESSES.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
