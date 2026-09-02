"""
java_junit_mining.py — the source half of characterization: JUnit → recorded facts.

Reading a customer's test suite is a *source-platform* skill. Knowing that
`new BigDecimal("200.00")` is a decimal literal, that `@Test(expected = ...)` records a
rejection, and that `DefaultOrderServiceTest` characterises `DefaultOrderService` are all
facts about Java and JUnit. None of them are facts about Salesforce, and an Adobe Commerce
source (PHPUnit) will need its own answers to the same three questions.

So this module owns them, and hands the neutral layer a **recorded value**:

    {"source": 'new BigDecimal("200.00")',   # verbatim, for the report
     "kind":   "decimal",                    # what sort of thing it is
     "value":  "200.00"}                     # the fact, in canonical form

`value is None` means the fact is an object graph or a live reference — something no
target can restate as a literal, which is why that judgement is made here, once, rather
than in every emitter. What the literal *looks like* in the target language is the
target's business (see `adapters/apex_characterization.py`); this module never decides it.
"""

from __future__ import annotations

import re

import javalang

from src.characterize import behavior_id

# Assertion helpers we understand, and what they mean.
_EQ = {"assertEquals", "assertSame"}
_TRUTHY = {"assertTrue"}
_FALSY = {"assertFalse"}
_NULLY = {"assertNull"}
_NOT_NULLY = {"assertNotNull"}
_ALL_ASSERTS = _EQ | _TRUTHY | _FALSY | _NULLY | _NOT_NULLY | {"assertNotEquals", "assertThat"}

# Java wrapper constructions that carry a plain value.
_BOXES = {"BigDecimal", "Integer", "Long", "Double", "Float", "Boolean", "String", "BigInteger"}

_TRUE = {"source": "true", "kind": "bool", "value": "true"}
_FALSE = {"source": "false", "kind": "bool", "value": "false"}
_NULL = {"source": "null", "kind": "null", "value": "null"}


def _value(node) -> dict:
    """Turn an AST expression into a recorded value, or mark it unrepresentable.

    `value` is None whenever the fact cannot be stated as a literal without inventing
    something — which is the signal that a behaviour needs an adapter or a human.
    """
    if node is None:
        return dict(_NULL)

    if isinstance(node, javalang.tree.Literal):
        raw = node.value
        if raw == "null":
            return {"source": raw, "kind": "null", "value": "null"}
        if raw.startswith(("'", '"')):
            return {"source": raw, "kind": "string", "value": raw[1:-1]}
        if raw in ("true", "false"):
            return {"source": raw, "kind": "bool", "value": raw}
        num = raw.rstrip("LlDdFf")
        if re.fullmatch(r"-?\d+(\.\d+)?", num):
            return {"source": raw, "kind": "number", "value": num}
        return {"source": raw, "kind": "other", "value": None}

    # new BigDecimal("200.00") / new Integer(5) — the box is Java plumbing; the fact
    # inside it is the number, so the box is unwrapped here rather than in every target.
    if isinstance(node, javalang.tree.ClassCreator):
        name = getattr(node.type, "name", "")
        args = node.arguments or []
        if name in _BOXES and len(args) == 1:
            inner = _value(args[0])
            if inner["value"] is not None:
                return {"source": f"new {name}({inner['source']})",
                        "kind": "decimal" if name == "BigDecimal" else inner["kind"],
                        "value": inner["value"]}
        return {"source": f"new {name}(...)", "kind": "object", "value": None}

    # Integer.valueOf(5) / BigDecimal.valueOf(2)
    if isinstance(node, javalang.tree.MethodInvocation):
        if node.member == "valueOf" and len(node.arguments or []) == 1:
            inner = _value(node.arguments[0])
            if inner["value"] is not None:
                return {"source": f"{node.qualifier}.valueOf({inner['source']})",
                        "kind": inner["kind"], "value": inner["value"]}
        return {"source": f"{node.qualifier or ''}.{node.member}(...)", "kind": "call", "value": None}

    # BigDecimal.ZERO, OrderStatus.NEW, LoyaltyTier.GOLD
    if isinstance(node, javalang.tree.MemberReference):
        q, m = node.qualifier or "", node.member
        if q == "BigDecimal" and m in ("ZERO", "ONE", "TEN"):
            return {"source": f"BigDecimal.{m}", "kind": "decimal",
                    "value": {"ZERO": "0", "ONE": "1", "TEN": "10"}[m]}
        if q and q[:1].isupper():
            return {"source": f"{q}.{m}", "kind": "enum", "value": m}
        return {"source": m, "kind": "variable", "value": None}

    return {"source": type(node).__name__, "kind": "complex", "value": None}


def _target_call(node):
    """Find the method call under test inside an assertion argument."""
    if isinstance(node, javalang.tree.MethodInvocation) and node.member not in _ALL_ASSERTS:
        return node
    for _, sub in node.filter(javalang.tree.MethodInvocation) if hasattr(node, "filter") else []:
        if sub.member not in _ALL_ASSERTS:
            return sub
    return None


def _readable(name: str) -> str:
    """testGoldCustomersGetTwelvePercentOff → 'gold customers get twelve percent off'."""
    s = re.sub(r"^(test|should)", "", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    return (s[:1].upper() + s[1:]).replace("_", " ").strip()


def mine(test_classes: list[dict]) -> list[dict]:
    """Extract every recorded input→output fact from a set of JUnit classes."""
    out: list[dict] = []
    for tc in test_classes or []:
        src = tc.get("source") or ""
        try:
            tree = javalang.parse.parse(src)
        except Exception:
            continue
        cls_name = tc.get("class_name", "")
        # DefaultOrderServiceTest → DefaultOrderService, the class it characterises.
        under_test = re.sub(r"(Test|Tests|TestCase|IT)$", "", cls_name)

        for _, m in tree.filter(javalang.tree.MethodDeclaration):
            anns = {(a.name or "").split(".")[-1]: a for a in (m.annotations or [])}
            if "Test" not in anns:
                continue

            # @Test(expected = IllegalArgumentException.class) — a recorded *rejection*.
            expects = None
            el = getattr(anns["Test"], "element", None)
            if el is not None:
                txt = str(el)
                hit = re.search(r"name=(\w+Exception)", txt) or re.search(r"(\w+Exception)", txt)
                if hit:
                    expects = hit.group(1)

            n = 0
            for _, inv in m.filter(javalang.tree.MethodInvocation):
                if inv.member not in _ALL_ASSERTS:
                    continue
                args = inv.arguments or []
                expected, actual = None, None
                if inv.member in _EQ and len(args) >= 2:
                    expected, actual = _value(args[0]), args[1]
                elif inv.member in _TRUTHY and args:
                    expected, actual = dict(_TRUE), args[-1]
                elif inv.member in _FALSY and args:
                    expected, actual = dict(_FALSE), args[-1]
                elif inv.member in _NULLY and args:
                    expected, actual = dict(_NULL), args[-1]
                else:
                    continue

                call = _target_call(actual)
                if call is None:
                    continue
                n += 1
                out.append({
                    "id": behavior_id(cls_name, m.name, n),
                    "test_class": cls_name, "test_method": m.name,
                    "label": _readable(m.name),
                    "source_class": under_test,
                    "target_method": call.member,
                    "args": [_value(a) for a in (call.arguments or [])],
                    "expected": expected,
                    "expects_exception": expects,
                })

            # A test whose whole point is the exception has no assertion to mine.
            if expects and n == 0:
                for _, inv in m.filter(javalang.tree.MethodInvocation):
                    if inv.member in _ALL_ASSERTS:
                        continue
                    out.append({
                        "id": behavior_id(cls_name, m.name, 1),
                        "test_class": cls_name, "test_method": m.name,
                        "label": _readable(m.name), "source_class": under_test,
                        "target_method": inv.member,
                        "args": [_value(a) for a in (inv.arguments or [])],
                        "expected": None, "expects_exception": expects,
                    })
                    break
    return out
