"""Characterization: mine recorded behaviour from JUnit and replay it against the Apex."""

import textwrap

from src.agentic.blackboard import Artifact
from src.characterize import (mine_behaviors, plan_replay, generate_apex, summarise,
                              headline, write_characterization_md, behavior_id,
                              is_runnable, build_adapters)

JUNIT = textwrap.dedent("""
    package com.acme;
    import org.junit.Test;
    import java.math.BigDecimal;
    import static org.junit.Assert.assertEquals;
    import static org.junit.Assert.assertTrue;

    public class DefaultPromotionServiceTest {
        @Test
        public void spendDiscountAppliesTenPercentOverThreshold() {
            assertEquals(new BigDecimal("180.00"), svc.applySpendDiscount(new BigDecimal("200.00")));
        }
        @Test
        public void unknownCodesChangeNothing() {
            assertEquals(new BigDecimal("50.00"), svc.applyPromoCode(new BigDecimal("50.00"), "NOPE"));
        }
        @Test
        public void highSpendersQualify() {
            assertTrue(svc.qualifiesForFreeShipping(new BigDecimal("500.00")));
        }
        @Test(expected = IllegalArgumentException.class)
        public void negativeSubtotalIsRejected() {
            svc.applySpendDiscount(new BigDecimal("-1.00"));
        }
        @Test
        public void loyaltyNeedsARealCustomer() {
            assertEquals(new BigDecimal("88.00"), svc.applyLoyaltyDiscount(subtotal, customer));
        }
    }
    """)

# Apex where the signatures survived — the `direct` case.
APEX_OK = """
public with sharing class PromotionService {
    public Decimal applySpendDiscount(Decimal subtotal) { return subtotal; }
    public Decimal applyPromoCode(Decimal subtotal, String code) { return subtotal; }
    public static Boolean qualifiesForFreeShipping(Decimal subtotal) { return true; }
    public Decimal applyLoyaltyDiscount(Decimal subtotal, Customer__c c) { return subtotal; }
}
"""


def _tests():
    return [{"class_name": "DefaultPromotionServiceTest", "source": JUNIT, "is_test": True}]


def _art(main=APEX_OK, status="ok"):
    return Artifact(target_name="PromotionService", layer="Service", status=status,
                    main_class=main,
                    source_classes=[{"class_name": "DefaultPromotionService"}])


def test_mines_recorded_values_not_opinions():
    got = {b["test_method"]: b for b in mine_behaviors(_tests())}
    b = got["spendDiscountAppliesTenPercentOverThreshold"]
    assert b["source_class"] == "DefaultPromotionService"
    assert b["target_method"] == "applySpendDiscount"
    assert b["args"][0]["apex"] == "200.00"      # new BigDecimal("200.00") → Apex Decimal
    assert b["expected"]["apex"] == "180.00"


def test_mines_a_recorded_rejection():
    b = next(b for b in mine_behaviors(_tests()) if b["test_method"] == "negativeSubtotalIsRejected")
    assert b["expects_exception"] == "IllegalArgumentException"


def test_direct_when_the_signature_survived():
    planned = plan_replay(mine_behaviors(_tests()), [_art()])
    modes = {p["test_method"]: p["mode"] for p in planned}
    assert modes["spendDiscountAppliesTenPercentOverThreshold"] == "direct"
    assert modes["unknownCodesChangeNothing"] == "direct"
    assert modes["highSpendersQualify"] == "direct"
    # Non-literal arguments cannot be replayed faithfully — must not be claimed as direct.
    assert modes["loyaltyNeedsARealCustomer"] == "adapter"


def test_adapter_when_the_migration_reshaped_the_call():
    """A bulkified method is the common real case: the name is simply gone."""
    bulk = "public with sharing class PromotionService { public List<Decimal> applyDiscounts(List<Decimal> subs) { return subs; } }"
    planned = plan_replay(mine_behaviors(_tests()), [_art(main=bulk)])
    assert {p["mode"] for p in planned} == {"adapter"}
    assert "reshaped" in next(p for p in planned)["reason"]


def test_manual_when_nothing_carries_the_class():
    planned = plan_replay(mine_behaviors(_tests()), [])
    assert {p["mode"] for p in planned} == {"manual"}
    assert planned[0]["target"] is None


def test_failed_target_is_never_claimed_as_proof():
    planned = plan_replay(mine_behaviors(_tests()), [_art(status="error")])
    assert {p["mode"] for p in planned} == {"manual"}


def test_generated_apex_asserts_the_recorded_value():
    apex = generate_apex(plan_replay(mine_behaviors(_tests()), [_art()]))
    body = apex["PromotionServiceCharacterizationTest"]
    assert "@isTest" in body and "private class PromotionServiceCharacterizationTest" in body
    # The recorded pair must appear verbatim — that is the whole point.
    assert "System.assertEquals(180.00, new PromotionService().applySpendDiscount(200.00)" in body
    # A static Apex method must not be called through an instance.
    assert "PromotionService.qualifiesForFreeShipping(500.00)" in body
    # The recorded rejection becomes a try/catch, not an equality assertion.
    assert "Boolean threw = false;" in body


def test_generated_apex_excludes_everything_but_direct():
    """Anything we cannot replay faithfully must not appear as a passing test."""
    body = generate_apex(plan_replay(mine_behaviors(_tests()), [_art()]))["PromotionServiceCharacterizationTest"]
    assert "applyLoyaltyDiscount" not in body


def test_no_apex_generated_when_nothing_is_direct():
    assert generate_apex(plan_replay(mine_behaviors(_tests()), [])) == {}


def test_summary_and_headline_are_honest():
    s = summarise(plan_replay(mine_behaviors(_tests()), [_art()]))
    assert s["total"] == 5 and s["direct"] == 4 and s["adapter"] == 1
    assert "4/5 recorded behaviours replay against the generated Apex (80% — 4 direct)" in headline(s)
    assert "No JUnit tests found" in headline(summarise([]))


def test_ids_are_stable_and_unique():
    a = [b["id"] for b in mine_behaviors(_tests())]
    assert a == [b["id"] for b in mine_behaviors(_tests())]
    assert len(set(a)) == len(a)
    assert behavior_id("A", "m", 1) != behavior_id("B", "m", 1)


def test_report_grades_the_evidence(tmp_path):
    planned = plan_replay(mine_behaviors(_tests()), [_art()])
    text = open(write_characterization_md(str(tmp_path), planned, generate_apex(planned)),
                encoding="utf-8").read()
    assert "4/5 recorded behaviours replay against the generated Apex" in text
    # The reader must be told how far to trust each mode.
    assert "**Strong**" in text and "Medium" in text
    assert "PromotionServiceCharacterizationTest.cls" in text


# ── ingest: JUnit tests must never be migrated as production code ──────────────

def _parse(src, name="Foo.java", tmp=None):
    from src.ingest import _parse_java_file
    p = tmp / name
    p.write_text(src, encoding="utf-8")
    return _parse_java_file(str(p))


def test_junit_import_marks_a_test(tmp_path):
    src = "import org.junit.Test;\npublic class Anything { public void go() {} }"
    assert _parse(src, "Anything.java", tmp_path)["is_test"] is True


def test_test_annotation_marks_a_test(tmp_path):
    src = "public class Whatever { @Test public void go() {} }"
    assert _parse(src, "Whatever.java", tmp_path)["is_test"] is True


def test_a_production_class_named_test_is_not_excluded(tmp_path):
    """`ABTestService` and friends are production code. Excluding them would silently
    drop real business logic from the migration — far worse than a wasted conversion."""
    src = "public class ABTestService { public void assign() {} }"
    assert _parse(src, "ABTestService.java", tmp_path)["is_test"] is False


def test_naming_alone_needs_a_test_shaped_body(tmp_path):
    src = "public class PricingTest { public void computeRate() {} }"
    assert _parse(src, "PricingTest.java", tmp_path)["is_test"] is False


def test_ingest_holds_tests_aside_from_the_migration_set():
    from src.ingest import ingest
    r = ingest("../Testing/demo-hybris-ordermgmt/acmeordermanagement")
    assert [c["class_name"] for c in r["test_classes"]] == [
        "DefaultOrderServiceTest", "DefaultPromotionServiceTest"]
    assert not any(c["class_name"].endswith("Test") for c in r["classes"])


# ── the adapter bridge: a model may arrange, never assert ─────────────────────

BULK = ("public with sharing class PromotionService { "
        "public List<Decimal> applyDiscounts(List<Decimal> subs) { return subs; } }")


def _adapters(bridges, monkeypatch):
    """Run build_adapters against a stubbed model response."""
    import src.llm as llm
    monkeypatch.setattr(llm, "call_structured",
                        lambda *a, **k: {"parsed": {"bridges": bridges}})
    planned = plan_replay(mine_behaviors(_tests()), [_art(main=BULK)])
    return build_adapters(planned, apex_of={"PromotionService": BULK})


def _ids(planned):
    return {p["test_method"]: p for p in planned}


def test_a_feasible_bridge_becomes_runnable(monkeypatch):
    rows = plan_replay(mine_behaviors(_tests()), [_art(main=BULK)])
    target = _ids(rows)["spendDiscountAppliesTenPercentOverThreshold"]
    planned = _adapters([{"id": target["id"], "feasible": True,
                          "setup": "Decimal r = new PromotionService().applyDiscounts(new List<Decimal>{200.00})[0];",
                          "result_expr": "r", "note": "wrapped the single value in a list"}],
                        monkeypatch)
    got = _ids(planned)["spendDiscountAppliesTenPercentOverThreshold"]
    assert got["bridge"]["result_expr"] == "r"
    assert is_runnable(got)


def test_the_assertion_is_written_by_us_not_the_model(monkeypatch):
    """The recorded value must appear in the generated assert even though the model
    was never told it — that separation is what keeps a bridged test evidence."""
    rows = plan_replay(mine_behaviors(_tests()), [_art(main=BULK)])
    target = _ids(rows)["spendDiscountAppliesTenPercentOverThreshold"]
    planned = _adapters([{"id": target["id"], "feasible": True,
                          "setup": "Decimal r = svc.applyDiscounts(new List<Decimal>{200.00})[0];",
                          "result_expr": "r", "note": ""}], monkeypatch)
    body = generate_apex(planned)["PromotionServiceCharacterizationTest"]
    assert "System.assertEquals(180.00, r," in body


def test_a_bridge_that_writes_its_own_assertion_is_rejected(monkeypatch):
    """Otherwise a model could assert whatever makes the test pass."""
    rows = plan_replay(mine_behaviors(_tests()), [_art(main=BULK)])
    target = _ids(rows)["spendDiscountAppliesTenPercentOverThreshold"]
    planned = _adapters([{"id": target["id"], "feasible": True,
                          "setup": "Decimal r = 999; System.assertEquals(999, r);",
                          "result_expr": "r", "note": ""}], monkeypatch)
    got = _ids(planned)["spendDiscountAppliesTenPercentOverThreshold"]
    assert "bridge" not in got
    assert "own assertion" in got["reason"]
    assert generate_apex(planned) == {}


def test_an_infeasible_bridge_is_never_emitted(monkeypatch):
    rows = plan_replay(mine_behaviors(_tests()), [_art(main=BULK)])
    target = _ids(rows)["spendDiscountAppliesTenPercentOverThreshold"]
    planned = _adapters([{"id": target["id"], "feasible": False, "setup": "", "result_expr": "",
                          "note": "the new API has no single-order equivalent"}], monkeypatch)
    got = _ids(planned)["spendDiscountAppliesTenPercentOverThreshold"]
    assert "bridge" not in got and "no single-order equivalent" in got["reason"]


def test_unassertable_return_values_are_never_sent_for_bridging(monkeypatch):
    """A behaviour whose recorded ANSWER is an object graph has nothing to assert
    against, so bridging it would produce a test that proves nothing."""
    src = textwrap.dedent("""
        import org.junit.Test;
        import static org.junit.Assert.assertEquals;
        public class DefaultPromotionServiceTest {
            @Test public void returnsTheSameCart() {
                assertEquals(expectedCart, svc.rebuildCart(cart));
            }
        }
        """)
    sent = []
    import src.llm as llm
    monkeypatch.setattr(llm, "call_structured",
                        lambda *a, **k: sent.append(a[0]) or {"parsed": {"bridges": []}})
    planned = plan_replay(mine_behaviors([{"class_name": "DefaultPromotionServiceTest",
                                           "source": src}]), [_art(main=BULK)])
    build_adapters(planned, apex_of={"PromotionService": BULK})
    assert "object graph" in planned[0]["reason"]
    assert sent == [], "an unassertable behaviour must never reach the model"


def test_a_model_failure_never_breaks_the_run(monkeypatch):
    import src.llm as llm
    def boom(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(llm, "call_structured", boom)
    planned = plan_replay(mine_behaviors(_tests()), [_art(main=BULK)])
    out = build_adapters(planned, apex_of={"PromotionService": BULK})
    assert all("bridge" not in r for r in out)
    assert any("bridging unavailable" in r["reason"] for r in out)


# ── orchestrator wiring ───────────────────────────────────────────────────────

def test_characterize_wiring_actually_produces_a_summary(tmp_path, monkeypatch):
    """_characterize contains a broad except so evidence-gathering can never break a
    migration — which also means a plain programming error inside it shows up only as
    'characterization skipped'. This asserts the happy path really works."""
    import src.agentic.orchestrator as O
    import src.llm as llm
    from src.agentic.blackboard import Blackboard

    monkeypatch.setattr(llm, "call_structured", lambda *a, **k: {"parsed": {"bridges": []}})
    bb = Blackboard("in", str(tmp_path))
    bb.test_classes = [{"class_name": "DefaultPromotionServiceTest", "source": JUNIT}]
    bb.artifacts = [_art()]

    out = O._characterize(bb, str(tmp_path), offline=False,
                          config={"provider": "anthropic", "agentic": {"routing": {"enabled": True,
                                  "models": {"cheap": "c", "frontier": "f"},
                                  "tiers": {"generate": "frontier"}}}})
    assert out is not None, "characterization was skipped when it should have run"
    assert out["summary"]["total"] == 5 and out["summary"]["direct"] == 4
    assert (tmp_path / "CHARACTERIZATION.md").exists()
    assert (tmp_path / "force-app/main/default/classes/"
            "PromotionServiceCharacterizationTest.cls").exists()


def test_characterize_is_a_no_op_without_junit(tmp_path):
    import src.agentic.orchestrator as O
    from src.agentic.blackboard import Blackboard
    assert O._characterize(Blackboard("in", "out"), str(tmp_path),
                           offline=False, config={}) is None
