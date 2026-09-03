"""
java_transactions.py — what `@Transactional` becomes, and when it becomes nothing. [1.21c]

The radar already reports `@Transactional` and says to use a savepoint. That advice is
right about half the time, and the half it is wrong about is the more common one.

**Apex already has the transaction.** An uncaught exception from an entry point rolls the
whole thing back — every DML statement in the request, without a savepoint being set. So a
Spring method whose rollback is driven purely by *throwing* — validate, throw, let the
caller see it — needs no savepoint at all. Adding one is not merely redundant: each
`Database.setSavepoint()` consumes a DML statement from the 150 the transaction is allowed,
so a converter that adds savepoints everywhere spends the budget the migration needs.

A savepoint earns its place in exactly one shape: the method **catches** and carries on.
That is a *partial* rollback — undo this part, keep going — which Apex has no other way to
express.

And a gotcha worth carrying across, because it surprises people who know Spring: rolling
back does **not** restore governor counters. The DML you rolled back still counted against
the 150. A retry loop around a savepoint runs out of statements while appearing to have
undone its work.
"""

from __future__ import annotations

import javalang

#: How the method's rollback is driven, which decides what it becomes.
THROWS = "throws"          # rollback by propagating — Apex does this for free
CATCHES = "catches"        # partial rollback — a savepoint is the only way to say it


def _annotated(node) -> bool:
    return any((a.name or "").split(".")[-1] == "Transactional"
               for a in (node.annotations or []))


def analyse(source: str) -> list:
    """Every `@Transactional` method, and what it needs on the target.

    Each row: `{method, rollback, catches, dml, line}`.
    """
    try:
        tree = javalang.parse.parse(source or "")
    except Exception:
        return []

    out = []
    for _, method in tree.filter(javalang.tree.MethodDeclaration):
        if not _annotated(method):
            continue
        catches = len(list(method.filter(javalang.tree.CatchClause)))
        dml = sum(1 for _, c in method.filter(javalang.tree.MethodInvocation)
                  if c.member in ("save", "saveAll", "remove", "removeAll"))
        out.append({
            "method": method.name,
            "rollback": CATCHES if catches else THROWS,
            "catches": catches,
            "dml": dml,
            "line": method.position.line if method.position else 0,
        })
    return out


def findings(source: str, rel: str, cls: str, lines: list) -> list:
    """Radar findings that say which of the two shapes this is. [1.21c]"""
    out = []
    for m in analyse(source):
        if m["rollback"] == THROWS:
            hazard = (f"`{m['method']}()` is `@Transactional` and rolls back by throwing — "
                      "it catches nothing. Apex already does that: an uncaught exception "
                      "from an entry point rolls back every DML in the request. No "
                      "savepoint is needed, and adding one is not free — each "
                      "`Database.setSavepoint()` spends one of the 150 DML statements the "
                      "transaction is allowed.")
            fix = ("Drop the annotation and let the exception propagate. Confirm the "
                   "caller does not swallow it: Apex rolls back on an *uncaught* "
                   "exception, so a catch anywhere above this method turns the rollback "
                   "off silently.")
            severity = "medium"
        else:
            hazard = (f"`{m['method']}()` is `@Transactional` and catches "
                      f"{m['catches']} exception(s), so it rolls part of its work back and "
                      "carries on. Apex has no other way to express that than an explicit "
                      "savepoint, and this is the one shape where a savepoint is right.")
            fix = ("`Database.SavePoint sp = Database.setSavepoint();` before the work, "
                   "`Database.rollback(sp);` in the catch. Note that a rollback does "
                   "**not** restore governor counters — the DML you undid still counted "
                   "against the 150 — so a retry loop around this runs out of statements "
                   "while appearing to have undone its work.")
            severity = "high"

        out.append({
            "rule": "TRANSACTION_SHAPE", "severity": severity, "file": rel,
            "line": m["line"], "source_class": cls, "hazard": hazard, "fix": fix,
            "snippet": (lines[m["line"] - 1].strip()[:120]
                        if 0 < m["line"] <= len(lines) else ""),
        })
    return out


def grounding_for(sources: list) -> str:
    """The transaction mapping, for the Builder's prompt. [1.21c, 1.23b pattern]

    The same argument as the derived queries: this is decidable from the source, and a
    decidable thing should not be generated. Left to the model, "translate @Transactional"
    reliably produces a savepoint — which is right for one shape and wasteful for the
    other, and the wasteful one is the common one.
    """
    rows = [m for src in (sources or []) for m in analyse(src or "")]
    if not rows:
        return ""

    out = ["## @Transactional — already decided", ""]
    for m in rows:
        if m["rollback"] == THROWS:
            out.append(f"- `{m['method']}()` rolls back by throwing and catches nothing. "
                       "Emit it **without a savepoint**: an uncaught exception rolls back "
                       "the whole Apex transaction already, and a savepoint would spend "
                       "one of the 150 DML statements for nothing.")
        else:
            out.append(f"- `{m['method']}()` catches and continues, so it needs a real "
                       "savepoint: `Database.SavePoint sp = Database.setSavepoint();` "
                       "before the work and `Database.rollback(sp);` in the catch. A "
                       "rollback does not restore governor counters.")
    return "\n".join(out) + "\n"
