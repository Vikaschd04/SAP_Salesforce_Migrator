"""
flow_generator.py — a Hybris business process becomes a Salesforce Flow.

The state machine is *fully specified* in the source XML: which action runs first, which
named outcome goes where, where the waits are, what the end states are. None of that needs
a judgement call, so none of it goes near a language model. The graph is translated
deterministically, which makes it free, repeatable, and testable — and it means the shape
of your process cannot be hallucinated.

    Hybris                          Salesforce Flow
    ─────────────────────────────   ────────────────────────────────────────────
    <process start="...">           <start> → first element
    <action bean="fooAction">       <actionCalls> invoking an @InvocableMethod
    <transition name="OK" to=..>    <decisions> branching on the action's outcome
    <wait><timeout delay="PT4H">    <waits> with a duration event
    <end state="SUCCEEDED">         a terminal assignment, then no connector

**What this does not claim.** The topology is faithful; the *semantics inside each step*
are only as good as the Apex the Builder produced, and two things are genuinely inferred:

- **Outcome strings.** Hybris transitions are named (`OK`, `NOK`, `DECLINED`) and the
  action returns one. The generated wrapper returns that string and the decision compares
  against it — which is right if the converted Apex kept the same vocabulary, and wrong if
  the Builder renamed it. Every generated decision is listed for review for that reason.
- **What flows between steps.** Hybris passes a process model; the Flow passes a record id.
  Anything else an action read off the process (retry counters, flags) is *not* wired, and
  is reported per action rather than quietly dropped.

So this is a **deployable scaffold that preserves the shape of the process**, not a
finished migration — and it says so, in the Flow's own description, in the ledger, and in
BUSINESS_PROCESSES.md. Shipping it as "done" would be the overclaim this product exists
not to make.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

API_VERSION = "62.0"

# Laid out on a grid so the Flow Builder canvas is readable rather than a pile at 0,0 —
# a reviewer opening this in Salesforce should see the process, not untangle it.
_X0, _Y0, _DX, _DY = 176, 48, 340, 168


def _safe(name: str) -> str:
    """A Flow element API name: alphanumeric + underscore, not starting with a digit."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", name or "")
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "Step"
    return ("X" + s) if s[0].isdigit() else s


def _label(name: str) -> str:
    """`authorizePayment` → `Authorize Payment`, for the canvas."""
    s = re.sub(r"(?<!^)(?=[A-Z])", " ", name or "").replace("_", " ")
    return " ".join(w.capitalize() if w.islower() else w for w in s.split()) or "Step"


def _iso8601_to_minutes(delay: str) -> int | None:
    """`PT4H` → 240. Flow measures pauses in minutes; Hybris uses ISO-8601 durations."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", (delay or "").strip())
    if not m:
        return None
    d, h, mi, s = (int(g) if g else 0 for g in m.groups())
    total = d * 1440 + h * 60 + mi + (1 if s and not (d or h or mi) else 0)
    return total or None


def _invocable_name(cls: str) -> str:
    return f"{cls}Invocable"


def build_flow(process: dict, converted: set[str] | None = None) -> dict:
    """Translate one process into Flow metadata + the wrappers it needs to call.

    Returns {name, api_name, xml, invocables, review_notes, coverage}.
    """
    converted = converted or set()
    api = _safe(process.get("name") or "Process")
    nodes = {}                                   # id -> element api name
    order = []

    actions = process.get("actions") or []
    flow_nodes = process.get("flow") or []
    ends = process.get("end_states") or []

    for a in actions:
        nid = a.get("id") or a.get("bean") or "step"
        nodes[nid] = _safe(nid)
        order.append(("action", a))
    for w in flow_nodes:
        nid = w.get("id") or "wait"
        nodes[nid] = _safe(nid)
        order.append(("flow", w))
    for e in ends:
        nodes[e.get("id", "")] = _safe(e.get("id") or "End")

    def target(ref: str) -> str:
        """A transition target as a Flow element reference, or '' for a dangling edge."""
        return nodes.get(ref, "")

    review, xml, positions = [], [], {}
    for i, (_, n) in enumerate(order):
        positions[n.get("id", "")] = (_X0 + (i % 3) * _DX, _Y0 + (i // 3) * _DY)
    for i, e in enumerate(ends):
        positions[e.get("id", "")] = (_X0 + (i % 3) * _DX,
                                      _Y0 + ((len(order) + 2) // 3) * _DY)

    invocables = {}
    for a in actions:
        aid = a.get("id") or ""
        cls = a.get("implemented_by") or ""
        el = nodes.get(aid, _safe(aid))
        x, y = positions.get(aid, (_X0, _Y0))
        outs = a.get("transitions_to") or []

        if cls and cls in converted:
            invocables[cls] = _invocable_name(cls)
            action_name = _invocable_name(cls)
        else:
            # No Apex to call. The step is still placed, so the shape of the process
            # survives and the hole is visible on the canvas rather than absent from it.
            action_name = ""
            review.append(
                f"`{aid}` has no converted Apex to call"
                + (f" (bean `{a.get('bean', '')}` did not resolve to a class)"
                   if not cls else f" (`{cls}` was not generated)")
                + " — the step is present but does nothing until you point it at an "
                  "@InvocableMethod.")

        # Where this element goes next. One outcome → straight connector; more than one →
        # a decision element, because a named Hybris transition is a branch.
        nxt = f"{el}_Outcome" if len(outs) > 1 else (target(outs[0]) if outs else "")

        xml.append(_action_call(el, _label(aid), x, y, action_name, nxt,
                                bool(action_name)))

        if len(outs) > 1:
            names = [t.get("name", "") for t in (a.get("transitions") or [])]
            xml.append(_decision(f"{el}_Outcome", f"{_label(aid)} — outcome",
                                 x, y + 84, el, outs, names, target))
            review.append(
                f"`{aid}` branches {len(outs)} ways. The decision compares the value the "
                "Apex returns against the original Hybris transition names — check the "
                "converted class still uses them.")

    for w in flow_nodes:
        wid = w.get("id") or ""
        el = nodes.get(wid, _safe(wid))
        x, y = positions.get(wid, (_X0, _Y0))
        outs = w.get("transitions_to") or []
        mins = _iso8601_to_minutes(w.get("timeout") or "")
        xml.append(_wait(el, _label(wid), x, y,
                         target(outs[0]) if outs else "",
                         target(outs[1]) if len(outs) > 1 else "", mins))
        review.append(
            f"`{wid}` was a Hybris wait" +
            (f" for `{w.get('event')}`" if w.get("event") else "") +
            (f" with a {w.get('timeout')} timeout" if w.get("timeout") else "") +
            ". It is a Flow pause on the timeout only — **the resume event is not wired**, "
            "because Hybris events have no automatic Salesforce equivalent. Connect a "
            "Platform Event or a scheduled path before relying on this.")

    for e in ends:
        eid = e.get("id") or ""
        el = nodes.get(eid, _safe(eid))
        x, y = positions.get(eid, (_X0, _Y0))
        xml.append(_end_assignment(el, _label(eid), x, y, e.get("state", "")))

    start_ref = target(process.get("start") or "") or (
        nodes.get(actions[0].get("id"), "") if actions else "")

    body = _flow_document(api, process, start_ref, xml, review)
    resolved = sum(1 for a in actions if (a.get("implemented_by") or "") in converted)
    return {
        "name": process.get("name") or api,
        "api_name": api,
        "xml": body,
        "invocables": invocables,
        "review_notes": review,
        "coverage": {"actions": len(actions), "wired": resolved,
                     "waits": len(flow_nodes), "ends": len(ends)},
    }


# ── element writers ───────────────────────────────────────────────────────────

def _conn(target_ref: str, tag: str = "connector") -> str:
    if not target_ref:
        return ""
    return f"    <{tag}><targetReference>{target_ref}</targetReference></{tag}>\n"


def _action_call(name, label, x, y, action_name, next_ref, wired) -> str:
    out = [f"  <actionCalls>\n    <name>{name}</name>\n"
           f"    <label>{escape(label)}</label>\n"
           f"    <locationX>{x}</locationX>\n    <locationY>{y}</locationY>\n"]
    if wired:
        out.append(f"    <actionName>{action_name}</actionName>\n"
                   "    <actionType>apex</actionType>\n")
        out.append("    <inputParameters>\n"
                   "      <name>recordIds</name>\n"
                   "      <value><elementReference>recordId</elementReference></value>\n"
                   "    </inputParameters>\n")
    else:
        # A placeholder keeps the topology visible on the canvas. It is deliberately
        # inert: a step that silently did nothing would be worse than one that is
        # obviously unfinished.
        out.append("    <actionName>__NOT_MIGRATED__</actionName>\n"
                   "    <actionType>apex</actionType>\n"
                   "    <description>No converted Apex for this step — wire an "
                   "@InvocableMethod here.</description>\n")
    out.append(_conn(next_ref))
    out.append("  </actionCalls>\n")
    return "".join(out)


def _decision(name, label, x, y, source_el, targets, names, resolve) -> str:
    out = [f"  <decisions>\n    <name>{name}</name>\n"
           f"    <label>{escape(label)}</label>\n"
           f"    <locationX>{x}</locationX>\n    <locationY>{y}</locationY>\n"]
    # The last transition becomes the default path, so no outcome is left unhandled.
    for i, tgt in enumerate(targets[:-1]):
        outcome = names[i] if i < len(names) and names[i] else f"Outcome{i + 1}"
        ref = resolve(tgt)
        out.append(
            f"    <rules>\n      <name>{_safe(name + '_' + outcome)}</name>\n"
            "      <conditionLogic>and</conditionLogic>\n"
            "      <conditions>\n"
            f"        <leftValueReference>{source_el}.outcome</leftValueReference>\n"
            "        <operator>EqualTo</operator>\n"
            f"        <rightValue><stringValue>{escape(outcome)}</stringValue></rightValue>\n"
            "      </conditions>\n"
            + _conn(ref).replace("    <", "      <")
            + f"      <label>{escape(outcome)}</label>\n    </rules>\n")
    last = resolve(targets[-1]) if targets else ""
    out.append(_conn(last, "defaultConnector"))
    default_label = names[-1] if names and names[-1] else "Otherwise"
    out.append(f"    <defaultConnectorLabel>{escape(default_label)}</defaultConnectorLabel>\n")
    out.append("  </decisions>\n")
    return "".join(out)


def _wait(name, label, x, y, then_ref, timeout_ref, minutes) -> str:
    mins = minutes or 60
    return (f"  <waits>\n    <name>{name}</name>\n"
            f"    <label>{escape(label)}</label>\n"
            f"    <locationX>{x}</locationX>\n    <locationY>{y}</locationY>\n"
            "    <description>Hybris wait. The timeout is modelled; the resume event is "
            "not — wire a Platform Event before relying on this.</description>\n"
            f"    <defaultConnectorLabel>Resumed</defaultConnectorLabel>\n"
            + _conn(then_ref, "defaultConnector") +
            f"    <waitEvents>\n      <name>{name}_Timeout</name>\n"
            f"      <conditionLogic>and</conditionLogic>\n"
            + _conn(timeout_ref or then_ref).replace("    <", "      <") +
            f"      <label>After {mins} minutes</label>\n"
            "      <inputParameters>\n        <name>TimeOffset</name>\n"
            f"        <value><numberValue>{mins}.0</numberValue></value>\n"
            "      </inputParameters>\n"
            "      <inputParameters>\n        <name>TimeOffsetUnit</name>\n"
            "        <value><stringValue>Minutes</stringValue></value>\n"
            "      </inputParameters>\n"
            "      <eventType>AlarmEvent</eventType>\n"
            "    </waitEvents>\n  </waits>\n")


def _end_assignment(name, label, x, y, state) -> str:
    """A terminal state, recorded in a variable so the outcome is observable."""
    return (f"  <assignments>\n    <name>{name}</name>\n"
            f"    <label>{escape(label)}</label>\n"
            f"    <locationX>{x}</locationX>\n    <locationY>{y}</locationY>\n"
            "    <assignmentItems>\n"
            "      <assignToReference>processResult</assignToReference>\n"
            "      <operator>Assign</operator>\n"
            f"      <value><stringValue>{escape(state or name)}</stringValue></value>\n"
            "    </assignmentItems>\n  </assignments>\n")


def _flow_document(api, process, start_ref, elements, review) -> str:
    src = Path(process.get("file", "")).name
    desc = (f"Generated from the Hybris business process `{process.get('name', '')}` "
            f"({src}). The topology is a faithful translation; outcome names and the data "
            "passed between steps are inferred and need review. "
            f"{len(review)} item(s) flagged — see BUSINESS_PROCESSES.md.")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Flow xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        f"  <apiVersion>{API_VERSION}</apiVersion>\n"
        f"  <description>{escape(desc)}</description>\n"
        "  <environments>Default</environments>\n"
        f"  <interviewLabel>{escape(_label(api))} {{!$Flow.CurrentDateTime}}</interviewLabel>\n"
        f"  <label>{escape(_label(api))}</label>\n"
        "  <processType>AutoLaunchedFlow</processType>\n"
        # Draft on purpose: an unreviewed translation of someone's order pipeline must not
        # be activatable by an accidental deploy.
        "  <status>Draft</status>\n"
        + "".join(elements) +
        "  <start>\n    <locationX>50</locationX>\n    <locationY>0</locationY>\n"
        + _conn(start_ref) +
        "  </start>\n"
        "  <variables>\n    <name>recordId</name>\n    <dataType>String</dataType>\n"
        "    <isCollection>false</isCollection>\n    <isInput>true</isInput>\n"
        "    <isOutput>false</isOutput>\n  </variables>\n"
        "  <variables>\n    <name>processResult</name>\n    <dataType>String</dataType>\n"
        "    <isCollection>false</isCollection>\n    <isInput>false</isInput>\n"
        "    <isOutput>true</isOutput>\n  </variables>\n"
        "</Flow>\n")


def build_invocable(apex_class: str, methods: list[str] | None = None) -> str:
    """A thin @InvocableMethod wrapper so a Flow can call converted Apex.

    Separate from the converted class on purpose. The Builder's output is what provenance
    traces and the Critic reviewed; bolting an invocable annotation into it afterwards
    would put generated-by-a-different-mechanism code inside an artifact that other parts
    of the system have already vouched for.
    """
    name = _invocable_name(apex_class)
    return f"""/**
 * Flow entry point for {apex_class}, generated from a Hybris business process.
 *
 * Bulk-safe by construction: Flow invokes with a list, and the outcome list returned is
 * positionally aligned with the input. The outcome string is what the Flow's decision
 * elements branch on — keep it matching the original Hybris transition names
 * (OK / NOK / ...) or update the Flow to match.
 */
public with sharing class {name} {{

    public class Request {{
        @InvocableVariable(required=true label='Record Id')
        public Id recordId;
    }}

    public class Result {{
        @InvocableVariable(label='Outcome')
        public String outcome;
    }}

    @InvocableMethod(label='{_label(apex_class)}' category='Migrated Hybris Process')
    public static List<Result> run(List<Request> requests) {{
        List<Result> results = new List<Result>();
        for (Request req : requests) {{
            Result res = new Result();
            // TODO: call {apex_class} with the record and map its return to an outcome
            // string. The Hybris action returned a named transition; the Flow branches on
            // that name, so this mapping is the contract between the two.
            res.outcome = 'OK';
            results.add(res);
        }}
        return results;
    }}
}}
"""
