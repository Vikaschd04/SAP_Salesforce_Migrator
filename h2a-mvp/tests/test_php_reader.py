"""PHP source into IR units. [2.3]

A real parser rather than regex, for the same reason the Java side uses javalang: what a
migration needs from a class — what it implements, what its constructor demands, what each
method promises to return — is exactly what regex gets wrong on the files that matter
most. A long Magento model with nested closures is where a pattern-matcher quietly returns
the wrong answer, and it is also where the business rules live.

The tests below are mostly about two commitments: docblocks survive, and an undeclared
type stays undeclared rather than becoming a guess.
"""

import textwrap
from pathlib import Path

import pytest

from src import ir
from src.adapters.php_reader import available, read_file, read_tree

MAGENTO = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")

pytestmark = pytest.mark.skipif(not available(), reason="tree-sitter-php not installed")


@pytest.fixture(scope="module")
def units():
    return {u.name: u for u in read_tree(MAGENTO)}


def test_every_class_interface_and_trait_is_found(units):
    assert {"PricingService", "PricingServiceInterface", "OrderTotalPlugin",
            "AwardPointsObserver", "ExpirePoints", "AddLoyaltyAttributes"} <= set(units)


def test_the_namespace_and_fqn_are_recorded(units):
    svc = units["PricingService"]
    assert svc.extra["namespace"] == "Acme\\Loyalty\\Model"
    assert svc.extra["fqn"] == "Acme\\Loyalty\\Model\\PricingService"


def test_an_interface_is_distinguished_from_a_class(units):
    assert units["PricingServiceInterface"].extra["kind"] == "interface"
    assert units["PricingService"].extra["kind"] == "class"


def test_implemented_interfaces_are_captured(units):
    assert "PricingServiceInterface" in units["PricingService"].referenced_types


def test_the_layer_comes_from_magento_directory_convention(units):
    """PHP has no annotation saying what a class is; the path is the only declaration."""
    assert units["PricingService"].layer == "Model"
    assert units["OrderTotalPlugin"].layer == "Plugin"
    assert units["AwardPointsObserver"].layer == "Observer"
    assert units["ExpirePoints"].layer == "Cron"
    assert units["PricingServiceInterface"].layer == "Api"


def test_method_signatures_carry_parameter_and_return_types(units):
    m = next(m for m in units["PricingService"].methods if m.name == "applyTierDiscount")
    assert m.return_type == "float"
    assert [(p["type"], p["name"]) for p in m.parameters] == [("float", "subtotal"),
                                                              ("string", "tier")]


def test_a_nullable_type_is_kept_as_written(units):
    m = next(m for m in units["PricingService"].methods if m.name == "thresholdForStore")
    assert m.parameters[0]["type"] == "?int"


def test_visibility_is_read(units):
    by_name = {m.name: m for m in units["PricingService"].methods}
    assert by_name["applySpendDiscount"].visibility == "public"
    assert by_name["scale"].visibility == "private"


def test_docblocks_are_kept_verbatim(units):
    """On a dynamically typed source the docblock is often the only statement of intent."""
    m = next(m for m in units["PricingService"].methods if m.name == "applySpendDiscount")
    assert "200 or more get 10% off" in m.doc
    assert m.doc.startswith("/**")


def test_an_undeclared_return_type_stays_empty_never_guessed(tmp_path):
    """"" means unknown and routes to must-review. A guess compiles and is wrong."""
    f = tmp_path / "Untyped.php"
    f.write_text("<?php\nclass Untyped {\n  public function whatever($x) { return $x; }\n}\n",
                 encoding="utf-8")
    m = read_file(str(f), str(tmp_path))[0].methods[0]
    assert m.return_type == ""
    assert m.parameters[0]["type"] == ""


def test_constructor_promoted_properties_are_marked(tmp_path):
    f = tmp_path / "Promoted.php"
    f.write_text("<?php\nclass Promoted {\n"
                 "  public function __construct(private readonly int $count) {}\n}\n",
                 encoding="utf-8")
    p = read_file(str(f), str(tmp_path))[0].methods[0].parameters[0]
    assert p["name"] == "count" and p["promoted"] is True


def test_typed_properties_are_read(units):
    props = {p["name"]: p["type"] for p in units["PricingService"].fields}
    assert props["discountThreshold"] == "float"
    assert props["scopeConfig"] == "ScopeConfigInterface"


def test_methods_carry_their_line_range(units):
    m = next(m for m in units["PricingService"].methods if m.name == "applySpendDiscount")
    assert 0 < m.line_start < m.line_end


def test_a_static_method_is_marked(units):
    m = next(m for m in units["AddLoyaltyAttributes"].methods
             if m.name == "getDependencies")
    assert m.is_static is True


def test_a_php_file_with_no_class_is_recorded_not_dropped(units):
    """registration.php is real code. "No class here" is a fact; absence is not."""
    reg = units["registration"]
    assert reg.layer == "Script" and reg.extra["kind"] == "script"


def test_a_test_class_is_flagged_as_one(units):
    assert units["PricingServiceTest"].is_test is True
    assert units["PricingService"].is_test is False


def test_an_unparseable_file_reaches_the_ledger_rather_than_vanishing(tmp_path):
    f = tmp_path / "Broken.php"
    f.write_bytes(b"\xff\xfe\x00\x00 not php at all {{{")
    units = read_file(str(f), str(tmp_path))
    assert len(units) == 1
    assert units[0].unreadable, "a file we cannot read must still produce a row"


def test_a_file_with_recoverable_syntax_errors_is_still_read(tmp_path):
    """tree-sitter recovers. Discarding real code over a syntax error would lose more."""
    f = tmp_path / "Sloppy.php"
    f.write_text("<?php\nclass Sloppy {\n  public function ok(): int { return 1; }\n"
                 "  public function bad( { }\n}\n", encoding="utf-8")
    got = read_file(str(f), str(tmp_path))
    assert any(u.name == "Sloppy" for u in got)
    assert any("syntax errors" in (u.unreadable or "") for u in got)


def test_vendor_is_not_read(tmp_path):
    v = tmp_path / "vendor" / "m"
    v.mkdir(parents=True)
    (v / "X.php").write_text("<?php class X {}", encoding="utf-8")
    assert read_tree(str(tmp_path)) == []


def test_units_are_ir_types(units):
    assert isinstance(units["PricingService"], ir.SourceUnit)
    assert isinstance(units["PricingService"].methods[0], ir.Method)
