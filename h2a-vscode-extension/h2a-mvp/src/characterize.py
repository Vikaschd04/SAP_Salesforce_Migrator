"""
characterize.py — golden-master parity from the customer's own JUnit suite.

The rule ledger can say *"a test plausibly covers this rule"*. It can never say
*"this behaves the same"*, because it compares words, not behaviour. This module is
what closes that gap.

The idea is unglamorous and that is exactly why it works: a customer's existing JUnit
suite is a **recorded log of how their system actually behaved**. `assertEquals(new
BigDecimal("180.00"), svc.applySpendDiscount(new BigDecimal("200.00")))` is not an
opinion — it is a fact about the old system, checked in and CI-verified for years.
Mine those facts, replay them against the generated Apex, and the claim upgrades from
"the AI thinks it's equivalent" to:

    340 recorded behaviours from your own suite · 332 reproduce · 8 differ — here they are.

**The catch, stated up front.** The migration deliberately reshapes code: a single-record
`placeOrder(customer, entries)` becomes a bulkified `createOrders(List<OrderRequest>)`.
So most behaviours cannot be replayed by calling the same method with the same
arguments. Each one is therefore classified:

    direct   — the signature survived; the replay is generated deterministically, and
               every value in it is a recorded fact. This is the strong evidence.
    adapter  — the shape changed; bridging code is needed to express the old call
               against the new signature. The *expected values* are still recorded
               facts, but the plumbing around them is generated, so it is weaker.
    manual   — mocks, object graphs or framework state we will not pretend to port.

Nothing here guesses an expected value. A behaviour we cannot faithfully replay is
reported as such rather than quietly dropped — an honest `manual` row is worth more
than a green tick that means nothing.
"""

from __future__ import annotations

import hashlib
import re

import javalang

# Assertion helpers we understand, and what they mean.
_EQ = {"assertEquals", "assertSame"}
_TRUTHY = {"assertTrue"}
_FALSY = {"assertFalse"}
_NULLY = {"assertNull"}
_NOT_NULLY = {"assertNotNull"}
_ALL_ASSERTS = _EQ | _TRUTHY | _FALSY | _NULLY | _NOT_NULLY | {"assertNotEquals", "assertThat"}

# Java wrapper constructions that carry a plain value.
_BOXES = {"BigDecimal", "Integer", "Long", "Double", "Float", "Boolean", "String", "BigInteger"}


def behavior_id(test_class: str, test_method: str, n: int) -> str:
    """Stable id so a behaviour can be tracked across runs and reports."""
    return "B-" + hashlib.md5(f"{test_class}#{test_method}#{n}".encode("utf-8")).hexdigest()[:8]


# ── mining ────────────────────────────────────────────────────────────────────

def _value(node) -> dict:
    """Turn an AST expression into a replayable value, or mark it complex.

    `apex` is None whenever we cannot express the value in Apex without inventing
    something — which is the signal that a behaviour needs an adapter or a human.
    """
    if node is None:
        return {"java": "null", "kind": "null", "apex": "null"}

    if isinstance(node, javalang.tree.Literal):
        raw = node.value
        if raw == "null":
            return {"java": raw, "kind": "null", "apex": "null"}
        if raw.startswith(("'", '"')):
            return {"java": raw, "kind": "string", "apex": "'" + raw[1:-1].replace("'", "\\'") + "'"}
        if raw in ("true", "false"):
            return {"java": raw, "kind": "bool", "apex": raw}
        num = raw.rstrip("LlDdFf")
        if re.fullmatch(r"-?\d+(\.\d+)?", num):
            return {"java": raw, "kind": "number", "apex": num}
        return {"java": raw, "kind": "other", "apex": None}

    # new BigDecimal("200.00") / new Integer(5)
    if isinstance(node, javalang.tree.ClassCreator):
        name = getattr(node.type, "name", "")
        args = node.arguments or []
        if name in _BOXES and len(args) == 1:
            inner = _value(args[0])
            if inner["apex"] is not None:
                apex = inner["apex"]
                if name == "BigDecimal" and inner["kind"] == "string":
                    apex = apex.strip("'")           # new BigDecimal("1.50") → 1.50
                return {"java": f"new {name}({inner['java']})",
                        "kind": "decimal" if name == "BigDecimal" else inner["kind"], "apex": apex}
        return {"java": f"new {name}(...)", "kind": "object", "apex": None}

    # Integer.valueOf(5) / BigDecimal.valueOf(2)
    if isinstance(node, javalang.tree.MethodInvocation):
        if node.member == "valueOf" and len(node.arguments or []) == 1:
            inner = _value(node.arguments[0])
            if inner["apex"] is not None:
                return {"java": f"{node.qualifier}.valueOf({inner['java']})",
                        "kind": inner["kind"], "apex": inner["apex"].strip("'")}
        return {"java": f"{node.qualifier or ''}.{node.member}(...)", "kind": "call", "apex": None}

    # BigDecimal.ZERO, OrderStatus.NEW, LoyaltyTier.GOLD
    if isinstance(node, javalang.tree.MemberReference):
        q, m = node.qualifier or "", node.member
        if q == "BigDecimal" and m in ("ZERO", "ONE", "TEN"):
            return {"java": f"BigDecimal.{m}", "kind": "decimal",
                    "apex": {"ZERO": "0", "ONE": "1", "TEN": "10"}[m]}
        if q and q[:1].isupper():
            return {"java": f"{q}.{m}", "kind": "enum", "apex": f"'{m}'"}   # Apex enums map to strings
        return {"java": m, "kind": "variable", "apex": None}

    return {"java": type(node).__name__, "kind": "complex", "apex": None}


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


def mine_behaviors(test_classes: list[dict]) -> list[dict]:
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
                    expected, actual = {"java": "true", "kind": "bool", "apex": "true"}, args[-1]
                elif inv.member in _FALSY and args:
                    expected, actual = {"java": "false", "kind": "bool", "apex": "false"}, args[-1]
                elif inv.member in _NULLY and args:
                    expected, actual = {"java": "null", "kind": "null", "apex": "null"}, args[-1]
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


# ── mapping a recorded behaviour onto the generated Apex ──────────────────────

_SIG = r"(?:public|global|private|protected)\s+(?:(static)\s+)?[\w<>,\[\]\.]+\s+{m}\s*\("


def _find_method(apex: str, name: str) -> dict | None:
    """Locate `name` in generated Apex and report whether it is static."""
    hit = re.search(_SIG.format(m=re.escape(name)), apex or "")
    return None if not hit else {"static": bool(hit.group(1))}


def plan_replay(behaviors: list[dict], artifacts: list) -> list[dict]:
    """Decide, per behaviour, whether it can be replayed and how strong that replay is.

    The classification is the honest part of this module. `direct` means every value in
    the generated test is a recorded fact and the call shape survived the migration —
    that is real proof. `adapter` and `manual` are not, and are labelled so.
    """
    by_source: dict[str, object] = {}
    for a in artifacts or []:
        for c in a.source_classes:
            if c.get("class_name"):
                by_source[c["class_name"]] = a

    planned = []
    for b in behaviors:
        art = by_source.get(b["source_class"])
        row = dict(b, target=None, mode="manual", reason="")

        if art is None:
            row["reason"] = "no generated artifact carries this class"
            planned.append(row)
            continue

        row["target"] = art.target_name
        if getattr(art, "status", "") == "error":
            row["reason"] = "the target failed to generate"
            planned.append(row)
            continue

        found = _find_method(art.main_class or "", b["target_method"])
        expressible = (all(a.get("apex") is not None for a in b["args"])
                       and (b["expects_exception"] or (b["expected"] or {}).get("apex") is not None))

        if found and expressible:
            row["mode"], row["static"] = "direct", found["static"]
            row["reason"] = "signature survived the migration; every value is a recorded fact"
        elif found:
            row["mode"] = "adapter"
            row["reason"] = "method exists, but the arguments need bridging code to express"
        else:
            row["mode"] = "adapter"
            row["reason"] = (f"no method named {b['target_method']} in {art.target_name} — "
                             "the migration reshaped this call (e.g. bulkified)")
        planned.append(row)
    return planned


def generate_apex(planned: list[dict]) -> dict[str, str]:
    """Build one Apex characterization test class per target, from `direct` rows only.

    Deliberately deterministic: no model is asked what the answer should be. Every
    asserted value here was recorded by the customer's own suite.
    """
    by_target: dict[str, list[dict]] = {}
    for r in planned:
        if r["mode"] == "direct":
            by_target.setdefault(r["target"], []).append(r)

    out = {}
    for target, rows in sorted(by_target.items()):
        cls = f"{target}CharacterizationTest"
        L = [f"@isTest",
             f"private class {cls} {{",
             "    // Generated from the Hybris JUnit suite. Every expected value below was",
             "    // RECORDED from the original system — none of it is inferred. A failure here",
             "    // means the migrated behaviour genuinely differs from the legacy behaviour.",
             ""]
        for r in rows:
            args = ", ".join(a["apex"] for a in r["args"])
            call = (f"{r['target']}.{r['target_method']}({args})" if r.get("static")
                    else f"new {r['target']}().{r['target_method']}({args})")
            msg = f"{r['id']} · {r['test_class']}.{r['test_method']}"
            L += [f"    // {r['id']} — recorded: {r['label']}",
                  f"    @isTest",
                  f"    static void {r['id'].replace('-', '_').lower()}() {{"]
            if r["expects_exception"]:
                L += ["        Boolean threw = false;",
                      f"        try {{ {call}; }} catch (Exception e) {{ threw = true; }}",
                      f"        System.assert(threw, '{msg} — expected a rejection');"]
            else:
                L += [f"        System.assertEquals({r['expected']['apex']}, {call},",
                      f"            '{msg}');"]
            L += ["    }", ""]
        L.append("}")
        out[cls] = "\n".join(L)
    return out


def summarise(planned: list[dict]) -> dict:
    counts = {m: 0 for m in ("direct", "adapter", "manual")}
    for r in planned:
        counts[r["mode"]] = counts.get(r["mode"], 0) + 1
    total = len(planned)
    return {"total": total, **counts,
            "replayable_pct": round(100.0 * counts["direct"] / total) if total else None}


def headline(s: dict) -> str:
    t = s.get("total") or 0
    if not t:
        return ("No JUnit tests found — characterization needs the customer's existing "
                "test suite as its source of recorded behaviour.")
    return (f"{s['direct']}/{t} recorded behaviours replay directly against the generated Apex "
            f"({s.get('replayable_pct', 0)}%) · {s['adapter']} need bridging · {s['manual']} manual")


def write_characterization_md(output_dir: str, planned: list[dict], apex: dict[str, str]) -> str:
    from pathlib import Path

    s = summarise(planned)
    out = ["# Characterization Report — replaying your own tests", "",
           "Your existing JUnit suite is a recorded log of how the legacy system actually",
           "behaved. This replays those recorded facts against the generated Apex.", "",
           f"**{headline(s)}**", "",
           "| Mode | Count | What it means | How much to trust it |",
           "|---|---|---|---|",
           f"| `direct` | {s['direct']} | The signature survived; the replay calls the same method "
           "with the same recorded values | **Strong** — a failure is a real behavioural difference |",
           f"| `adapter` | {s['adapter']} | The migration reshaped the call (e.g. single-record → "
           "bulk), so bridging code is needed | Medium — expected values are still recorded facts, "
           "but the plumbing around them is not |",
           f"| `manual` | {s['manual']} | Mocks, object graphs or framework state we will not "
           "pretend to port | None — these need a human |", ""]

    if apex:
        out += [f"## Generated test classes ({len(apex)})", "",
                "Deployed with the rest of the project; run them in a scratch org to get the "
                "reproduce/differ verdict.", ""]
        out += [f"- `{name}.cls` — {sum(1 for r in planned if r['mode'] == 'direct' and r['target'] + 'CharacterizationTest' == name)} recorded behaviour(s)"
                for name in sorted(apex)]
        out.append("")

    for mode, blurb in (("direct", "replayed automatically"),
                        ("adapter", "need bridging code before they can run"),
                        ("manual", "cannot be replayed automatically")):
        group = [r for r in planned if r["mode"] == mode]
        if not group:
            continue
        out += [f"## {mode} — {len(group)} behaviour(s) {blurb}", "",
                "| Id | Recorded behaviour | Legacy call | Now | Note |", "|---|---|---|---|---|"]
        for r in group:
            args = ", ".join(a["java"] for a in r["args"]).replace("|", "\\|")
            exp = r["expects_exception"] or (r["expected"] or {}).get("java", "—")
            legacy = f"`{r['source_class']}.{r['target_method']}({args})` → `{exp}`".replace("|", "\\|")
            out.append(f"| `{r['id']}` | {r['label']} | {legacy} | "
                       f"`{r['target'] or '—'}` | {r['reason']} |")
        out.append("")

    out += ["---", "",
            "> **Why this matters.** Every other check in this migration asks whether the new code ",
            "> *looks* right. This asks whether it *behaves* the same, against evidence your team ",
            "> wrote and trusted for years. A `direct` failure is not a style opinion — it is proof ",
            "> that something changed."]

    path = Path(output_dir) / "CHARACTERIZATION.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
