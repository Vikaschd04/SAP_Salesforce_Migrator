"""Review triage: which artifacts actually need a person.

The point of ranking is that the reviewer's attention lands on the right files. So these
test the *ordering and the reasons*, not the arithmetic — the score is a sorting device
and asserting exact numbers would just freeze one arbitrary weighting in place.
"""

from src.agentic.blackboard import Blackboard, Artifact
from src.triage import build_triage, headline, write_triage_md


def bb_with(artifacts, radar_findings=(), comprehensions=None):
    bb = Blackboard("in", "out")
    bb.artifacts = list(artifacts)
    bb.comprehensions = comprehensions or {}
    bb.radar = {"findings": [{"id": f"H-{i:03d}", **f} for i, f in enumerate(radar_findings, 1)],
                "summary": {}}
    return bb


def art(name, layer="Service", **kw):
    return Artifact(target_name=name, layer=layer,
                    source_classes=kw.pop("sources", [{"class_name": f"Default{name}",
                                                       "file": f"Default{name}.java"}]), **kw)


def by_target(t):
    return {i["target"]: i for i in t["items"]}


def test_a_failed_artifact_always_lands_in_must_review():
    t = build_triage(bb_with([art("A", status="error")]))
    item = by_target(t)["A"]
    assert item["band"] == "must"
    assert any("did not build" in r for r in item["reasons"])


def test_one_critical_hazard_is_must_review_on_its_own():
    t = build_triage(bb_with(
        [art("OrderFulfilmentService")],
        [{"severity": "critical", "rule": "DML_IN_LOOP", "file": "DefaultOrderFulfilmentService.java",
          "source_class": "DefaultOrderFulfilmentService"}]))
    item = by_target(t)["OrderFulfilmentService"]
    # Asserted on the band, not the score: a single critical hazard is must-review on
    # its own merits, and it should not depend on a weighted sum happening to clear a
    # threshold. (It does not — one critical scores 30 against a threshold of 40.)
    assert item["band"] == "must"
    assert "DML_IN_LOOP" in " ".join(item["reasons"])


def test_hazards_reach_the_artifact_even_without_a_file_reference():
    """builders.py rebuilt source_classes and dropped `file`, so a file-only lookup
    silently matched nothing and every artifact came out routine."""
    a = art("X", sources=[{"class_name": "DefaultX"}])          # no `file` key
    t = build_triage(bb_with([a], [{"severity": "critical", "rule": "DML_IN_LOOP",
                                    "file": "DefaultX.java", "source_class": "DefaultX"}]))
    assert by_target(t)["X"]["hazards"]["critical"] == 1


def test_a_hazard_is_not_counted_twice_when_both_keys_match():
    a = art("X", sources=[{"class_name": "DefaultX", "file": "DefaultX.java"}])
    t = build_triage(bb_with([a], [{"severity": "critical", "rule": "DML_IN_LOOP",
                                    "file": "DefaultX.java", "source_class": "DefaultX"}]))
    assert by_target(t)["X"]["hazards"]["critical"] == 1, "matched on both keys and double counted"


def test_a_clean_mechanical_artifact_is_routine_and_says_why():
    t = build_triage(bb_with([art("OrderSelector", layer="DAO")]))
    item = by_target(t)["OrderSelector"]
    assert item["band"] == "routine"
    assert any("mechanical" in r for r in item["reasons"])


def test_business_rules_raise_an_otherwise_clean_artifact():
    plain = art("A")
    rich = art("B")
    rich.business_rules = [f"rule {i}" for i in range(6)]
    t = by_target(build_triage(bb_with([plain, rich])))
    assert t["B"]["score"] > t["A"]["score"]
    assert t["B"]["band"] != "routine", "an artifact carrying six rules is not routine"


def test_critic_errors_outrank_critic_warnings():
    e = art("E"); e.critic_findings = [{"severity": "error", "message": "x"}]
    w = art("W"); w.critic_findings = [{"severity": "warning", "message": "x"}]
    t = by_target(build_triage(bb_with([e, w])))
    assert t["E"]["score"] > t["W"]["score"]


def test_a_native_recommendation_needs_a_human_decision():
    a = art("Pricing")
    a.review_flags = ["Salesforce CPQ may be a better home for this logic"]
    item = by_target(build_triage(bb_with([a])))["Pricing"]
    assert item["band"] != "routine"
    assert "CPQ" in " ".join(item["reasons"])


def test_items_are_ordered_worst_first():
    a = art("Clean", layer="DAO")
    b = art("Broken", status="error")
    items = build_triage(bb_with([a, b]))["items"]
    assert items[0]["target"] == "Broken"


def test_every_flagged_item_explains_itself():
    """A bare score is not actionable and not trustworthy — the reasons are the product."""
    t = build_triage(bb_with(
        [art("A", status="error"), art("B", layer="DAO")],
        [{"severity": "high", "rule": "TRANSACTIONAL", "file": "DefaultA.java",
          "source_class": "DefaultA"}]))
    for item in t["items"]:
        assert item["reasons"], f"{item['target']} was ranked with no explanation"


def test_the_headline_says_what_to_do():
    s = build_triage(bb_with([art("A", status="error"), art("B", layer="DAO")]))["summary"]
    assert "need your attention" in headline(s) and "1 must-review" in headline(s)
    clean = build_triage(bb_with([art("B", layer="DAO")]))["summary"]
    assert "look routine" in headline(clean)


def test_the_report_admits_the_score_is_a_judgement(tmp_path):
    t = build_triage(bb_with([art("A", status="error"), art("B", layer="DAO")]))
    text = open(write_triage_md(str(tmp_path), t), encoding="utf-8").read()
    assert "sorting device, not a measurement" in text
    assert "bulk-approve" in text


def test_high_complexity_raises_the_rank():
    a = art("A", sources=[{"class_name": "DefaultA", "file": "DefaultA.java"}])
    plain = build_triage(bb_with([a]))["items"][0]["score"]
    withcx = build_triage(bb_with([a], comprehensions={"DefaultA": {"complexity": "High"}}))["items"][0]
    assert withcx["score"] > plain
    assert any("high complexity" in r for r in withcx["reasons"])
