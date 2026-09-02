"""Inputs accounted for is not the same claim as outputs being distinct.

The completeness ledger walks source -> artifact, and that check passes even when two
artifacts share a target name: each source still finds *an* artifact. But `write_outputs`
is last-write-wins, so one of them is not on disk, and the ledger reported a run as
complete while a class's logic was missing from the output. This is the check that the
input-side walk structurally cannot make.
"""
import pytest

from src.agentic.blackboard import Blackboard, Artifact


def _bb(*artifacts):
    bb = Blackboard(input_dir="/in", output_dir="/out")
    for a in artifacts:
        bb.artifacts.append(a)
    bb.all_classes = [c for a in artifacts for c in a.source_classes]
    return bb


def _art(target, layer, *sources):
    a = Artifact(target_name=target, layer=layer)
    a.source_classes = [{"class_name": s, "layer": layer, "file": f"{s}.java"} for s in sources]
    return a


def test_no_collision_when_targets_are_distinct():
    bb = _bb(_art("PricingService", "Service", "DefaultPricingService"),
             _art("OrderService", "Service", "DefaultOrderService"))
    assert bb.output_collisions() == {}
    assert {r["outcome"] for r in bb.completeness_ledger()} == {"converted"}


def test_two_artifacts_writing_one_file_are_caught():
    """The interface/impl pairing bug: both halves resolved to `PricingService`."""
    bb = _bb(_art("PricingService", "Service", "PricingService"),
             _art("PricingService", "Service", "DefaultPricingService"))

    coll = bb.output_collisions()
    assert list(coll) == ["PricingService.cls"]
    assert len(coll["PricingService.cls"]) == 2

    rows = {r["source"]: r for r in bb.completeness_ledger()}
    # Both are reported, not just one: last-write-wins means the survivor depends on
    # iteration order, so naming a winner would be a guess presented as a fact.
    assert rows["PricingService"]["outcome"] == "overwritten"
    assert rows["DefaultPricingService"]["outcome"] == "overwritten"
    assert "may not be in the output" in rows["PricingService"]["note"]


def test_the_old_check_would_have_passed():
    """Proves the gap was real: nothing is unaccounted for, yet a file was lost."""
    bb = _bb(_art("PricingService", "Service", "PricingService"),
             _art("PricingService", "Service", "DefaultPricingService"))
    ledger = bb.completeness_ledger()
    assert not any(r["outcome"] == "unaccounted" for r in ledger)
    assert any(r["outcome"] == "overwritten" for r in ledger)


def test_apex_and_lwc_sharing_a_name_do_not_collide():
    """`Pricing.cls` and `lwc/Pricing` are different files and must not be flagged."""
    bb = _bb(_art("Pricing", "Service", "PricingService"),
             _art("Pricing", "Component", "PricingComponent"))
    assert bb.output_collisions() == {}
    assert {r["outcome"] for r in bb.completeness_ledger()} == {"converted"}


def test_three_way_collision_reports_every_member():
    bb = _bb(_art("Svc", "Service", "A"), _art("Svc", "Service", "B"),
             _art("Svc", "Service", "C"))
    assert len(bb.output_collisions()["Svc.cls"]) == 3
    assert all(r["outcome"] == "overwritten" for r in bb.completeness_ledger())


def test_flagged_artifacts_still_report_collision_first():
    """A review flag is advice; an overwritten file is missing logic. Loss wins."""
    a = _art("PricingService", "Service", "DefaultPricingService")
    a.review_flags = ["consider CPQ"]
    bb = _bb(a, _art("PricingService", "Service", "PricingService"))
    rows = {r["source"]: r for r in bb.completeness_ledger()}
    assert rows["DefaultPricingService"]["outcome"] == "overwritten"
