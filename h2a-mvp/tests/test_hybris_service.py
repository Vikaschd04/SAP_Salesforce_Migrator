"""PHP units as Spring services a Hybris developer recognises. [3.2, 3.3]

The split is what these tests are mostly about: the package, the interface, every
signature, the wiring, the DAO's queries and the javadoc are *derived*; only the method
bodies are left for a model. Mixing those is how a generator starts inventing, and a
signature invented from a type nobody declared compiles and is wrong.
"""

from pathlib import Path

import pytest

from src.adapters.hybris_service import (UNRESOLVED, build_dao, build_implementation,
                                         build_interface, build_spring_beans, java_type,
                                         service_name)

MAGENTO = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")


@pytest.fixture(scope="module")
def model():
    from src.adapters.php_reader import available
    if not available():
        pytest.skip("tree-sitter-php not installed")
    from src.adapters.adobe_source import ADAPTER
    return ADAPTER.read(MAGENTO)


@pytest.fixture(scope="module")
def pricing(model):
    u = next(x for x in model.units if x.name == "PricingService")
    return build_interface(u, "com.acme.loyalty", model.extra["type_resolutions"]), \
        build_implementation(u, "com.acme.loyalty", model.extra["type_resolutions"])


# ── naming ────────────────────────────────────────────────────────────────────

def test_a_class_already_named_service_is_not_double_suffixed():
    assert service_name("PricingService") == "PricingService"
    assert service_name("AwardPointsObserver") == "AwardPointsObserverService"


def test_the_impl_follows_saps_default_prefix_convention(pricing):
    iface, impl = pricing
    assert "public interface PricingService" in iface
    assert "public class DefaultPricingService implements PricingService" in impl


# ── signatures are derived, never invented ────────────────────────────────────

def test_signatures_come_from_resolved_types(pricing):
    iface, _ = pricing
    assert "Double applySpendDiscount(Double subtotal)" in iface
    assert "Double applyTierDiscount(Double subtotal, String tier)" in iface
    assert "Integer pointsFor(Double subtotal)" in iface


def test_a_float_is_not_silently_promoted_to_bigdecimal(pricing):
    """PHP money is a float and Java money should be BigDecimal — but promoting it here
    would change arithmetic the recorded behaviours were measured against, and the
    migration would disagree with its own characterization for a reason nobody could see.
    The FLOAT_MONEY hazard is where that decision belongs."""
    iface, _ = pricing
    assert "BigDecimal applySpendDiscount" not in iface


def test_a_decimal_column_still_becomes_bigdecimal():
    """The source *declared* decimal there, so faithful and correct agree."""
    assert java_type("BigDecimal") == "java.math.BigDecimal"


def test_an_undeclared_type_is_marked_rather_than_guessed(model):
    u = next(x for x in model.units if x.name == "SubtotalPlugin")
    iface = build_interface(u, "com.acme.loyalty", model.extra["type_resolutions"])
    assert UNRESOLVED in iface
    assert "TYPE-UNRESOLVED: return, subject" in iface
    assert "Decide before implementing" in iface


def test_private_methods_stay_out_of_the_contract(pricing):
    iface, _ = pricing
    assert "scale(" not in iface, "a private helper is not part of the service contract"
    assert "thresholdForStore" not in iface


# ── documentation ─────────────────────────────────────────────────────────────

def test_the_php_docblock_is_carried_verbatim(pricing):
    """A model asked to summarise a docblock produces something shorter and less true.
    `/** */` means the same in both languages, so the honest transformation is none."""
    iface, _ = pricing
    assert "Orders of 200 or more get 10% off" in iface
    assert "GOLD takes 12%, SILVER 6%" in iface


def test_javadoc_continuation_lines_align(pricing):
    """Class-level javadoc sits at column 0, method-level at 4. Both must align their
    `*` under the second character of `/**`, which is what every Java formatter does."""
    iface, _ = pricing
    lines = iface.splitlines()
    for i, ln in enumerate(lines):
        if not ln.strip().startswith("*") or ln.strip().startswith("*/"):
            continue
        opener = next(lines[j] for j in range(i, -1, -1) if "/**" in lines[j])
        indent = len(opener) - len(opener.lstrip())
        assert ln.startswith(" " * (indent + 1) + "* "), repr(ln)


# ── bodies are left, and left loudly ──────────────────────────────────────────

def test_an_unmigrated_body_throws_rather_than_returning_a_default(pricing):
    """A method returning null would let the extension build and behave as though the
    rule had been migrated to "do nothing"."""
    _, impl = pricing
    assert impl.count("UnsupportedOperationException") == 3
    assert "TODO migrate: PricingService::applySpendDiscount" in impl


# ── wiring ────────────────────────────────────────────────────────────────────

def test_every_service_is_wired_as_a_bean(model):
    xml = build_spring_beans([u for u in model.units if u.name == "PricingService"],
                             "com.acme.loyalty", "acmeloyalty")
    import xml.etree.ElementTree as ET

    ET.fromstring(xml)
    assert 'class="com.acme.loyalty.service.impl.DefaultPricingService"' in xml
    assert 'alias="pricingService"' in xml


# ── the DAO ───────────────────────────────────────────────────────────────────

def test_the_dao_queries_the_way_a_hybris_developer_writes_it(model):
    dt = next(t for t in model.data_model.types if t.code == "acme_loyalty_account")
    dao = build_dao(dt, "com.acme.loyalty")
    assert "SELECT {i:pk} FROM {AcmeLoyaltyAccount AS i} WHERE {i:code} = ?code" in dao
    assert 'query.addQueryParameter("code", code)' in dao
    assert "flexibleSearchService.<AcmeLoyaltyAccountModel>search(query)" in dao


def test_the_dao_does_not_trip_our_own_hazard_rules(model):
    """QUERY_NO_LIMIT fires on an unbounded FlexibleSearch. Emitting one would be odd."""
    from src.radar import _java_findings

    dt = next(t for t in model.data_model.types if t.code == "acme_loyalty_account")
    assert "query.setCount(1);" in build_dao(dt, "com.acme.loyalty")


def test_the_dao_is_parameterised_not_concatenated(model):
    """String-built FlexibleSearch is how injection arrives on this platform."""
    dt = next(t for t in model.data_model.types if t.code == "acme_loyalty_account")
    dao = build_dao(dt, "com.acme.loyalty")
    assert '" + ' not in dao and "' + " not in dao
