"""Provenance: where each generated method came from.

Line numbers here are computed from the text, never taken from a model — so these assert
exact ranges, which would be meaningless if they were opinions.
"""

from src.agentic.blackboard import Blackboard, Artifact
from src.provenance import map_artifact, build_provenance, headline, write_provenance_md

JAVA = """public class DefaultPricingService {
    public BigDecimal applySpendDiscount(final BigDecimal subtotal) {
        return subtotal;
    }
    public BigDecimal placeOrder(final OrderModel order) {
        return BigDecimal.ZERO;
    }
    private BigDecimal scale(final BigDecimal v) {
        return v;
    }
}"""

APEX = """public with sharing class PricingService {
    public PricingService() {
    }
    public Decimal applySpendDiscount(Decimal subtotal) {
        return subtotal;
    }
    public List<Order__c> createOrders(List<OrderRequest> reqs) {
        return null;
    }
    public Decimal roundIt(Decimal v) {
        return v;
    }
}"""


def art(apex=APEX, java=JAVA):
    return Artifact(target_name="PricingService", layer="Service", main_class=apex,
                    source_classes=[{"class_name": "DefaultPricingService",
                                     "file": "DefaultPricingService.java", "source": java}])


def links(m):
    return {l["apex"]: l for l in m["links"]}


def test_an_unchanged_name_is_traced_exactly():
    l = links(map_artifact(art()))["applySpendDiscount"]
    assert l["java"] == "applySpendDiscount"
    assert l["confidence"] == "high" and l["basis"] == "exact name"


def test_line_ranges_are_computed_from_the_text():
    """These are facts, not a model's recollection — which is the entire design premise."""
    l = links(map_artifact(art()))["applySpendDiscount"]
    assert l["apex_lines"] == [4, 6]
    assert l["java_lines"] == [2, 4]


def test_a_bulkified_rename_is_still_traced_but_marked_lower_confidence():
    """placeOrder becoming createOrders is the reshaping characterization already found."""
    l = links(map_artifact(art()))["createOrders"]
    assert l["java"] == "placeOrder"
    assert l["confidence"] == "medium" and l["basis"] == "normalised name"


def test_apex_with_no_java_origin_is_listed():
    """Either scaffolding or invention — a reviewer should see it either way."""
    assert [o["apex"] for o in map_artifact(art())["apex_without_origin"]] == ["roundIt"]


def test_a_constructor_is_not_reported_as_unexplained():
    assert "PricingService" not in [o["apex"] for o in map_artifact(art())["apex_without_origin"]]


def test_java_with_no_apex_counterpart_is_listed():
    """The more alarming direction: logic that may simply not have been carried over."""
    assert [u["java"] for u in map_artifact(art())["java_without_apex"]] == ["scale"]


def test_generic_names_are_not_paired_on_similarity_alone():
    """Matching `run` to `run` across unrelated classes would be worse than not matching."""
    m = map_artifact(art(apex="public class X {\n  public void run() {\n  }\n}",
                         java="public class Y {\n  public void execute() {\n  }\n}"))
    assert m["links"] == []


def test_coverage_reflects_what_was_actually_traced():
    m = map_artifact(art())
    assert m["coverage"] == 67          # 2 of 3 non-constructor methods


def test_headline_reports_both_directions():
    bb = Blackboard("in", "out")
    bb.artifacts = [art()]
    s = build_provenance(bb)["summary"]
    assert "2/3 generated method(s) traced" in headline(s)
    assert "1 with no origin" in headline(s)
    assert "1 Java method(s) with no Apex counterpart" in headline(s)


def test_lwc_artifacts_are_skipped():
    bb = Blackboard("in", "out")
    bb.artifacts = [Artifact(target_name="cart", layer="Component", main_class="")]
    assert build_provenance(bb)["summary"]["methods"] == 0


def test_the_report_explains_what_confidence_means(tmp_path):
    bb = Blackboard("in", "out")
    bb.artifacts = [art()]
    text = open(write_provenance_md(str(tmp_path), build_provenance(bb)), encoding="utf-8").read()
    assert "no Apex counterpart" in text
    assert "exact name` is a fact" in text
    assert "confidently wrong" in text
