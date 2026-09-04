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
    return {l["target"]: l for l in m["links"]}


def test_an_unchanged_name_is_traced_exactly():
    l = links(map_artifact(art()))["applySpendDiscount"]
    assert l["source"] == "applySpendDiscount"
    assert l["confidence"] == "high" and l["basis"] == "exact name"


def test_line_ranges_are_computed_from_the_text():
    """These are facts, not a model's recollection — which is the entire design premise."""
    l = links(map_artifact(art()))["applySpendDiscount"]
    assert l["target_lines"] == [4, 6]
    assert l["source_lines"] == [2, 4]


def test_a_bulkified_rename_is_still_traced_but_marked_lower_confidence():
    """placeOrder becoming createOrders is the reshaping characterization already found."""
    l = links(map_artifact(art()))["createOrders"]
    assert l["source"] == "placeOrder"
    assert l["confidence"] == "medium" and l["basis"] == "normalised name"


def test_apex_with_no_java_origin_is_listed():
    """Either scaffolding or invention — a reviewer should see it either way."""
    assert [o["target"] for o in map_artifact(art())["target_without_origin"]] == ["roundIt"]


def test_a_constructor_is_not_reported_as_unexplained():
    assert "PricingService" not in [o["target"] for o in map_artifact(art())["target_without_origin"]]


def test_java_with_no_apex_counterpart_is_listed():
    """The more alarming direction: logic that may simply not have been carried over."""
    assert [u["source"] for u in map_artifact(art())["source_without_target"]] == ["scale"]


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


# ── which platform's language is the origin? [1.36] ───────────────────────────

def test_the_headline_names_the_source_language_not_a_fixed_one():
    """It read "traced to their Java origin" for every pipeline. Java is the *target* of
    the Adobe→Hybris path, so that run reported methods traced to the language it had
    just written. The word was right for the shipped pipeline, which is why it survived
    4.4 — that item parameterised the sentences either side of this one and missed it."""
    from src import runctx
    from src.provenance import headline

    s = {"methods": 4, "linked": 2, "coverage": 50, "target_without_origin": 2,
         "source_without_target": 3}
    token = runctx._pipeline_id.set("adobe->hybris")
    try:
        got = headline(s)
    finally:
        runctx._pipeline_id.reset(token)
    assert "their PHP origin" in got
    assert "PHP method(s) with no Java counterpart" in got


def test_the_shipped_pipeline_still_reads_the_same():
    """The fix must not move the shipped path's prose — Java really is its source."""
    from src import runctx
    from src.provenance import headline

    s = {"methods": 4, "linked": 2, "coverage": 50, "target_without_origin": 2,
         "source_without_target": 3}
    token = runctx._pipeline_id.set("hybris->salesforce")
    try:
        got = headline(s)
    finally:
        runctx._pipeline_id.reset(token)
    assert "their Java origin" in got
    assert "Java method(s) with no Apex counterpart" in got


def test_the_signoff_caveat_names_the_source_language_too():
    """Same bug, one line below a sibling that already parameterised it."""
    from src import assurance, runctx
    from src.signoff import _caveats

    claim = {"rung": assurance.REPLAYED, "claim": "", "limit": ""}
    token = runctx._pipeline_id.set("adobe->hybris")
    try:
        text = "\n".join(_caveats({}, {}, {}, {"target_without_origin": 3}, {}, [], claim))
    finally:
        runctx._pipeline_id.reset(token)
    assert "trace to no PHP origin" in text


# ── a coverage figure that measures nothing says so [1.36] ────────────────────

def test_a_stub_run_says_its_coverage_measures_placeholders(tmp_path):
    """A stub run emits one placeholder method per artifact, which traces to nothing by
    construction. Reported bare, the percentage reads as a tool inventing most of its
    output — misleading in the pessimistic direction, and read in demos."""
    from src.provenance import write_provenance_md

    prov = {"artifacts": [], "summary": {"methods": 8, "linked": 4, "coverage": 50,
                                         "target_without_origin": 4,
                                         "source_without_target": 0, "generated": False}}
    write_provenance_md(str(tmp_path), prov)
    body = (tmp_path / "PROVENANCE.md").read_text()
    assert "No model generated this output" in body
    assert "not a migration" in body


def test_a_real_run_carries_no_such_notice(tmp_path):
    from src.provenance import write_provenance_md

    prov = {"artifacts": [], "summary": {"methods": 8, "linked": 4, "coverage": 50,
                                         "target_without_origin": 4,
                                         "source_without_target": 0, "generated": True}}
    write_provenance_md(str(tmp_path), prov)
    assert "No model generated" not in (tmp_path / "PROVENANCE.md").read_text()


def test_a_run_with_no_methods_says_nothing_either_way(tmp_path):
    from src.provenance import write_provenance_md

    write_provenance_md(str(tmp_path), {"artifacts": [], "summary": {"methods": 0}})
    assert "No model generated" not in (tmp_path / "PROVENANCE.md").read_text()


def test_an_invented_method_is_caught_on_the_adobe_path(tmp_path):
    """The residue list is the hallucination check, and it has to work across a language
    boundary the shipped path never crosses: PHP in, Java out.

    Read with a Java-shaped regex the PHP side returns roughly one method in six — it does
    not fail, it under-reports, which would make every generated method look invented.
    This pins the whole chain: the source adapter's reader, the target's, and the pairing
    between them. [1.36]
    """
    from pathlib import Path

    from src import runctx
    from src.provenance import map_artifact

    php = (Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento"
           / "app/code/Acme/Loyalty/Model/PricingService.php").read_text()

    class _Artifact:
        target_name = "PricingService"
        is_lwc = False
        main_class = (
            "package com.migrated.service.impl;\n"
            "public class DefaultPricingService implements PricingService {\n"
            "    public double applySpendDiscount(final double subtotal) { return subtotal; }\n"
            "    public int pointsFor(final double total) { return 0; }\n"
            "    public double invented(final double x) { return x; }\n"
            "}")
        source_classes = [{"class_name": "PricingService", "source": php}]

    token = runctx._pipeline_id.set("adobe->hybris")
    try:
        got = map_artifact(_Artifact())
    finally:
        runctx._pipeline_id.reset(token)

    linked = {l["target"] for l in got["links"]}
    assert {"applySpendDiscount", "pointsFor"} <= linked, "real PHP origins were missed"
    assert [o["target"] for o in got["target_without_origin"]] == ["invented"]
