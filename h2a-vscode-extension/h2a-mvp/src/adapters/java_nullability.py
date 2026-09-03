"""
java_nullability.py — a getter's result dereferenced without a guard. [1.30]

Split out of 1.17 for a reason that still holds: deciding whether a getter *can* return
null needs type resolution across files, and a regex over call sites would be noisy in
both directions. A noisy rule gets ignored, which is worse than no rule.

So this asks a narrower question that the AST answers exactly: **is the result of a getter
dereferenced in a method that never checks it against null?** That is not "can this be
null" — it is "if it is, this line throws, and nothing here says otherwise".

Why it matters on this pair specifically. Hybris model getters return boxed types and
return null freely for an unset attribute; the same code migrated to Apex throws a
NullPointerException at *runtime*, which means it passes every static check, deploys
cleanly, and fails on the first record with an empty field. The reference corpus shows
both shapes within a few lines of each other:

    order.getTotalPrice() == null ? BigDecimal.ZERO           // guarded
        : BigDecimal.valueOf(order.getTotalPrice().doubleValue())
    event.getProcess().getOrder()                             // not

A guard anywhere in the same method counts, deliberately. Tracking whether the check
dominates the use needs flow analysis, and being wrong about that direction produces false
positives on correct code — the direction that makes a rule ignored.
"""

from __future__ import annotations

import javalang

#: Prefixes that name an accessor. `is`/`has` return primitives in practice, so they
#: cannot produce the null this rule is about.
_GETTER = ("get",)


def _is_getter(member: str) -> bool:
    return bool(member) and member.startswith(_GETTER) and len(member) > 3 \
        and member[3].isupper()


def _guarded_in(method) -> set:
    """`{(qualifier, member)}` compared against null anywhere in this method."""
    out = set()
    for _, node in method.filter(javalang.tree.BinaryOperation):
        if node.operator not in ("==", "!="):
            continue
        operands = [node.operandl, node.operandr]
        if not any(isinstance(o, javalang.tree.Literal) and o.value == "null"
                   for o in operands):
            continue
        for o in operands:
            if isinstance(o, javalang.tree.MethodInvocation) and _is_getter(o.member):
                out.add((o.qualifier or "", o.member))
    return out


def find_unguarded(source: str) -> list:
    """Every getter result dereferenced in a method that never null-checks it.

    Each row: `{method, expression, line}`.
    """
    try:
        tree = javalang.parse.parse(source or "")
    except Exception:
        return []

    out = []
    for _, method in tree.filter(javalang.tree.MethodDeclaration):
        guarded = _guarded_in(method)
        for _, call in method.filter(javalang.tree.MethodInvocation):
            if not _is_getter(call.member) or not call.selectors:
                continue
            # A selector chain on a getter's result is the dereference: `getX().y()`
            # evaluates `getX()` and immediately calls into whatever it returned.
            if (call.qualifier or "", call.member) in guarded:
                continue
            first = next((getattr(s, "member", None) for s in call.selectors
                          if getattr(s, "member", None)), None)
            if not first:
                continue
            qualifier = f"{call.qualifier}." if call.qualifier else ""
            out.append({
                "method": method.name,
                "expression": f"{qualifier}{call.member}().{first}()",
                "line": (call.position.line if call.position else 0),
            })
    return out


def findings(source: str, rel: str, cls: str, lines: list) -> list:
    """Radar findings for one file. [1.30]"""
    out = []
    for hit in find_unguarded(source):
        out.append({
            "rule": "UNGUARDED_NULL", "severity": "high", "file": rel,
            "line": hit["line"], "source_class": cls,
            "hazard": f"`{hit['expression']}` in `{hit['method']}()` dereferences a "
                      "getter's result, and nothing in that method checks it against "
                      "null. A Hybris model getter returns null freely for an unset "
                      "attribute; the migrated Apex throws a NullPointerException at "
                      "*runtime*, so this passes every static check, deploys cleanly, and "
                      "fails on the first record with an empty field.",
            "fix": "Guard it, or establish that the attribute is mandatory — an "
                   "items.xml `optional=\"false\"` makes this safe and is worth recording "
                   "as the reason. The same class already guards other getters this way, "
                   "which is usually the quickest thing to copy.",
            "snippet": (lines[hit["line"] - 1].strip()[:120]
                        if 0 < hit["line"] <= len(lines) else ""),
        })
    return out
