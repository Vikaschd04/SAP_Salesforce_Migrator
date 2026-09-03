"""Recorded behaviour from a PHPUnit suite. [2.9]

The Java miner's argument applies unchanged: a customer's test suite is a recorded log of
how their system actually behaved, and `assertEquals(180.00, $svc->applySpendDiscount(200.00))`
is a fact about the old system, not an opinion about the new one.

What differs is the reading. PHPUnit puts assertions on `$this`, declares an expected
exception with `expectException()` *before* the call rather than in an annotation, and has
no BigDecimal — money is a float literal.

The output shape is asserted to match the Java miner's exactly, because the neutral layer
above both must not care which platform recorded the behaviour. That is the whole point of
the 1.13 split.
"""

import textwrap
from pathlib import Path

import pytest

from src.adapters.php_phpunit_mining import mine
from src.adapters.php_reader import available

pytestmark = pytest.mark.skipif(not available(), reason="tree-sitter-php not installed")

FIXTURE = (Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento" /
           "app/code/Acme/Loyalty/Test/Unit/Model/PricingServiceTest.php")


def _mine(src, cls="PricingServiceTest"):
    return mine([{"class_name": cls, "source": src}])


@pytest.fixture(scope="module")
def rows():
    return _mine(FIXTURE.read_text(encoding="utf-8"))


def test_every_recorded_behaviour_is_found(rows):
    assert len(rows) == 7


def test_the_class_under_test_is_derived_from_the_test_class_name(rows):
    assert {r["source_class"] for r in rows} == {"PricingService"}


def test_a_recorded_value_carries_source_kind_and_value(rows):
    r = next(r for r in rows if r["test_method"].startswith("testSpendDiscountApplies"))
    assert r["args"][0] == {"source": "200.00", "kind": "decimal", "value": "200.00"}
    assert r["expected"] == {"source": "180.00", "kind": "decimal", "value": "180.00"}


def test_a_float_literal_is_recorded_as_decimal_not_integer(rows):
    """It is money. A target holding it as an int would be wrong by the cents."""
    r = next(r for r in rows if r["target_method"] == "applyTierDiscount")
    assert all(a["kind"] in ("decimal", "string") for a in r["args"])


def test_an_integer_expectation_stays_an_integer(rows):
    r = next(r for r in rows if r["target_method"] == "pointsFor")
    assert r["expected"] == {"source": "199", "kind": "number", "value": "199"}


def test_a_string_argument_loses_its_quotes_but_not_its_kind(rows):
    r = next(r for r in rows if "Gold" in r["label"])
    assert r["args"][1] == {"source": "'GOLD'", "kind": "string", "value": "GOLD"}


def test_expect_exception_is_read_even_though_it_precedes_the_call(rows):
    """PHPUnit declares the rejection before the call, unlike JUnit's annotation."""
    r = next(r for r in rows if r["expects_exception"])
    assert r["expects_exception"] == "InvalidArgumentException"
    assert r["target_method"] == "applySpendDiscount"
    assert r["expected"] is None


def test_a_negative_literal_keeps_its_sign(rows):
    r = next(r for r in rows if r["expects_exception"])
    assert r["args"][0]["value"] == "-1.00"


def test_the_label_is_readable_prose(rows):
    r = next(r for r in rows if "Gold" in r["label"])
    assert r["label"] == "Gold Customers Get Twelve Percent Off"


def test_ids_are_stable_across_runs(rows):
    again = _mine(FIXTURE.read_text(encoding="utf-8"))
    assert [r["id"] for r in rows] == [r["id"] for r in again]


def test_the_shape_matches_the_java_miner_exactly(rows):
    """The neutral layer reads one shape. Two miners that drift break it silently."""
    from src.adapters.java_junit_mining import mine as java_mine

    java = java_mine([{"class_name": "FooTest", "source": textwrap.dedent("""\
        import org.junit.Test;
        public class FooTest {
            @Test public void testAddsUp() {
                org.junit.Assert.assertEquals(3, svc.add(1, 2));
            }
        }
        """)}])
    assert java, "the java fixture must mine something for this comparison to mean anything"
    assert set(rows[0]) == set(java[0])
    assert set(rows[0]["args"][0]) == set(java[0]["args"][0])


def test_a_value_we_cannot_restate_is_marked_rather_than_guessed():
    rows = _mine(textwrap.dedent("""\
        <?php
        class PricingServiceTest extends TestCase {
            public function testObjectResult(): void {
                $this->assertEquals($this->expectedOrder, $this->service->build(42));
            }
        }
        """))
    assert rows[0]["expected"]["value"] is None, "a variable is not a recorded literal"


def test_a_non_test_method_is_ignored():
    rows = _mine(textwrap.dedent("""\
        <?php
        class PricingServiceTest extends TestCase {
            private function helper(): void {
                $this->assertEquals(1, $this->service->x());
            }
        }
        """))
    assert rows == []


def test_the_adapter_exposes_it_through_the_characterization_seam():
    from src.adapters.adobe_source import ADAPTER

    rows = ADAPTER.mine_behaviours([{"class_name": "PricingServiceTest",
                                     "source": FIXTURE.read_text(encoding="utf-8")}])
    assert len(rows) == 7


def test_an_empty_suite_mines_nothing_without_raising():
    assert mine([]) == []
    assert mine([{"class_name": "X", "source": ""}]) == []
