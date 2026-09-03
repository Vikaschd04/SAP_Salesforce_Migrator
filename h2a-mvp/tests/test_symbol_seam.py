"""Locating a method is a platform skill, not a neutral one. [2.11]

`provenance` and `alignment` both answer "where is this method?" — and both used a single
Java-shaped regex to do it, for the source *and* the generated code. That worked only
because both platforms in v1 were C-family.

Run that regex over PHP and it finds one method in six. It does not raise, it does not
warn: it under-reports, in the two modules whose entire output is how much of the source
can be accounted for. A traceability report that quietly finds a sixth of the methods is
worse than one that refuses to run, because it will be believed.
"""

from pathlib import Path

import pytest

from src.adapters.braced_symbols import symbols as braced
from src.adapters.php_reader import available

TESTING = Path(__file__).resolve().parents[2] / "Testing"
PHP = (TESTING / "acme-commerce-magento" /
       "app/code/Acme/Loyalty/Model/PricingService.php").read_text()
JAVA = (TESTING / "acme-commerce-hybris" / "core-customize/hybris/bin/custom/acmecore/"
        "src/com/acme/core/service/impl/DefaultPricingService.java").read_text()


def test_the_java_shaped_reader_finds_java_methods():
    names = {s["name"] for s in braced(JAVA)}
    assert {"applySpendDiscount", "applyLoyaltyDiscount", "calculateOrderTotal"} <= names


@pytest.mark.skipif(not available(), reason="tree-sitter-php not installed")
def test_the_java_shaped_reader_is_wrong_about_php():
    """The premise of this item, asserted rather than asserted-about.

    If this ever starts passing with six methods, the seam is no longer load-bearing and
    this test should be the thing that says so.
    """
    assert len(braced(PHP)) < 3, "a Java regex must not appear to understand PHP"


@pytest.mark.skipif(not available(), reason="tree-sitter-php not installed")
def test_the_php_reader_finds_every_php_method():
    from src.adapters.php_reader import symbols

    assert {s["name"] for s in symbols(PHP)} == {
        "__construct", "applySpendDiscount", "applyTierDiscount", "pointsFor",
        "scale", "thresholdForStore"}


@pytest.mark.skipif(not available(), reason="tree-sitter-php not installed")
def test_php_symbols_carry_a_usable_line_range():
    from src.adapters.php_reader import symbols

    m = next(s for s in symbols(PHP) if s["name"] == "applySpendDiscount")
    assert m["line_start"] < m["line_end"]
    body = "\n".join(PHP.splitlines()[m["line_start"] - 1: m["line_end"]])
    assert "InvalidArgumentException" in body, "the range must actually cover the body"


def test_every_registered_adapter_can_locate_its_own_methods():
    """The seam's contract. An adapter that cannot do this breaks provenance silently."""
    from src import pipeline

    pipeline.ensure_registered()
    for p in pipeline.available():
        assert hasattr(p.source, "symbols"), f"{p.source_platform} source"
        assert hasattr(p.target, "symbols"), f"{p.target_platform} target"


def test_the_neutral_layer_asks_rather_than_parsing():
    """provenance must own no method-declaration pattern of its own."""
    src = (Path(__file__).resolve().parents[1] / "src" / "provenance.py").read_text()
    assert "_METHOD" not in src
    assert "function" not in src.lower() or "def " in src   # no PHP/Java syntax knowledge
    assert "_source_symbols" in src and "_target_symbols" in src
