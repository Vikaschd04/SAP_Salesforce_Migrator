"""Blast radius (#8) and deterministic replay (#9)."""

from src.agentic.blackboard import Blackboard, Artifact
from src.blast import blast_radius, headline as b_headline
from src.replay import build_replay, headline as r_headline, write_replay_md


def art(name, layer="Service", sources=(), refs=(), rules=(), sobjects=(), test="x"):
    return Artifact(target_name=name, layer=layer, test_class=test,
                    business_rules=list(rules), sobject_refs=list(sobjects),
                    source_classes=[{"class_name": s} for s in sources])


def bb_with(artifacts, classes):
    b = Blackboard("in", "out")
    b.artifacts = list(artifacts)
    b.all_classes = list(classes)
    return b


# ── blast radius ──────────────────────────────────────────────────────────────

def test_a_direct_dependent_is_found():
    b = bb_with([art("OrderSelector", "DAO", ["OrderDao"]),
                 art("OrderService", sources=["DefaultOrderService"])],
                [{"class_name": "OrderDao", "referenced_types": []},
                 {"class_name": "DefaultOrderService", "referenced_types": ["OrderDao"]}])
    r = blast_radius(b, "OrderSelector")
    assert [d["target"] for d in r["direct"]] == ["OrderService"]
    assert r["direct"][0]["via"] == ["DefaultOrderService"]


def test_distance_is_kept_rather_than_collapsed():
    """A dependent three hops out is not the same claim as one that calls you directly;
    merging them into one number would train people to ignore it."""
    b = bb_with([art("A", sources=["A"]), art("B", sources=["B"]), art("C", sources=["C"])],
                [{"class_name": "A", "referenced_types": []},
                 {"class_name": "B", "referenced_types": ["A"]},
                 {"class_name": "C", "referenced_types": ["B"]}])
    r = blast_radius(b, "A")
    assert [d["target"] for d in r["direct"]] == ["B"]
    assert [d["target"] for d in r["indirect"]] == ["C"]


def test_a_leaf_artifact_is_self_contained():
    b = bb_with([art("Leaf", sources=["Leaf"])], [{"class_name": "Leaf", "referenced_types": []}])
    assert b_headline(blast_radius(b, "Leaf")) == \
        "Nothing else depends on this — reworking it is self-contained."


def test_tests_to_rerun_include_the_artifact_and_its_dependents():
    b = bb_with([art("A", sources=["A"]), art("B", sources=["B"])],
                [{"class_name": "A", "referenced_types": []},
                 {"class_name": "B", "referenced_types": ["A"]}])
    assert blast_radius(b, "A")["tests_to_rerun"] == ["ATest", "BTest"]


def test_shared_schema_is_reported():
    """A shared object is how a rework reaches code that never references it directly."""
    b = bb_with([art("A", sources=["A"], sobjects=["Order__c", "Solo__c"]),
                 art("B", sources=["B"], sobjects=["Order__c"])],
                [{"class_name": "A", "referenced_types": []},
                 {"class_name": "B", "referenced_types": []}])
    r = blast_radius(b, "A")
    assert r["shared_schema"] == ["Order__c"] and "Solo__c" in r["schema"]


def test_dependents_carrying_rules_sort_first():
    b = bb_with([art("A", sources=["A"]),
                 art("Plain", sources=["P"]), art("Rich", sources=["R"], rules=["r1", "r2"])],
                [{"class_name": "A", "referenced_types": []},
                 {"class_name": "P", "referenced_types": ["A"]},
                 {"class_name": "R", "referenced_types": ["A"]}])
    assert blast_radius(b, "A")["direct"][0]["target"] == "Rich"


def test_an_unknown_target_is_reported_not_raised():
    assert blast_radius(bb_with([], []), "Nope")["found"] is False


# ── deterministic replay ──────────────────────────────────────────────────────

def log(n=3, cached=True):
    return [{"seq": i, "stage": f"comprehend_C{i}", "provider": "anthropic",
             "model": "claude-opus-4-8", "cache_key": f"{i:064x}", "cached": cached,
             "prompt_chars": 1000, "effort": "low", "attempts": 1, "at": 0.0}
            for i in range(1, n + 1)]


def test_every_call_is_replayable_because_every_call_has_a_key():
    s = build_replay(log(5))["summary"]
    assert s["total"] == 5 and s["replayable"] == 5


def test_cache_hits_and_live_calls_are_counted_separately():
    s = build_replay(log(2, cached=True) + log(3, cached=False))["summary"]
    assert s["cached"] == 2 and s["live"] == 3


def test_calls_are_grouped_by_stage_family():
    r = build_replay(log(3) + [{**log(1)[0], "seq": 4, "stage": "generate_X"}])
    fams = {s["stage"]: s["calls"] for s in r["stages"]}
    assert fams == {"comprehend": 3, "generate": 1}


def test_no_calls_does_not_claim_a_record():
    assert "nothing to replay" in r_headline(build_replay([])["summary"])


def test_the_record_does_not_store_prompts(tmp_path):
    """Prompts contain the customer's source; copying that to a second place on disk
    would be a liability rather than a feature."""
    text = open(write_replay_md(str(tmp_path), build_replay(log(2))), encoding="utf-8").read()
    assert "not stored here, deliberately" in text
    assert "Decision Record" in text
    assert "cache" in text
