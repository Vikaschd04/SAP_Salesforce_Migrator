"""Snapshots are only useful if what comes back is what went in.

The interesting failures here are quiet ones: a set returning as a list, a plan restored
beside generated files that implement a different plan, a checkpoint written by an older
version loading into today's dataclasses. Each looks fine and is wrong.
"""
import gzip
import json
import pytest

from src.agentic.blackboard import Blackboard, PlanItem, Artifact
from src.checkpoint import save, load, list_all, diff, headline, _dir, _SUFFIX


def _bb(tmp_path, *, skip=False):
    bb = Blackboard(input_dir=str(tmp_path / "src"), output_dir=str(tmp_path / "out"))
    (tmp_path / "src").mkdir(exist_ok=True)
    bb.all_classes = [{"class_name": "DefaultPricingService", "layer": "Service",
                       "file": "DefaultPricingService.java", "source": "class A {}"}]
    # The schema really does carry sets, which is the round-trip's sharp edge.
    bb.schema = {"Order__c": {"code": "Order", "fields": {"Total__c": "Currency"},
                              "required": {"Total__c", "Status__c"},
                              "unique": {"Code__c"}, "picklists": {}, "defaults": {}}}
    bb.plan = [PlanItem(target_name="PricingService", layer="Service", domain="Pricing",
                        target_kind="Skip" if skip else "Convert",
                        native_recommendation="Salesforce CPQ")]
    a = Artifact(target_name="PricingService", layer="Service")
    a.main_class = "public class PricingService {}"
    a.status = "accepted"
    bb.artifacts = [a]
    bb.record("Planner", "planned", "1 target")
    return bb


def test_round_trip_preserves_state(tmp_path):
    bb = _bb(tmp_path)
    meta = save(bb, "before plan gate", phase="plan")
    back, warnings = load(str(tmp_path / "out"), meta["id"])

    assert back.input_dir == bb.input_dir
    assert [p.target_name for p in back.plan] == ["PricingService"]
    assert back.plan[0].native_recommendation == "Salesforce CPQ"
    assert back.artifacts[0].main_class == "public class PricingService {}"
    assert back.decisions[0]["agent"] == "Planner"


def test_sets_survive_as_sets(tmp_path):
    """A list here would still pass `in` checks and fail the first set operation."""
    bb = _bb(tmp_path)
    meta = save(bb, "s", phase="plan")
    back, _ = load(str(tmp_path / "out"), meta["id"])

    req = back.schema["Order__c"]["required"]
    assert isinstance(req, set), f"required came back as {type(req).__name__}"
    assert req == {"Total__c", "Status__c"}
    assert isinstance(back.schema["Order__c"]["unique"], set)
    # And it still behaves like one.
    assert req | {"X"} == {"Total__c", "Status__c", "X"}


def test_restored_plan_items_are_dataclasses_not_dicts(tmp_path):
    bb = _bb(tmp_path)
    meta = save(bb, "s")
    back, _ = load(str(tmp_path / "out"), meta["id"])
    assert isinstance(back.plan[0], PlanItem)
    assert isinstance(back.artifacts[0], Artifact)
    assert back.plan[0].is_code is True          # the property still works


def test_the_live_callback_is_not_captured(tmp_path):
    """on_decision belongs to the process that made it, not to the state."""
    bb = _bb(tmp_path)
    bb.on_decision = lambda e: None
    meta = save(bb, "s")
    raw = json.loads(gzip.decompress(
        (_dir(str(tmp_path / "out")) / f"{meta['id']}{_SUFFIX}").read_bytes()))
    assert "on_decision" not in raw["state"]
    back, _ = load(str(tmp_path / "out"), meta["id"])
    assert back.on_decision is None


def test_generated_files_on_disk_are_flagged_as_not_belonging_to_the_snapshot(tmp_path):
    """The trap this exists to prevent: a restored plan read beside someone else's code."""
    bb = _bb(tmp_path)
    meta = save(bb, "s")
    cls = tmp_path / "out" / "force-app" / "main" / "default" / "classes"
    cls.mkdir(parents=True)
    (cls / "Other.cls").write_text("public class Other {}")

    _, warnings = load(str(tmp_path / "out"), meta["id"])
    assert any("belong to whatever ran last" in w for w in warnings)


def test_missing_source_repository_is_reported(tmp_path):
    bb = _bb(tmp_path)
    meta = save(bb, "s")
    (tmp_path / "src").rmdir()
    _, warnings = load(str(tmp_path / "out"), meta["id"])
    assert any("no longer exists" in w for w in warnings)


def test_a_clean_restore_warns_about_nothing(tmp_path):
    bb = _bb(tmp_path)
    meta = save(bb, "s")
    _, warnings = load(str(tmp_path / "out"), meta["id"])
    assert warnings == []


def test_unknown_fields_from_an_older_checkpoint_are_dropped(tmp_path):
    """A checkpoint written before a field was removed must still load."""
    bb = _bb(tmp_path)
    meta = save(bb, "s")
    path = _dir(str(tmp_path / "out")) / f"{meta['id']}{_SUFFIX}"
    raw = json.loads(gzip.decompress(path.read_bytes()))
    raw["plan"][0]["a_field_we_deleted"] = "x"
    path.write_bytes(gzip.compress(json.dumps(raw).encode()))
    back, _ = load(str(tmp_path / "out"), meta["id"])
    assert back.plan[0].target_name == "PricingService"


def test_a_future_format_is_refused_rather_than_misread(tmp_path):
    bb = _bb(tmp_path)
    meta = save(bb, "s")
    path = _dir(str(tmp_path / "out")) / f"{meta['id']}{_SUFFIX}"
    raw = json.loads(gzip.decompress(path.read_bytes()))
    raw["format"] = 99
    path.write_bytes(gzip.compress(json.dumps(raw).encode()))
    with pytest.raises(ValueError, match="different version"):
        load(str(tmp_path / "out"), meta["id"])


def test_a_corrupt_checkpoint_does_not_hide_the_intact_ones(tmp_path):
    bb = _bb(tmp_path)
    save(bb, "good one")
    (_dir(str(tmp_path / "out")) / f"broken{_SUFFIX}").write_bytes(b"not gzip at all")
    rows = list_all(str(tmp_path / "out"))
    assert [r["name"] for r in rows] == ["good one"]


def test_listing_is_newest_first(tmp_path):
    bb = _bb(tmp_path)
    a = save(bb, "first")
    b = save(bb, "second")
    ids = [r["id"] for r in list_all(str(tmp_path / "out"))]
    assert ids.index(b["id"]) < ids.index(a["id"])


# ── comparing two plans: the reason to keep more than one ────────────────────

def test_diff_reports_a_changed_plan_decision(tmp_path):
    out = str(tmp_path / "out")
    a = save(_bb(tmp_path), "before", phase="plan")
    b = save(_bb(tmp_path, skip=True), "after", phase="plan")

    d = diff(out, a["id"], b["id"])
    assert d["summary"]["plan_changed"] == 1
    assert d["plan_changes"][0] == {
        "target": "PricingService", "kind": "changed", "from": "Convert", "to": "Skip",
        "from_native": "Salesforce CPQ", "to_native": "Salesforce CPQ"}
    assert d["summary"]["convert_delta"] == -1
    assert "plan decision(s) differ" in headline(d)


def test_diff_of_identical_checkpoints_says_so(tmp_path):
    out = str(tmp_path / "out")
    a = save(_bb(tmp_path), "one")
    b = save(_bb(tmp_path), "two")
    assert headline(diff(out, a["id"], b["id"])).startswith("Identical")


def test_diff_notices_regenerated_code(tmp_path):
    out = str(tmp_path / "out")
    a = save(_bb(tmp_path), "one")
    bb2 = _bb(tmp_path)
    bb2.artifacts[0].main_class = "public class PricingService { /* different */ }"
    b = save(bb2, "two")

    d = diff(out, a["id"], b["id"])
    assert d["artifact_changes"][0]["kind"] == "regenerated"


def test_diff_flags_when_the_source_differed(tmp_path):
    """Otherwise a difference caused by the repo reads as a difference caused by a choice."""
    out = str(tmp_path / "out")
    a = save(_bb(tmp_path), "one")
    bb2 = _bb(tmp_path)
    bb2.all_classes[0]["source"] = "class A { int x; }"
    b = save(bb2, "two")

    d = diff(out, a["id"], b["id"])
    assert d["same_source"] is False
    assert "different source" in headline(d)  # never silently "identical"
