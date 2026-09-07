"""Tell the model what the emitter is about to write. [1.51]

Three consecutive real runs merged almost nothing, and each time the cause looked
different: the emitter dropped the artifacts (1.48), the merge was keyed on the source
name (1.48), the service target came back as an interface (1.48). They were one cause
wearing three hats. Nobody had ever told the model what to name anything.

It was asked to migrate a PHP class and left to infer the target's shape, so a job came
back with `execute`, a listener with `perform`, an interceptor with `onValidate` where the
emitter had derived `onPrepare`. Good logic, discarded on arrival for wearing the wrong
name — and guessing was never the model's job, because the emitter knew the answer the
whole time and had simply never said it.

Every string below is derived from the same helpers the emitters call, so a contract that
promises something the emitted class does not declare is a test failure rather than a
silent discard.
"""

import pytest

from src.adapters.hybris_plan import (DECORATOR, EVENT_LISTENER, INTERCEPTOR, JOB,
                                      SERVICE)
from src.adapters.hybris_target import ADAPTER, target_contract


class _M:
    def __init__(self, name, visibility="public"):
        self.name, self.visibility = name, visibility


def _contract(kind, target="T", methods=("doThing",)):
    return target_contract(kind, target, [_M(m) for m in methods])


# ── each kind is told its own entry point ─────────────────────────────────────

def test_a_job_is_told_to_write_perform():
    """`perform` is the platform's entry point. A method named after the PHP one is
    never called — the class compiles, deploys, and does nothing."""
    got = _contract(JOB, "ExpirePointsJobPerformable", ["execute"])
    assert "PerformResult perform(final CronJobModel cronJob)" in got
    assert "AbstractJobPerformable<CronJobModel>" in got
    assert "ExpirePointsJobPerformable" in got


def test_a_listener_is_told_to_write_on_event():
    got = _contract(EVENT_LISTENER, "TierCheckObserverListener", ["execute"])
    assert "void onEvent(final E event)" in got


def test_an_interceptor_is_told_which_hook_it_declares():
    """The hook is derived from the plugin's prefix. The model wrote `onValidate` on a
    class the emitter had declared with `onPrepare`, and the two are not interchangeable:
    one may reject the model and the other may not."""
    assert "void onPrepare(" in _contract(INTERCEPTOR, "P", ["beforeSave"])
    assert "void onValidate(" in _contract(INTERCEPTOR, "P", ["aroundSave"])


def test_the_interceptor_contract_matches_the_class_the_emitter_writes():
    """Derived by the same function, so the two cannot drift."""
    from src.adapters.hybris_hooks import build_interceptor, interceptor_hook

    unit = type("U", (), {"name": "SubtotalPlugin", "file": "a.php", "extra": {},
                          "methods": [_M("beforeSave")]})()
    emitted = build_interceptor(unit, "com.x", {})
    hook = interceptor_hook(unit)
    assert f"public void {hook}(" in emitted
    assert f"void {hook}(" in _contract(INTERCEPTOR, "P", ["beforeSave"])


def test_a_decorator_is_told_the_wrapped_names():
    """`aroundGetGrandTotal` in the source becomes `getGrandTotal` on the target. The
    model wrote the source name and it matched nothing."""
    from src.adapters.hybris_hooks import wrapped_method

    got = _contract(DECORATOR, "OrderTotalPluginDecorator", ["aroundGetGrandTotal"])
    assert f"`{wrapped_method('aroundGetGrandTotal')}`" in got
    assert "(final Object... args)" in got


def test_a_service_is_told_to_write_the_implementation():
    """`PricingService` on this platform is the *interface*, and asking for it got one —
    correct, and useless: the interface is derived, the logic is not."""
    got = _contract(SERVICE, "DefaultPricingService", ["applySpendDiscount"])
    assert "implementation" in got and "DefaultPricingService" in got
    assert "you do not need to write it" in got


def test_a_service_method_is_named_the_way_the_signature_will_be():
    from src.adapters.hybris_service import _camel

    got = _contract(SERVICE, "DefaultPricingService", ["apply_spend_discount"])
    assert f"`{_camel('apply_spend_discount')}`" in got


# ── what it refuses to claim ──────────────────────────────────────────────────

def test_a_kind_with_no_emitter_promises_nothing():
    """Inventing a shape for a target nobody emits would be worse than silence: the model
    would write to a contract the migration never honours."""
    assert target_contract("manual", "T", [_M("x")]) == ""
    assert target_contract("", "T", [_M("x")]) == ""


def test_the_contract_says_what_happens_to_a_body_that_misses():
    """A model that knows *why* the names matter writes better ones than one told only
    to obey."""
    got = _contract(JOB, "J", ["execute"])
    assert "discarded" in got and "by method name" in got.replace("**", "")


def test_an_honest_gap_is_asked_for_rather_than_an_invented_one():
    assert "honest gap is reviewable" in _contract(JOB, "J", ["execute"])


# ── the adapter seam ──────────────────────────────────────────────────────────

def test_the_target_exposes_it_so_the_builder_stays_platform_blind():
    """The Builder must not know which platform it is building for; it asks whatever
    target the pipeline gave it and uses whatever comes back."""
    item = type("P", (), {"kind": JOB, "target_name": "J"})()
    unit = type("U", (), {"methods": [_M("execute")]})()
    assert "perform(" in ADAPTER.contract_for(item, [unit])


def test_a_target_that_offers_no_contract_is_simply_not_asked():
    """Salesforce has no such notion, and its golden baseline proves the prompt on that
    path is byte-identical."""
    from src.adapters.salesforce_target import ADAPTER as sf

    assert not hasattr(sf, "contract_for")
