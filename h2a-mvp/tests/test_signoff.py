"""The contract's value is in what it refuses to claim.

Most of these tests assert the *absence* of assurance: that an unattended run cannot be
made to look approved, that unproven things stay listed as unproven, and that the actor
is whoever the server established rather than whoever asked.
"""
import pytest

from src.agentic.blackboard import Blackboard, Artifact
from src.signoff import build_signoff, write_signoff_md, headline


def _bb(**kw):
    bb = Blackboard(input_dir="/in", output_dir="/out")
    a = Artifact(target_name="PricingService", layer="Service")
    a.source_classes = [{"class_name": "DefaultPricingService", "layer": "Service",
                         "file": "DefaultPricingService.java", "source": "class X {}"}]
    a.main_class = "public class PricingService { public void applyDiscount() {} }"
    bb.artifacts.append(a)
    bb.all_classes = list(a.source_classes)
    for k, v in kw.items():
        setattr(bb, k, v)
    return bb


def _approve(bb, gate, actor="ada@example.com", supervised=True):
    bb.approvals.append({"gate": gate, "action": "approve", "actor": actor,
                         "supervised": supervised, "at": "2026-08-10T12:00:00+00:00",
                         "note": ""})


# ── an unattended run must never read as an approved one ──────────────────────

def test_unattended_run_is_reported_as_unreviewed():
    c = build_signoff(_bb())
    assert c["supervised"] is False
    assert "Unreviewed" in headline(c)
    assert any("No human reviewed" in x for x in c["caveats"])


def test_auto_approval_does_not_count_as_review():
    bb = _bb()
    _approve(bb, "discovery", actor=None, supervised=False)
    c = build_signoff(bb)
    assert c["supervised"] is False
    assert c["gates_reviewed_by_a_human"] == []
    assert "discovery" in c["gates_auto_approved"]


def test_a_gate_callback_that_failed_is_not_a_human_decision():
    """The reviewer was asked and no answer came. Approving is fine; filing it as a
    human approval is not."""
    bb = _bb()
    _approve(bb, "plan", actor=None, supervised=False)
    bb.approvals[-1]["note"] = "gate callback failed (TimeoutError)"
    c = build_signoff(bb)
    assert c["supervised"] is False


def test_partial_supervision_names_the_gates_nobody_reviewed():
    bb = _bb()
    _approve(bb, "discovery")
    c = build_signoff(bb)
    assert c["supervised"] is True
    assert c["gates_reviewed_by_a_human"] == ["discovery"]
    assert any("Auto-approved without a reviewer" in x and "Plan" in x and "Build" in x
               for x in c["caveats"])


# ── unproven things stay listed as unproven ───────────────────────────────────

def test_never_deployed_is_always_called_out():
    c = build_signoff(_bb())
    assert c["org_verified"] is False
    assert any("never deployed" in x for x in c["caveats"])


def test_deploy_verification_is_recorded_when_the_org_accepted_it():
    c = build_signoff(_bb(), verified={"verified": True, "message": "Compiled cleanly."})
    assert c["org_verified"] is True
    assert not any("never deployed" in x for x in c["caveats"])


def test_dropped_rules_appear_in_the_caveats():
    bb = _bb(rule_ledger={"summary": {"total": 10, "asserted": 3, "implemented": 5,
                                      "at_risk": 1, "dropped": 2}})
    c = build_signoff(bb)
    joined = " ".join(c["caveats"])
    assert "2 extracted business rule(s) are carried by no generated artifact" in joined
    assert "1 business rule(s) are in artifacts that did not build" in joined
    assert "7 of 10 business rule(s) have no test asserting them" in joined


def test_no_recorded_behaviours_is_itself_a_caveat():
    """Silence about parity would read as parity."""
    c = build_signoff(_bb())
    assert any("nothing here is backed by golden-master parity" in x for x in c["caveats"])


def test_overwritten_outputs_reach_the_contract():
    bb = _bb()
    b = Artifact(target_name="PricingService", layer="Service")
    b.source_classes = [{"class_name": "PricingService", "layer": "Service",
                         "file": "PricingService.java", "source": "interface X {}"}]
    bb.artifacts.append(b)
    bb.all_classes = [c for a in bb.artifacts for c in a.source_classes]
    c = build_signoff(bb)
    assert c["completeness"].get("overwritten") == 2
    assert any("may not be in the output" in x or "another artifact also wrote" in x
               for x in c["caveats"])


# ── identity and reproducibility ──────────────────────────────────────────────

def test_reviewers_are_listed_once_each():
    bb = _bb()
    _approve(bb, "discovery"); _approve(bb, "plan"); _approve(bb, "build")
    c = build_signoff(bb)
    assert c["reviewers"] == ["ada@example.com"]
    assert "ada@example.com" in headline(c)


def test_contract_id_is_stable_for_the_same_facts():
    bb1, bb2 = _bb(), _bb()
    assert build_signoff(bb1)["contract_id"] == build_signoff(bb2)["contract_id"]


def test_contract_id_changes_when_a_certified_fact_changes():
    a = build_signoff(_bb())
    b = build_signoff(_bb(), verified={"verified": True})
    assert a["contract_id"] != b["contract_id"]


def test_document_renders_and_leads_with_the_weaker_reading(tmp_path):
    p = write_signoff_md(str(tmp_path), build_signoff(_bb()))
    text = open(p, encoding="utf-8").read()
    assert "# Migration Sign-Off Contract" in text
    assert "Unreviewed" in text
    assert "What this does **not** certify" in text
    # The banner must appear before the evidence, not after it.
    assert text.index("This run was unattended") < text.index("## 3. Evidence")


# ── stopping at a gate is not approving ───────────────────────────────────────

def test_stopping_at_a_gate_is_never_recorded_as_an_approval(tmp_path):
    """Cancelling used to inject `{"action": "approve"}` to unblock the paused engine
    thread, which meant a run the reviewer *stopped* was filed in this contract as one
    they approved — the precise overclaim the document exists to prevent."""
    from src.agentic.orchestrator import _run_gate
    from src.agentic.blackboard import Blackboard

    bb = Blackboard(input_dir=str(tmp_path), output_dir=str(tmp_path / "out"))
    _run_gate(lambda name, payload: {"action": "cancelled"},
              lambda *a, **k: None, "plan", {}, bb)

    entry = bb.approvals[-1]
    assert entry["action"] == "cancelled"
    assert entry["supervised"] is False
    assert "nothing was approved" in entry["note"]

    c = build_signoff(bb)
    assert c["supervised"] is False
    assert "plan" in c["gates_auto_approved"] or c["gates_reviewed_by_a_human"] == []
    assert "Unreviewed" in headline(c)


def test_a_real_approval_at_the_same_gate_still_counts(tmp_path):
    from src.agentic.orchestrator import _run_gate
    from src.agentic.blackboard import Blackboard

    bb = Blackboard(input_dir=str(tmp_path), output_dir=str(tmp_path / "out"))
    _run_gate(lambda name, payload: {"action": "approve", "actor": "ada@example.com"},
              lambda *a, **k: None, "plan", {}, bb)
    assert bb.approvals[-1]["supervised"] is True
    assert build_signoff(bb)["reviewers"] == ["ada@example.com"]
