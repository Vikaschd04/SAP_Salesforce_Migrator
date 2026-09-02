"""
apex_characterization.py — the target half of characterization: recorded facts → Apex.

The neutral layer decides *which* recorded behaviours can be replayed and how much a
replay is worth. It does not know how to write the replay down. That is this module:
how a decimal is spelled, how an enum crosses the language boundary, what a test class
looks like, and how to find a method in generated code.

Everything here is Salesforce-specific by design. A Hybris target will hold the same four
answers in Java, which is the point of the split — the *evidence* is platform-neutral, and
only its expression changes.

One rule survives the split unchanged and matters more than the rest: **the assertion is
written here, from the recorded value.** The model is never asked what the answer should
be and its output is never trusted to say. That is what keeps a bridged test evidence
rather than a second opinion.
"""

from __future__ import annotations

import re

# A method signature in generated Apex, capturing whether it is static.
_SIG = r"(?:public|global|private|protected)\s+(?:(static)\s+)?[\w<>,\[\]\.]+\s+{m}\s*\("

# An adapter that writes its own assertion would defeat the entire point of the module,
# so bridges that try are rejected outright rather than trusted.
_FORBIDDEN = ("System.assert", "System.assertEquals", "System.assertNotEquals", "@isTest")


def literal(value: dict | None) -> str | None:
    """Render a recorded value as an Apex literal, or None if it cannot be one.

    `kind` comes from the source miner and says what sort of fact was recorded; this
    decides what that looks like in Apex. Enums are the one real translation: an Apex
    enum member is not addressable the way a Java one is, so recorded enum values cross
    as strings.
    """
    if not value or value.get("value") is None:
        return None
    kind, v = value.get("kind"), value["value"]
    if kind == "null":
        return "null"
    if kind == "string":
        return "'" + v.replace("'", "\\'") + "'"
    if kind == "enum":
        return f"'{v}'"
    return v                                  # bool, number, decimal — same spelling


def find_method(code: str, name: str) -> dict | None:
    """Locate `name` in generated Apex and report whether it is static."""
    hit = re.search(_SIG.format(m=re.escape(name)), code or "")
    return None if not hit else {"static": bool(hit.group(1))}


def test_class_name(target: str) -> str:
    return f"{target}CharacterizationTest"


def emit(runnable_by_target: dict[str, list[dict]]) -> dict[str, str]:
    """Build one Apex characterization test class per target.

    Two kinds of row arrive: `direct` (the signature survived, so the call is constructed
    deterministically) and bridged `adapter` rows (a model arranged the inputs for a
    reshaped signature). In BOTH cases the assertion below is written from the recorded
    value, never from the model.
    """
    out = {}
    for target, rows in sorted(runnable_by_target.items()):
        cls = test_class_name(target)
        L = [f"@isTest",
             f"private class {cls} {{",
             "    // Generated from the Hybris JUnit suite. Every expected value below was",
             "    // RECORDED from the original system — none of it is inferred. A failure here",
             "    // means the migrated behaviour genuinely differs from the legacy behaviour.",
             ""]
        for r in rows:
            msg = f"{r['id']} · {r['test_class']}.{r['test_method']}"
            expected = literal(r.get("expected"))

            if r.get("bridge"):
                br = r["bridge"]
                L += [f"    // {r['id']} — recorded: {r['label']}",
                      f"    // bridged onto the reshaped signature: {br.get('note', '')[:110]}",
                      "    @isTest",
                      f"    static void {r['id'].replace('-', '_').lower()}() {{"]
                if r["expects_exception"]:
                    L += ["        Boolean threw = false;", "        try {"]
                    L += [f"            {ln}" for ln in br["setup"].splitlines()]
                    L += ["        } catch (Exception e) { threw = true; }",
                          f"        System.assert(threw, '{msg} — expected a rejection');"]
                else:
                    L += [f"        {ln}" for ln in br["setup"].splitlines()]
                    L += [f"        System.assertEquals({expected}, {br['result_expr']},",
                          f"            '{msg}');"]
                L += ["    }", ""]
                continue

            args = ", ".join(literal(a) for a in r["args"])
            call = (f"{r['target']}.{r['target_method']}({args})" if r.get("static")
                    else f"new {r['target']}().{r['target_method']}({args})")
            L += [f"    // {r['id']} — recorded: {r['label']}",
                  f"    @isTest",
                  f"    static void {r['id'].replace('-', '_').lower()}() {{"]
            if r["expects_exception"]:
                L += ["        Boolean threw = false;",
                      f"        try {{ {call}; }} catch (Exception e) {{ threw = true; }}",
                      f"        System.assert(threw, '{msg} — expected a rejection');"]
            else:
                L += [f"        System.assertEquals({expected}, {call},",
                      f"            '{msg}');"]
            L += ["    }", ""]
        L.append("}")
        out[cls] = "\n".join(L)
    return out


# ── bridging a reshaped call ──────────────────────────────────────────────────

ADAPTER_SCHEMA = {
    "type": "object",
    "properties": {
        "bridges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "the behaviour id being bridged"},
                    "feasible": {"type": "boolean",
                                 "description": "false if this legacy call cannot be faithfully "
                                                "expressed against the new signature"},
                    "setup": {"type": "string",
                              "description": "Apex statements that arrange test data and invoke "
                                             "the new method. NO assertions."},
                    "result_expr": {"type": "string",
                                    "description": "an Apex expression yielding the single value "
                                                   "equivalent to what the legacy call returned"},
                    "note": {"type": "string", "description": "how the shapes were reconciled"},
                },
                "required": ["id", "feasible", "setup", "result_expr", "note"],
            },
        }
    },
    "required": ["bridges"],
}

_ADAPTER_SYSTEM = (
    "You port recorded legacy test cases onto migrated Apex. You are given facts about how "
    "a Java system behaved and the Apex that replaced it. Your ONLY job is to arrange the "
    "equivalent inputs and invoke the new code.\n\n"
    "You must NEVER write an assertion, and you must NEVER state what the expected value is — "
    "the expected value is a recorded fact supplied separately and will be asserted for you. "
    "If you cannot express the legacy call against the new signature without changing its "
    "meaning, set feasible=false. A false is always better than a plausible fabrication."
)


def bridge_request(target: str, code: str, rows: list[dict]) -> dict:
    """Everything the neutral bridging loop needs to ask this target's question.

    Returned rather than executed, so the LLM plumbing — cost accounting, retries,
    schema handling, the forbidden-token check — stays in one platform-neutral place.
    """
    lines = [f"# The migrated Apex class `{target}`", "```apex", (code or "")[:12000], "```", "",
             "# Recorded legacy behaviours to bridge", ""]
    for r in rows:
        args = ", ".join(a["source"] for a in r["args"])
        lines.append(f"- id `{r['id']}` — legacy call `{r['source_class']}.{r['target_method']}({args})`")
        lines.append(f"  · what it did: {r['label']}")
        if r["expects_exception"]:
            lines.append(f"  · the legacy code REJECTED this input (threw {r['expects_exception']}). "
                         "Arrange the equivalent invalid input and invoke; the rejection is asserted for you.")
        else:
            lines.append("  · it returned a single value. `result_expr` must yield the Apex "
                         "equivalent of that value.")
    lines += ["", "For each id return a bridge. `setup` may insert records and call the new "
                  "method; `result_expr` must be a single expression (often a local variable you "
                  "assigned in `setup`). Do not assert anything."]
    return {"prompt": "\n".join(lines), "system": _ADAPTER_SYSTEM, "schema": ADAPTER_SCHEMA,
            "max_tokens": 4000, "forbidden": _FORBIDDEN}
