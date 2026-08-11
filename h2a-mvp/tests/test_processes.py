"""A business process must never be able to vanish without trace.

Before these files were read at all, a Hybris process could not be reported as missing:
it was absent from the completeness ledger rather than listed in it. The action classes
converted, so the output looked complete while the orchestration — the order the actions
run in, the branches, the error paths — was simply gone. These tests pin that shut.
"""
import pytest

from src.processes import (parse_process, discover, summarise, headline,
                           ledger_rows, covered_classes, _bean_to_class)

PROC = """<?xml version="1.0" encoding="UTF-8"?>
<process xmlns="http://www.hybris.de/xsd/processdefinition"
         name="order-fulfilment" start="checkOrder" onError="handleFailure"
         processClass="de.hybris.platform.orderprocessing.model.OrderProcessModel">
  <action id="checkOrder" bean="checkOrderAction">
    <transition name="OK" to="authorize"/>
    <transition name="NOK" to="handleFailure"/>
  </action>
  <action id="authorize" bean="acmecore.authorizePaymentAction">
    <transition name="OK" to="waitForWarehouse"/>
    <transition name="RETRY" to="authorize"/>
  </action>
  <wait id="waitForWarehouse" then="confirm">
    <event>WarehouseConfirmedEvent</event>
    <timeout delay="PT4H" then="handleFailure"/>
  </wait>
  <action id="confirm" bean="sendOrderConfirmationAction">
    <transition name="OK" to="done"/>
  </action>
  <action id="handleFailure" bean="handleFailureAction"/>
  <end id="done" state="SUCCEEDED">Fulfilled.</end>
  <end id="failed" state="ERROR">Failed.</end>
</process>
"""

NAMES = {"CheckOrderAction", "AuthorizePaymentAction", "SendOrderConfirmationAction"}


@pytest.fixture
def proc(tmp_path):
    f = tmp_path / "order-fulfilment-process.xml"
    f.write_text(PROC, encoding="utf-8")
    return parse_process(str(f), NAMES)


def test_parses_the_state_machine(proc):
    assert proc["name"] == "order-fulfilment"
    assert proc["start"] == "checkOrder"
    assert proc["on_error"] == "handleFailure"
    assert [a["id"] for a in proc["actions"]] == [
        "checkOrder", "authorize", "confirm", "handleFailure"]
    assert {e["id"] for e in proc["end_states"]} == {"done", "failed"}


def test_counts_flow_nodes_and_transitions(proc):
    """The wait is why a process is not just a list of classes."""
    assert proc["flow_nodes"] == 1                     # the <wait>
    # Five named transitions on the actions, plus the wait's `then` and its timeout's
    # `then`. Both are edges someone has to rebuild, so both are counted.
    assert proc["transitions"] == 7


def test_resolves_beans_to_ingested_classes(proc):
    by_id = {a["id"]: a for a in proc["actions"]}
    assert by_id["checkOrder"]["implemented_by"] == "CheckOrderAction"
    # A namespace-qualified bean id still resolves.
    assert by_id["authorize"]["implemented_by"] == "AuthorizePaymentAction"


def test_an_unresolved_bean_is_reported_not_guessed(proc):
    """Beans often live in Spring XML we do not parse. Naming a class we never saw
    would be worse than admitting we could not find it."""
    by_id = {a["id"]: a for a in proc["actions"]}
    assert by_id["handleFailure"]["implemented_by"] == ""
    assert by_id["handleFailure"]["bean"] == "handleFailureAction"


def test_bean_resolution_never_invents_a_class():
    assert _bean_to_class("somethingElseAction", NAMES) == ""
    assert _bean_to_class("", NAMES) == ""


# ── the point of the whole feature ────────────────────────────────────────────

def test_ledger_records_the_process_as_manual(proc):
    rows = ledger_rows([proc], converted={"CheckOrderAction", "AuthorizePaymentAction"})
    assert len(rows) == 1
    assert rows[0]["outcome"] == "manual"
    assert rows[0]["layer"] == "Process"
    assert "2 action classes converted" in rows[0]["note"]
    assert "did not" in rows[0]["note"]


def test_a_process_appears_in_the_blackboard_ledger(tmp_path):
    """The regression: with processes unread, this row did not exist at all."""
    from src.agentic.blackboard import Blackboard, Artifact
    bb = Blackboard(input_dir=str(tmp_path), output_dir=str(tmp_path / "out"))
    a = Artifact(target_name="CheckOrderAction", layer="Service")
    a.source_classes = [{"class_name": "CheckOrderAction", "layer": "Service",
                         "file": "CheckOrderAction.java"}]
    bb.artifacts = [a]
    bb.all_classes = list(a.source_classes)
    f = tmp_path / "p-process.xml"
    f.write_text(PROC, encoding="utf-8")
    bb.processes = [parse_process(str(f), NAMES)]

    rows = bb.completeness_ledger()
    proc_rows = [r for r in rows if r["layer"] == "Process"]
    assert len(proc_rows) == 1, "the process is missing from the completeness ledger"
    assert proc_rows[0]["outcome"] == "manual"
    # And the action class that did convert is still reported as converted.
    assert any(r["source"] == "CheckOrderAction" and r["outcome"] == "converted"
               for r in rows)


def test_no_processes_means_no_rows_and_no_noise():
    from src.agentic.blackboard import Blackboard
    bb = Blackboard(input_dir="/in", output_dir="/out")
    assert bb.completeness_ledger() == []
    assert "No Hybris business processes" in headline(summarise([]))


# ── robustness on real estates ────────────────────────────────────────────────

def test_identified_by_root_element_not_filename(tmp_path):
    """Teams rename these; and an items.xml inside a folder called `process` must not
    be mistaken for one."""
    (tmp_path / "weird-name.xml").write_text(PROC, encoding="utf-8")
    (tmp_path / "process" ).mkdir()
    (tmp_path / "process" / "acme-items.xml").write_text(
        '<?xml version="1.0"?><items><itemtype code="Order"/></items>', encoding="utf-8")
    found = discover(str(tmp_path), NAMES)
    assert [p["name"] for p in found] == ["order-fulfilment"]


def test_malformed_process_is_reported_rather_than_skipped(tmp_path):
    f = tmp_path / "broken-process.xml"
    f.write_text("<process><action id='a'</process>", encoding="utf-8")
    rec = parse_process(str(f))
    assert rec["unreadable"]
    rows = ledger_rows([rec])
    assert rows[0]["outcome"] == "unreadable"
    assert "migrate by hand" in rows[0]["note"]


def test_non_process_xml_is_ignored(tmp_path):
    f = tmp_path / "acme-items.xml"
    f.write_text('<?xml version="1.0"?><items><itemtype code="Order"/></items>',
                 encoding="utf-8")
    assert parse_process(str(f)) is None


def test_summary_and_covered_classes(proc):
    s = summarise([proc])
    assert s == {"processes": 1, "actions": 4, "actions_resolved": 3,
                 "unreadable": 0, "transitions": 7}
    assert covered_classes([proc]) == NAMES
    assert "1 business process found" in headline(s)   # not "1 process(es)"


def test_document_leads_with_the_loss(tmp_path, proc):
    from src.processes import write_processes_md
    path = write_processes_md(str(tmp_path), [proc])
    text = open(path, encoding="utf-8").read()
    assert "not migrated" in text.lower()
    assert "pieces without the wiring" in text
    # the unresolved beans are named, not hidden
    assert "handleFailureAction" in text
    assert text.index("You are holding the pieces") < text.index("| Step |")


def test_the_reference_corpus_has_one(tmp_path):
    """Guards the sample too — a demo that lost its process would hide the feature."""
    found = discover("../Testing/acme-commerce-hybris", set())
    assert [p["name"] for p in found] == ["order-fulfilment-process"]
    assert len(found[0]["actions"]) == 9
