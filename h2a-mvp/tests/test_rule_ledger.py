"""The business-rule ledger: every extracted rule gets a verdict, especially the lost ones."""

from src.agentic.blackboard import Blackboard, PlanItem, Artifact
from src.rule_ledger import build_rule_ledger, rule_id, headline, write_rules_md


def _bb():
    bb = Blackboard("in", "out")
    bb.comprehensions = {
        # asserted: the test names the discount threshold
        "DefaultPricingService": {"business_rules": [
            "Orders above 5000 receive a 10 percent discount",
        ]},
        # implemented: built, but the test asserts nothing about it
        "DefaultTaxService": {"business_rules": [
            "Tax is calculated per delivery region code",
        ]},
        # at_risk: its target blew up during generation
        "DefaultRefundService": {"business_rules": [
            "Refunds are denied after 30 days from delivery",
        ]},
        # dropped: the planner skipped the class, so nothing carries the rule
        "LegacyLoyaltyCalculator": {"business_rules": [
            "Gold tier customers accrue double loyalty points",
        ]},
    }
    bb.plan = [PlanItem(target_name="Skip:LegacyLoyaltyCalculator", layer="Service",
                        domain="Loyalty", target_kind="Skip",
                        rationale="dead code — no callers found",
                        source_classes=[{"class_name": "LegacyLoyaltyCalculator"}])]
    bb.artifacts = [
        Artifact(target_name="PricingService", layer="Service", status="ok",
                 source_classes=[{"class_name": "DefaultPricingService"}],
                 test_class="@isTest static void discountAboveThreshold() {"
                            " System.assertEquals(10, d, 'orders above 5000 get 10 percent discount'); }"),
        Artifact(target_name="TaxService", layer="Service", status="ok",
                 source_classes=[{"class_name": "DefaultTaxService"}],
                 test_class="@isTest static void smoke() { /* TODO */ }"),
        Artifact(target_name="RefundService", layer="Service", status="error",
                 source_classes=[{"class_name": "DefaultRefundService"}], test_class=""),
    ]
    return bb


def test_every_rule_gets_a_verdict():
    led = build_rule_ledger(_bb())
    got = {r["source"]: r["status"] for r in led["rules"]}
    assert got == {
        "DefaultPricingService": "asserted",
        "DefaultTaxService": "implemented",
        "DefaultRefundService": "at_risk",
        "LegacyLoyaltyCalculator": "dropped",
    }
    s = led["summary"]
    assert s["total"] == 4 and s["asserted"] == 1 and s["dropped"] == 1
    assert s["assured_pct"] == 25


def test_dropped_rule_keeps_the_planner_reason():
    """A rule nobody carries must say *why* — that is the whole point of the row."""
    row = next(r for r in build_rule_ledger(_bb())["rules"] if r["status"] == "dropped")
    assert "dead code" in row["evidence"]
    assert row["target"] == "—"


def test_dropped_rules_sort_first():
    """The reviewer must meet the riskiest rows before the reassuring ones."""
    assert build_rule_ledger(_bb())["rules"][0]["status"] == "dropped"


def test_rule_ids_are_stable_and_unique():
    a, b = _bb(), _bb()
    assert ([r["id"] for r in build_rule_ledger(a)["rules"]]
            == [r["id"] for r in build_rule_ledger(b)["rules"]])
    assert rule_id("A", "same text") != rule_id("B", "same text")
    ids = [r["id"] for r in build_rule_ledger(a)["rules"]]
    assert len(set(ids)) == len(ids)


def test_headline_surfaces_dropped_rules():
    s = build_rule_ledger(_bb())["summary"]
    assert "1/4 business rules preserved and asserted" in headline(s)
    assert "1 DROPPED" in headline(s)


def test_empty_ledger_does_not_claim_success():
    """No rules found must never render as 100%."""
    led = build_rule_ledger(Blackboard("in", "out"))
    assert led["summary"]["total"] == 0 and led["summary"]["assured_pct"] is None
    assert "No business rules were extracted" in headline(led["summary"])


def test_report_warns_and_flags_the_heuristic(tmp_path):
    path = write_rules_md(str(tmp_path), build_rule_ledger(_bb()))
    text = open(path, encoding="utf-8").read()
    assert "1 rule(s) are not carried by any generated artifact" in text
    assert "Gold tier customers accrue double loyalty points" in text
    # We must never let "asserted" read as proof of behavioural equivalence.
    assert "heuristic" in text and "not proof" in text


def test_pipe_in_rule_text_does_not_break_the_table(tmp_path):
    bb = Blackboard("in", "out")
    bb.comprehensions = {"C": {"business_rules": ["status is A | B | C"]}}
    text = open(write_rules_md(str(tmp_path), build_rule_ledger(bb)), encoding="utf-8").read()
    row = next(ln for ln in text.splitlines() if "status is A" in ln)
    assert row.count("|") - row.count("\\|") == 6  # 5 cells → 6 unescaped delimiters
