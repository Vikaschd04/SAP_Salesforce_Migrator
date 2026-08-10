"""Semantic alignment: intent · implementation · proof on one row."""

from src.agentic.blackboard import Blackboard, Artifact
from src.alignment import build_alignment, headline, write_alignment_md

JAVA = """public class DefaultPricingService {
    public BigDecimal applySpendDiscount(final BigDecimal subtotal) {
        if (subtotal.compareTo(THRESHOLD) < 0) { return subtotal; }
        return subtotal.subtract(subtotal.multiply(RATE));
    }
    public BigDecimal applyPromoCode(final BigDecimal subtotal, final String code) {
        return subtotal;
    }
}"""
APEX = """public with sharing class PricingService {
    public Decimal applySpendDiscount(Decimal subtotal) {
        return subtotal;
    }
    public Decimal applyPromoCode(Decimal subtotal, String code) {
        return subtotal;
    }
}"""

R_SPEND = "Orders above the spend threshold receive a discount"
R_PROMO = "A promo code never reduces a subtotal below zero"
R_ALIEN = "Refunds are denied after 30 days"


def bb(rules=(R_SPEND,), behaviours=(), verdicts=(), apex=APEX, java=JAVA):
    b = Blackboard("in", "out")
    b.artifacts = [Artifact(target_name="PricingService", layer="Service", main_class=apex,
                            source_classes=[{"class_name": "DefaultPricingService",
                                             "file": "x.java", "source": java}])]
    b.comprehensions = {"DefaultPricingService": {"business_rules": list(rules)}}
    b.characterization = {"behaviors": list(behaviours)}
    b.rule_ledger = {"rules": list(verdicts)}
    return b


def rows(b):
    return {r["rule"]: r for r in build_alignment(b)["rows"]}


def test_a_rule_is_traced_to_the_method_that_implements_it():
    r = rows(bb())[R_SPEND]
    assert r["java_method"] == "applySpendDiscount"
    assert r["apex_method"] == "applySpendDiscount"
    assert r["apex_lines"] == [2, 4] and r["link_confidence"] == "high"


def test_a_replayed_behaviour_is_the_strongest_proof():
    r = rows(bb(behaviours=[{"id": "B-001", "label": "spend discount applies",
                             "target_method": "applySpendDiscount", "mode": "direct"}]))[R_SPEND]
    assert r["proof_kind"] == "replayed" and "B-001" in r["proof"]


def test_an_asserted_rule_falls_back_to_the_ledger_verdict():
    r = rows(bb(rules=[R_PROMO], verdicts=[{"rule": R_PROMO, "status": "asserted"}]))[R_PROMO]
    assert r["proof_kind"] == "asserted"


def test_a_replayed_behaviour_outranks_a_keyword_match():
    r = rows(bb(behaviours=[{"id": "B-001", "label": "x", "target_method": "applySpendDiscount",
                             "mode": "direct"}],
                verdicts=[{"rule": R_SPEND, "status": "asserted"}]))[R_SPEND]
    assert r["proof_kind"] == "replayed"


def test_a_rule_with_no_matching_method_says_so_rather_than_guessing():
    """A plausible chain built on a bad match would be worse than an incomplete one,
    because it would be believed."""
    r = rows(bb(rules=[R_ALIEN]))[R_ALIEN]
    assert r["apex_method"] is None
    assert "carried by the class as a whole" in r["broken_at"]


def test_a_rule_whose_class_produced_nothing_reports_that():
    b = bb()
    b.artifacts = []
    r = rows(b)[R_SPEND]
    assert r["broken_at"] == "no artifact carries this class"


def test_a_method_with_no_apex_counterpart_breaks_the_chain_explicitly():
    stripped = "public with sharing class PricingService {\n}"
    r = rows(bb(apex=stripped))[R_SPEND]
    assert r["apex_method"] is None
    assert "no traceable counterpart" in r["broken_at"]


def test_the_summary_counts_alignment_and_proof_separately():
    s = build_alignment(bb(rules=[R_SPEND, R_PROMO, R_ALIEN],
                           behaviours=[{"id": "B-001", "label": "x",
                                        "target_method": "applySpendDiscount", "mode": "direct"}],
                           verdicts=[{"rule": R_PROMO, "status": "asserted"}]))["summary"]
    assert s["rules"] == 3 and s["aligned"] == 2 and s["proven"] == 2 and s["replayed"] == 1
    assert s["broken"] == 1


def test_unaligned_rules_sort_to_the_top():
    r = build_alignment(bb(rules=[R_SPEND, R_ALIEN]))["rows"]
    assert r[0]["rule"] == R_ALIEN, "the rows that need attention must lead"


def test_no_rules_does_not_claim_success():
    s = build_alignment(bb(rules=[]))["summary"]
    assert s["rules"] == 0 and "No business rules to align" in headline(s)


def test_the_report_names_the_weakest_link(tmp_path):
    al = build_alignment(bb(rules=[R_SPEND, R_ALIEN]))
    text = open(write_alignment_md(str(tmp_path), al), encoding="utf-8").read()
    assert "intent · implementation · proof" in text
    assert "keyword overlap" in text and "weakest" in text
    assert "Not a text diff" in text
