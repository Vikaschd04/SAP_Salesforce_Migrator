"""
php_phpunit_mining.py — the source half of characterization, for PHPUnit. [2.9]

The Java miner's argument applies unchanged here: a customer's existing test suite is a
recorded log of how their system actually behaved, and
`assertEquals(180.00, $svc->applySpendDiscount(200.00))` is not an opinion — it is a fact
about the old system, checked in and CI-verified for years.

What differs is everything about *reading* it. PHPUnit puts assertions on `$this`, records
an expected exception with `expectException()` before the call rather than in an
annotation, and has no `BigDecimal` — money is a float literal, which is itself a fact
worth carrying, because the Hybris target will hold it in `BigDecimal` and therefore
disagree with the recording in the last cent.

The output shape is byte-identical to the Java miner's, because the neutral layer above
both must not care which platform recorded the behaviour. That is the whole point of the
1.13 split: mining is source-side, and everything downstream reads one shape.
"""

from __future__ import annotations

import re

from src.characterize import behavior_id

_EQ = {"assertEquals", "assertSame", "assertEqualsWithDelta"}
_TRUTHY = {"assertTrue"}
_FALSY = {"assertFalse"}
_NULLY = {"assertNull"}
_ALL_ASSERTS = (_EQ | _TRUTHY | _FALSY | _NULLY |
                {"assertNotEquals", "assertNotNull", "assertNotSame", "assertCount",
                 "assertInstanceOf", "assertThat", "assertStringContainsString",
                 "expectException", "expectExceptionMessage"})

_TRUE = {"source": "true", "kind": "bool", "value": "true"}
_FALSE = {"source": "false", "kind": "bool", "value": "false"}
_NULL = {"source": "null", "kind": "null", "value": "null"}


def _txt(node) -> str:
    return node.text.decode("utf-8", "replace") if node is not None else ""


def _kids(node, *types):
    return [c for c in node.children if c.type in types]


def _first(node, *types):
    return next((c for c in node.children if c.type in types), None)


def _value(node) -> dict:
    """A PHP expression as a recorded value, or marked unrepresentable.

    `value is None` means the fact is an object graph, a variable or a call — something no
    target can restate as a literal. That judgement is made here, once, exactly as on the
    Java side.
    """
    if node is None:
        return dict(_NULL)
    raw = _txt(node)
    kind = node.type

    if kind == "float":
        return {"source": raw, "kind": "decimal", "value": raw}
    if kind == "integer":
        return {"source": raw, "kind": "number", "value": raw}
    if kind in ("string", "encapsed_string"):
        return {"source": raw, "kind": "string", "value": raw[1:-1]}
    if kind == "boolean":
        return {"source": raw, "kind": "bool", "value": raw.lower()}
    if kind == "null":
        return {"source": raw, "kind": "null", "value": "null"}

    # -1.00 / +3 — the sign belongs to the literal, not to an expression we cannot read.
    if kind == "unary_op_expression":
        inner = _first(node, "float", "integer")
        if inner is not None and raw.startswith(("-", "+")):
            v = _value(inner)
            return {"source": raw, "kind": v["kind"], "value": raw.replace(" ", "")}

    # A class constant used as an enum-ish value: Tier::GOLD
    if kind == "class_constant_access_expression":
        parts = [_txt(n) for n in _kids(node, "name", "qualified_name")]
        if len(parts) == 2 and parts[1] != "class":
            return {"source": raw, "kind": "enum", "value": parts[1]}

    return {"source": raw, "kind": kind, "value": None}


def _call_name(call) -> str:
    """The method name of a member_call_expression — the last bare `name` child."""
    names = _kids(call, "name")
    return _txt(names[-1]) if names else ""


def _args(call) -> list:
    args = _first(call, "arguments")
    if args is None:
        return []
    out = []
    for a in _kids(args, "argument"):
        inner = next((c for c in a.children if c.is_named), None)
        out.append(inner if inner is not None else a)
    return out


def _target_call(node):
    """The call under test inside an assertion argument — not the assertion itself."""
    if node is None:
        return None
    if node.type == "member_call_expression" and _call_name(node) not in _ALL_ASSERTS:
        return node
    for c in node.children:
        found = _target_call(c)
        if found is not None:
            return found
    return None


def _receiver(call) -> str:
    """`$this->service->applyX(...)` → "service". Names the collaborator under test."""
    recv = _first(call, "member_access_expression")
    if recv is None:
        return ""
    names = _kids(recv, "name")
    return _txt(names[-1]) if names else ""


def _readable(name: str) -> str:
    """testSpendDiscountAppliesTenPercentOverThreshold → readable prose."""
    s = re.sub(r"^(test|should|it)", "", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    return (s[:1].upper() + s[1:]).replace("_", " ").strip()


def _walk(node, wanted, out):
    if node.type == wanted:
        out.append(node)
    for c in node.children:
        _walk(c, wanted, out)
    return out


def mine(test_classes: list) -> list:
    """Every recorded input→output fact in a set of PHPUnit classes.

    `test_classes` are dicts with `class_name` and `source`, the same contract the Java
    miner takes — the neutral layer hands both the same thing.
    """
    from src.adapters.php_reader import _parser

    out: list = []
    for tc in test_classes or []:
        src = (tc.get("source") or "")
        if not src.strip():
            continue
        try:
            tree = _parser().parse(src.encode("utf-8"))
        except Exception:
            continue

        cls_name = tc.get("class_name", "")
        under_test = re.sub(r"(Test|TestCase)$", "", cls_name)

        for m in _walk(tree.root_node, "method_declaration", []):
            name = _txt(_first(m, "name"))
            if not name.startswith("test"):
                continue

            calls = _walk(m, "member_call_expression", [])

            # PHPUnit records an expected rejection by declaring it *before* the call,
            # so the whole method body has to be seen before any assertion is read.
            expects = None
            for c in calls:
                if _call_name(c) == "expectException":
                    a = _args(c)
                    if a:
                        hit = re.search(r"(\w+Exception|\w+Error)", _txt(a[0]))
                        expects = hit.group(1) if hit else _txt(a[0])
                    break

            n = 0
            for c in calls:
                member = _call_name(c)
                if member not in _ALL_ASSERTS or member == "expectException":
                    continue
                args = _args(c)
                if member in _EQ and len(args) >= 2:
                    expected, actual = _value(args[0]), args[1]
                elif member in _TRUTHY and args:
                    expected, actual = dict(_TRUE), args[-1]
                elif member in _FALSY and args:
                    expected, actual = dict(_FALSE), args[-1]
                elif member in _NULLY and args:
                    expected, actual = dict(_NULL), args[-1]
                else:
                    continue

                call = _target_call(actual)
                if call is None:
                    continue
                n += 1
                out.append({
                    "id": behavior_id(cls_name, name, n),
                    "test_class": cls_name, "test_method": name,
                    "label": _readable(name),
                    "source_class": _receiver(call) and under_test or under_test,
                    "target_method": _call_name(call),
                    "args": [_value(a) for a in _args(call)],
                    "expected": expected,
                    "expects_exception": expects,
                })

            # A test whose whole point is the rejection has no assertion to mine.
            if expects and n == 0:
                for c in calls:
                    if _call_name(c) in _ALL_ASSERTS:
                        continue
                    out.append({
                        "id": behavior_id(cls_name, name, 1),
                        "test_class": cls_name, "test_method": name,
                        "label": _readable(name), "source_class": under_test,
                        "target_method": _call_name(c),
                        "args": [_value(a) for a in _args(c)],
                        "expected": None, "expects_exception": expects,
                    })
                    break
    return out
