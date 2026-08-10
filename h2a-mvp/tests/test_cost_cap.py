"""The forecast says what a run should cost; the cap is what makes that binding.

Without it the only thing standing between a non-converging repair loop and an unbounded
bill is that nobody has hit one yet.
"""
import pytest

from src import llm, pricing
from src.llm import CostCapExceeded, _with_retry, reset_accounting, reset_call_log


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("H2A_COST_CAP", raising=False)
    reset_accounting()
    reset_call_log()
    yield
    reset_accounting()
    reset_call_log()


def _spend(model="claude-opus-5", prompt=0, completion=0):
    """Record usage the way a real call does, so the cap sees real numbers."""
    llm._record("anthropic", prompt, completion, model=model)


CFG = {"cost_cap": {"usd": 1.0}}


def test_uncapped_by_default():
    assert llm._cost_cap({}) == 0
    _spend(prompt=100_000_000)
    llm.check_budget({}, "generate")            # must not raise


def test_under_the_cap_passes():
    _spend(prompt=1000, completion=1000)
    assert llm.spent_usd(CFG) < 1.0
    llm.check_budget(CFG, "generate")


def test_reaching_the_cap_stops_the_run():
    # $5/1M in on opus-5 → 1M prompt tokens is $5, comfortably over a $1 cap.
    _spend(prompt=1_000_000)
    with pytest.raises(CostCapExceeded) as e:
        llm.check_budget(CFG, "generate")
    assert "cap" in str(e.value)


def test_the_cap_is_enforced_before_the_call_not_after():
    """A cost cap that only notices after spending is a receipt, not a limit."""
    _spend(prompt=1_000_000)
    called = []
    with pytest.raises(CostCapExceeded):
        _with_retry(lambda: called.append(1), stage="generate_X", config=CFG)
    assert not called, "the provider was called after the budget was exhausted"


def test_env_overrides_config():
    import os
    _spend(prompt=1_000_000)                     # $5 spent
    os.environ["H2A_COST_CAP"] = "100"
    try:
        llm.check_budget(CFG, "generate")        # $5 < $100 — env wins over the $1 config
    finally:
        del os.environ["H2A_COST_CAP"]


def test_per_run_override_beats_env(monkeypatch):
    """Concurrent runs belong to different tenants; one budget must not bind another."""
    from src import runctx
    monkeypatch.setenv("H2A_COST_CAP", "100")
    _spend(prompt=1_000_000)                     # $5 spent

    def run():
        runctx.set_overrides(cost_cap=1.0)
        with pytest.raises(CostCapExceeded):
            llm.check_budget(CFG, "generate")

    import contextvars
    contextvars.copy_context().run(run)
    llm.check_budget(CFG, "generate")            # outside that run, the env cap still applies


def test_cap_latches_so_siblings_stop_immediately():
    """Every parallel worker must stop, not just the one that noticed."""
    _spend(prompt=1_000_000)
    with pytest.raises(CostCapExceeded):
        llm.check_budget(CFG, "generate_A")
    reached = []
    with pytest.raises(CostCapExceeded):
        _with_retry(lambda: reached.append(1), stage="generate_B", config={})
    assert not reached


def test_spend_is_a_floor_when_a_model_has_no_published_rate():
    """Unpriced usage contributes nothing, so the cap fires late rather than early —
    the safe direction, and the reason this is documented as a floor."""
    _spend(model="some-unlisted-model", prompt=1_000_000)
    assert llm.spent_usd(CFG) == 0.0
    llm.check_budget(CFG, "generate")


def test_reset_clears_spend_between_runs():
    _spend(prompt=1_000_000)
    reset_accounting()
    reset_call_log()
    llm.check_budget(CFG, "generate")


# ── the Discovery gate should say so before the money is spent ────────────────

def _classes(n=20, size=3000):
    return [{"class_name": f"C{i}", "layer": "Service", "source": "x" * size}
            for i in range(n)]


def _cfg(cap):
    return {"model": "claude-opus-5", "concurrency": 8, "cost_cap": {"usd": cap},
            "max_tokens": {"comprehend": 800, "generate": 8000},
            "agentic": {"critic": True}}


def test_forecast_warns_when_the_run_cannot_finish_inside_the_cap():
    from src.forecast import forecast, headline
    f = forecast(_classes(), targets=12, config=_cfg(0.01), provider="anthropic")
    assert f["budget"]["will_exceed"] is True
    assert "will be stopped" in headline(f)


def test_forecast_is_quiet_when_the_cap_is_comfortable():
    from src.forecast import forecast, headline
    f = forecast(_classes(), targets=12, config=_cfg(10_000), provider="anthropic")
    assert f["budget"]["will_exceed"] is False
    assert "cap" not in headline(f)


def test_forecast_flags_the_range_that_straddles_the_cap():
    """The honest case: the low bound fits and the high bound does not."""
    from src.forecast import forecast
    f = forecast(_classes(), targets=12, config=_cfg(10_000), provider="anthropic")
    mid = (f["cost"]["low"] + f["cost"]["high"]) / 2
    f2 = forecast(_classes(), targets=12, config=_cfg(mid), provider="anthropic")
    assert f2["budget"]["may_exceed"] is True
    assert f2["budget"]["will_exceed"] is True


def test_mock_runs_have_no_budget_warning():
    from src.forecast import forecast
    assert forecast(_classes(), targets=12, config=_cfg(0.01), provider="mock")["budget"] is None
