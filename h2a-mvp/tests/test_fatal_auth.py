"""A dead API key must stop the run, not quietly empty it.

This is the failure the first real-provider run actually hit: every comprehension
returned its deterministic fallback, the run completed, and the reports said the estate
carried no business rules. That is indistinguishable, to a reader, from an estate that
genuinely carries none — a confidently wrong answer, which is the one outcome the whole
proof track exists to prevent.
"""
import pytest

from src import llm
from src.llm import ProviderAuthError, is_fatal_auth, _with_retry, reset_call_log


class _Boom(Exception):
    def __init__(self, status):
        super().__init__(f"status {status}")
        self.status_code = status


class _NamedAuthError(Exception):
    """Providers whose SDK signals auth by type rather than status code."""


_NamedAuthError.__name__ = "AuthenticationError"


@pytest.fixture(autouse=True)
def _clean():
    reset_call_log()
    yield
    reset_call_log()


@pytest.mark.parametrize("status", [401, 403])
def test_auth_status_is_fatal(status):
    assert is_fatal_auth(_Boom(status))


@pytest.mark.parametrize("status", [429, 500, 529])
def test_transient_status_is_not_fatal(status):
    assert not is_fatal_auth(_Boom(status))


def test_named_auth_error_is_fatal():
    assert is_fatal_auth(_NamedAuthError())


def test_retry_converts_auth_error_and_does_not_retry():
    calls = []

    def fn():
        calls.append(1)
        raise _Boom(401)

    with pytest.raises(ProviderAuthError):
        _with_retry(fn, stage="comprehend_X", config={"resilience": {"max_attempts": 4}})
    assert len(calls) == 1, "a bad key must not be retried four times"


def test_latch_short_circuits_later_calls():
    """The second class must fail instantly rather than wait for its own 401."""
    def fn():
        raise _Boom(401)

    with pytest.raises(ProviderAuthError):
        _with_retry(fn, stage="comprehend_A", config={})

    reached = []

    def never():
        reached.append(1)
        return "ok"

    with pytest.raises(ProviderAuthError):
        _with_retry(never, stage="comprehend_B", config={})
    assert not reached, "the provider was called again after proving it cannot succeed"


def test_reset_call_log_clears_the_latch():
    """Otherwise one bad key would poison every later run in the same process —
    which, in the web backend, means every run until someone restarts it."""
    def fn():
        raise _Boom(401)

    with pytest.raises(ProviderAuthError):
        _with_retry(fn, stage="s", config={})
    reset_call_log()
    assert _with_retry(lambda: "ok", stage="s", config={}) == "ok"


def test_comprehend_does_not_fall_back_on_bad_credentials(monkeypatch):
    """The actual bug: containment turning a dead key into an empty understanding."""
    from src import comprehend

    def boom(*a, **k):
        raise ProviderAuthError("nope")

    monkeypatch.setattr(comprehend, "call_structured", boom)
    with pytest.raises(ProviderAuthError):
        comprehend.comprehend_class({"class_name": "DefaultPricingService",
                                     "layer": "Service", "source": "class X {}",
                                     "methods": []})


def test_comprehend_still_contains_ordinary_failures(monkeypatch):
    """The containment that was right all along must survive the fix."""
    from src import comprehend

    def boom(*a, **k):
        raise ValueError("unparseable response")

    monkeypatch.setattr(comprehend, "call_structured", boom)
    u = comprehend.comprehend_class({"class_name": "Odd", "layer": "Service",
                                     "source": "class X {}", "methods": []})
    assert u["business_rules"] == [] and u["purpose"]


def test_stage_boundary_stops_a_run_whose_stage_swallowed_it():
    """Belt and braces: even if some stage catches everything, the next stage stops."""
    from src.agentic.orchestrator import _make_emitter

    emit = _make_emitter(None)
    emit("stage", name="comprehend", status="start")      # fine before any failure

    def fn():
        raise _Boom(401)

    with pytest.raises(ProviderAuthError):
        _with_retry(fn, stage="comprehend_A", config={})

    with pytest.raises(ProviderAuthError):
        emit("stage", name="plan", status="start")
