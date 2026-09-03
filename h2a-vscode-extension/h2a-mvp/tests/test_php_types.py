"""Resolving PHP types from declarations, and refusing to invent the rest. [2.12]

PHP allows an untyped parameter and a `mixed` return. Java allows neither, so every gap
has to become *some* Java type before the target compiles — and there are exactly two ways
to fill it: find a declaration, or guess.

Guessing is the quiet failure. A guessed `String` compiles, the migration reports success,
the field deploys, and the mismatch appears the first time a real value flows through it —
by which point the guess is indistinguishable from a requirement. So a type is resolved
only from a declaration, and usage is deliberately not a source.
"""

from pathlib import Path

import pytest

from src.adapters.php_types import resolve, to_ir_type, unresolved_by_unit

MAGENTO = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")


class _M:
    def __init__(self, name, params=(), ret="", doc=""):
        self.name, self.parameters, self.return_type, self.doc = name, list(params), ret, doc


class _U:
    def __init__(self, name, methods=(), fields=()):
        self.name, self.methods, self.fields = name, list(methods), list(fields)


# ── the type map ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("php,ir", [
    ("float", "Double"), ("int", "Integer"), ("string", "String"), ("bool", "Boolean"),
    ("?float", "Double"),                      # nullability is a separate fact
    ("float|null", "Double"),                  # a union that is just T|null is T
    ("DateTimeImmutable", "DateTime"),
    ("Acme\\Loyalty\\Model\\Tier", "Tier"),    # a class keeps its short name
    ("string[]", "List"),
    ("void", "void"),                          # a declaration, not a gap
    ("mixed", ""), ("", ""), ("callable", ""), ("int|string", ""),
])
def test_php_types_map_to_the_ir(php, ir):
    assert to_ir_type(php) == ir


# ── authority ─────────────────────────────────────────────────────────────────

def test_a_declared_type_wins():
    u = _U("S", [_M("f", [{"name": "a", "type": "float"}], "int",
                    doc="/** @param string $a\n @return string */")])
    r = resolve([u])["resolutions"]
    assert [x for x in r if x["name"] == "a"][0] == {
        "where": "S::f($a)", "name": "a", "type": "Double", "via": "declared"}


def test_a_docblock_answers_where_the_signature_did_not():
    """PHP made authors write types in docblocks for years. That is still a declaration."""
    u = _U("S", [_M("f", [{"name": "a", "type": ""}], "",
                    doc="/** @param float $a\n * @return int */")])
    got = {x["name"]: x for x in resolve([u])["resolutions"]}
    assert got["a"]["type"] == "Double" and got["a"]["via"] == "docblock"
    assert got[""]["type"] == "Integer" and got[""]["via"] == "docblock"


def test_the_schema_answers_where_nothing_else_did():
    from src import ir

    dt = ir.DataType(code="t", attributes=[{"name": "points_balance", "type": "Integer"}])
    u = _U("S", fields=[{"name": "points_balance", "type": ""}])
    r = resolve([u], [dt])["resolutions"][0]
    assert r["type"] == "Integer" and r["via"] == "schema"


def test_a_schema_conflict_resolves_to_nothing():
    """Two columns of the same name and different types is not a fact about either."""
    from src import ir

    dts = [ir.DataType(code="a", attributes=[{"name": "code", "type": "Integer"}]),
           ir.DataType(code="b", attributes=[{"name": "code", "type": "String"}])]
    u = _U("S", fields=[{"name": "code", "type": ""}])
    assert resolve([u], dts)["unresolved"]


def test_usage_is_never_a_source():
    """`$x = $this->price * 2` strongly suggests a number. That is the trap."""
    u = _U("S", [_M("f", [{"name": "price", "type": ""}], "")])
    assert len(resolve([u])["unresolved"]) == 2, "param and return both stay unresolved"


# ── what counts as a gap ──────────────────────────────────────────────────────

def test_void_is_a_declaration_not_a_gap():
    """Counting it as unresolved sent every `execute(): void` to must-review."""
    u = _U("S", [_M("run", [], "void")])
    assert resolve([u])["unresolved"] == []


def test_a_constructor_return_is_not_a_gap():
    u = _U("S", [_M("__construct", [{"name": "a", "type": "int"}], "")])
    assert resolve([u])["unresolved"] == []


def test_declared_but_unmappable_is_reported_differently_from_undeclared():
    """One is a modelling decision, the other is a missing fact. Different questions."""
    u = _U("S", [_M("f", [{"name": "cb", "type": "callable"},
                          {"name": "x", "type": ""}], "void")])
    by_name = {x["name"]: x for x in resolve([u])["unresolved"]}
    assert "no single Java equivalent" in by_name["cb"]["reason"]
    assert "no declaration" in by_name["x"]["reason"]


# ── the fixture, and triage routing ───────────────────────────────────────────

def test_the_reference_project_resolves_what_it_declares():
    from src.adapters.magento_config import read_db_schema
    from src.adapters.php_reader import available, read_tree

    if not available():
        pytest.skip("tree-sitter-php not installed")
    res = resolve(read_tree(MAGENTO), read_db_schema(MAGENTO))
    assert len(res["resolutions"]) > 40
    assert all(r["via"] for r in res["resolutions"]), "a resolution must name its authority"
    # Magento plugin signatures are conventionally untyped; those are the real gaps.
    assert "SubtotalPlugin" in unresolved_by_unit(res)


def test_an_unresolved_type_forces_must_review():
    """Not a weight that happens to clear a threshold — a human decision, forced."""
    from src.agentic.blackboard import Artifact, Blackboard
    from src.triage import build_triage

    bb = Blackboard("in", "out")
    art = Artifact(target_name="SubtotalPlugin", layer="Utility")
    art.source_classes = [{"class_name": "SubtotalPlugin", "layer": "Utility"}]
    bb.artifacts = [art]
    bb.unresolved_types = {"SubtotalPlugin": ["SubtotalPlugin::beforeCollect($quote)"]}

    item = build_triage(bb)["items"][0]
    assert item["band"] == "must"
    assert any("no declaration resolves" in r for r in item["reasons"])


def test_a_fully_typed_artifact_is_not_forced():
    from src.agentic.blackboard import Artifact, Blackboard
    from src.triage import build_triage

    bb = Blackboard("in", "out")
    art = Artifact(target_name="PricingService", layer="Service")
    art.source_classes = [{"class_name": "PricingService", "layer": "Service"}]
    bb.artifacts = [art]
    bb.unresolved_types = {}
    assert build_triage(bb)["items"][0]["band"] != "must"
