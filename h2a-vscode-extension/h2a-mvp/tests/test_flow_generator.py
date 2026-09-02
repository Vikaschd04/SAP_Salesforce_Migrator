"""A Hybris process becomes a Flow whose shape can be checked against the source.

The topology is deterministic, so these tests pin it exactly. The two inferred parts —
outcome names and what passes between steps — are asserted to be *reported*, because the
failure that matters here is not a wrong Flow, it is a wrong Flow presented as a finished
migration.
"""
import xml.etree.ElementTree as ET

import pytest

from src.flow_generator import (build_flow, build_invocable, _iso8601_to_minutes,
                                _safe, _label)
from src.processes import parse_process

NS = {"f": "http://soap.sforce.com/2006/04/metadata"}

PROC = """<?xml version="1.0" encoding="UTF-8"?>
<process xmlns="http://www.hybris.de/xsd/processdefinition"
         name="order-fulfilment" start="checkOrder" onError="handleFailure">
  <action id="checkOrder" bean="checkOrderAction">
    <transition name="OK" to="authorize"/>
    <transition name="NOK" to="handleFailure"/>
  </action>
  <action id="authorize" bean="authorizePaymentAction">
    <transition name="OK" to="waitForWarehouse"/>
    <transition name="DECLINED" to="handleFailure"/>
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
</process>
"""

CONVERTED = {"CheckOrderAction", "AuthorizePaymentAction", "SendOrderConfirmationAction"}


@pytest.fixture
def flow(tmp_path):
    f = tmp_path / "order-fulfilment-process.xml"
    f.write_text(PROC, encoding="utf-8")
    proc = parse_process(str(f), CONVERTED)
    return build_flow(proc, CONVERTED)


def _root(flow):
    return ET.fromstring(flow["xml"])


def test_the_flow_is_well_formed_metadata(flow):
    root = _root(flow)
    assert root.tag.endswith("Flow")
    assert root.find("f:processType", NS).text == "AutoLaunchedFlow"


def test_it_deploys_as_draft(flow):
    """An unreviewed translation of an order pipeline must not be activatable by an
    accidental deploy."""
    assert _root(flow).find("f:status", NS).text == "Draft"


def test_start_points_at_the_hybris_start_action(flow):
    start = _root(flow).find("f:start", NS)
    assert start.find("f:connector/f:targetReference", NS).text == "checkOrder"


def test_every_action_becomes_an_element(flow):
    names = {e.find("f:name", NS).text
             for e in _root(flow).findall("f:actionCalls", NS)}
    assert names == {"checkOrder", "authorize", "confirm", "handleFailure"}


def test_a_branch_becomes_a_decision_on_the_hybris_transition_names(flow):
    d = next(e for e in _root(flow).findall("f:decisions", NS)
             if e.find("f:name", NS).text == "authorize_Outcome")
    labels = [r.find("f:label", NS).text for r in d.findall("f:rules", NS)]
    # Last transition becomes the default path, so two rules + one default for three ways.
    assert labels == ["OK", "DECLINED"]
    assert d.find("f:defaultConnectorLabel", NS).text == "RETRY"
    cond = d.find("f:rules/f:conditions/f:rightValue/f:stringValue", NS)
    assert cond.text == "OK"


def test_a_single_outcome_connects_straight_through(flow):
    confirm = next(e for e in _root(flow).findall("f:actionCalls", NS)
                   if e.find("f:name", NS).text == "confirm")
    assert confirm.find("f:connector/f:targetReference", NS).text == "done"
    assert not [d for d in _root(flow).findall("f:decisions", NS)
                if d.find("f:name", NS).text == "confirm_Outcome"]


def test_a_wait_becomes_a_pause_with_the_timeout_converted(flow):
    w = _root(flow).find("f:waits", NS)
    assert w.find("f:name", NS).text == "waitForWarehouse"
    mins = w.find("f:waitEvents/f:inputParameters/f:value/f:numberValue", NS)
    assert mins.text == "240.0"                       # PT4H
    assert w.find("f:defaultConnector/f:targetReference", NS).text == "confirm"


def test_the_unwired_resume_event_is_reported_not_hidden(flow):
    """A pause that silently never resumes would be the worst possible outcome here."""
    assert any("resume event is not wired" in n for n in flow["review_notes"])


def test_steps_with_no_converted_apex_are_present_but_inert(flow):
    """The shape of the process must survive even where the code did not."""
    hf = next(e for e in _root(flow).findall("f:actionCalls", NS)
              if e.find("f:name", NS).text == "handleFailure")
    assert hf.find("f:actionName", NS).text == "__NOT_MIGRATED__"
    assert "wire an @InvocableMethod" in hf.find("f:description", NS).text
    assert any("handleFailure" in n and "no converted Apex" in n
               for n in flow["review_notes"])


def test_wired_steps_call_their_invocable(flow):
    co = next(e for e in _root(flow).findall("f:actionCalls", NS)
              if e.find("f:name", NS).text == "checkOrder")
    assert co.find("f:actionName", NS).text == "CheckOrderActionInvocable"
    assert flow["invocables"]["CheckOrderAction"] == "CheckOrderActionInvocable"


def test_coverage_counts_what_is_actually_wired(flow):
    # checkOrder, authorize, confirm, handleFailure — the wait is counted separately
    assert flow["coverage"] == {"actions": 4, "wired": 3, "waits": 1, "ends": 1}


def test_inferred_outcome_names_are_flagged_for_review(flow):
    """The Flow branches on a string the converted Apex has to return. If the Builder
    renamed it the Flow is wrong, so every branch says so."""
    assert any("branches 3 ways" in n for n in flow["review_notes"])
    assert any("check the converted class still uses them" in n
               for n in flow["review_notes"])


def test_the_description_does_not_claim_completeness(flow):
    desc = _root(flow).find("f:description", NS).text
    assert "topology is a faithful translation" in desc
    assert "need review" in desc


# ── the wrapper the Flow calls ────────────────────────────────────────────────

def test_invocable_is_bulk_safe_and_says_what_is_left_to_do():
    src = build_invocable("CheckOrderAction")
    assert "@InvocableMethod" in src
    assert "List<Request> requests" in src and "for (Request req : requests)" in src
    assert "TODO" in src                       # the mapping is the human's job
    assert "with sharing" in src


# ── units ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("iso,mins", [
    ("PT4H", 240), ("PT30M", 30), ("P1D", 1440), ("P1DT2H30M", 1590),
    ("", None), ("garbage", None), ("PT45S", 1),
])
def test_iso8601_durations(iso, mins):
    assert _iso8601_to_minutes(iso) == mins


@pytest.mark.parametrize("raw,api", [
    ("order-fulfilment", "order_fulfilment"), ("2ndStep", "X2ndStep"),
    ("a  b", "a_b"), ("", "Step"),
])
def test_api_names_are_valid_for_salesforce(raw, api):
    assert _safe(raw) == api


def test_labels_are_readable_on_the_canvas():
    assert _label("authorizePayment") == "Authorize Payment"


def test_an_empty_process_does_not_explode(tmp_path):
    f = tmp_path / "empty-process.xml"
    f.write_text('<process xmlns="http://www.hybris.de/xsd/processdefinition" '
                 'name="empty"/>', encoding="utf-8")
    out = build_flow(parse_process(str(f), set()), set())
    ET.fromstring(out["xml"])
    assert out["coverage"]["actions"] == 0
