"""What each Magento unit becomes on SAP Hybris. [3.2b]

Until this existed every unit rendered as a service, which is right for a Model and wrong
for everything Magento uses to *intercept* behaviour. A plugin quietly emitted as a service
is a plugin that never runs.

The decision the module exists for is the `around` plugin. Magento lets it decline to call
`$proceed`, so the original never executes; a Hybris interceptor runs *alongside* an
operation and cannot replace one. Route that to an interceptor and the generated code
always calls through: it compiles, it deploys, nothing in review looks odd, and a rule that
could short-circuit an order total silently stops being able to.
"""

from pathlib import Path

import pytest

from src.adapters.hybris_plan import (DECORATOR, EVENT_LISTENER, INTERCEPTOR, JOB, MANUAL,
                                      SERVICE, plan_report, plan_targets)

MAGENTO = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")


class _U:
    def __init__(self, name, layer, fqn=None):
        self.name, self.layer = name, layer
        self.source, self.file = "", ""
        self.extra = {"fqn": fqn or f"Acme\\Loyalty\\{name}"}


@pytest.fixture(scope="module")
def model():
    from src.adapters.php_reader import available
    if not available():
        pytest.skip("tree-sitter-php not installed")
    from src.adapters.adobe_source import ADAPTER
    return ADAPTER.read(MAGENTO)


@pytest.fixture(scope="module")
def report(model):
    return plan_report(model.units + model.tests + model.skipped, model.extra["di"])


def _kind(report, source):
    return next(t["kind"] for t in report["targets"]
                if any(c["class_name"] == source for c in t["source_classes"]))


# ── the decision this module exists for ───────────────────────────────────────

def test_an_around_plugin_that_skips_proceed_becomes_a_decorator(report):
    assert _kind(report, "OrderTotalPlugin") == DECORATOR


def test_the_decorator_choice_explains_itself(report):
    why = next(t["rationale"] for t in report["targets"]
               if t["kind"] == DECORATOR)
    assert "without calling $proceed" in why
    assert "cannot replace one" in why


def test_a_plugin_that_always_proceeds_becomes_an_interceptor(report):
    assert _kind(report, "SubtotalPlugin") == INTERCEPTOR


def test_an_unclassifiable_plugin_takes_the_safe_superset():
    """A decorator expresses everything an interceptor can *and* skipping; an interceptor
    cannot express skipping. The failure directions are not symmetric — an unnecessary
    decorator is ceremony, a missing one is a rule that stopped working."""
    t = plan_targets([_U("MysteryPlugin", "Plugin")], wiring=None)[0]
    assert t["kind"] == DECORATOR
    assert "could not be classified" in t["rationale"]
    assert "not symmetric" in t["rationale"]


# ── the rest of the routing ───────────────────────────────────────────────────

def test_observers_become_event_listeners_and_the_caveat_travels(report):
    assert _kind(report, "AwardPointsObserver") == EVENT_LISTENER
    why = next(t["rationale"] for t in report["targets"]
               if t["kind"] == EVENT_LISTENER)
    assert "synchronously" in why and "EventService does neither" in why


def test_cron_becomes_a_job_performable_and_mentions_node_affinity(report):
    assert _kind(report, "ExpirePoints") == JOB
    why = next(t["rationale"] for t in report["targets"] if t["kind"] == JOB)
    assert "node affinity" in why


def test_a_trait_is_routed_to_a_human():
    t = plan_targets([_U("LoggerTrait", "Trait")])[0]
    assert t["kind"] == MANUAL and "single inheritance" in t["rationale"]


def test_a_unit_with_no_inferable_layer_is_not_guessed_at():
    """Guessing a target from a class name would be a guess about its behaviour."""
    t = plan_targets([_U("Mystery", "")])[0]
    assert t["kind"] == MANUAL
    assert "never established" in t["rationale"]


# ── the interface pairing ─────────────────────────────────────────────────────

def test_an_interface_and_its_implementation_become_one_service(report):
    """Magento's `PricingServiceInterface` + `PricingService` is Hybris's
    `PricingService` + `DefaultPricingService` — one contract, not two services."""
    svc = [t for t in report["targets"] if t["kind"] == SERVICE]
    assert len(svc) == 1
    assert svc[0]["target_name"] == "PricingService"
    assert {c["class_name"] for c in svc[0]["source_classes"]} == {
        "PricingServiceInterface", "PricingService"}


def test_the_merged_target_keeps_both_reasons(report):
    svc = next(t for t in report["targets"] if t["kind"] == SERVICE)
    assert "; also " in svc["rationale"]


# ── accounting ────────────────────────────────────────────────────────────────

def test_every_unit_is_either_planned_or_skipped_with_a_reason(report, model):
    everything = model.units + model.tests + model.skipped
    assert report["accounted"] == len(everything)
    assert report["unaccounted"] == [], "a unit in neither list is a unit lost"


def test_counting_targets_would_understate_it(report):
    """Two units merged into one target. Counting targets reported 10 of 11 and looked
    like a missing unit; counting *units represented* is the question actually being
    asked."""
    assert len(report["targets"]) < report["accounted"]


def test_tests_and_scripts_are_skipped_positively(report):
    reasons = {s["source"]: s["reason"] for s in report["skipped"]}
    assert "recorded behaviour" in reasons["PricingServiceTest"]
    assert "not migratable code" in reasons["registration"]


def test_every_target_carries_a_rationale(report):
    for t in report["targets"]:
        assert len(t["rationale"]) > 40, t["target_name"]


def test_the_adapter_exposes_the_planner():
    from src.adapters.hybris_target import ADAPTER

    got = ADAPTER.plan([_U("Thing", "Model")], {})
    assert got[0]["kind"] == SERVICE
