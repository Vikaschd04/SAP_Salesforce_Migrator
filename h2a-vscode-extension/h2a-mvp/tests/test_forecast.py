"""Cost and duration forecast: a number before anything is charged."""

from src.forecast import forecast, headline, write_forecast_md

CFG = {"model": "claude-opus-4-8", "concurrency": 8,
       "max_tokens": {"comprehend": 800, "generate": 8000},
       "agentic": {"critic": True, "routing": {"enabled": True,
                   "models": {"cheap": "claude-haiku-4-5", "frontier": "claude-opus-4-8"}}}}


def classes(n, layer="Service", size=1800):
    return [{"class_name": f"C{i}", "layer": layer, "source": "x" * size} for i in range(n)]


def test_it_reports_a_range_not_a_point():
    """A single figure implies a precision that does not exist."""
    c = forecast(classes(20), 12, CFG, provider="anthropic")["cost"]
    assert c["high"] > c["low"] > 0


def test_mock_is_free_and_says_so():
    f = forecast(classes(20), 12, CFG, provider="mock")
    assert f["free"] and f["cost"]["low"] == 0 and f["cost"]["high"] == 0
    assert "free" in headline(f)
    assert any("nothing is charged" in a for a in f["assumptions"])


def test_cost_scales_with_the_estate():
    small = forecast(classes(10), 6, CFG, provider="anthropic")["cost"]["high"]
    big = forecast(classes(200), 120, CFG, provider="anthropic")["cost"]["high"]
    assert big > small * 5


def test_routing_puts_the_cheap_tier_on_comprehension():
    stages = {s["stage"]: s for s in forecast(classes(20), 12, CFG, provider="anthropic")["stages"]}
    assert stages["comprehend"]["model"] == "claude-haiku-4-5"
    assert stages["generate"]["model"] == "claude-opus-4-8"


def test_routing_off_puts_everything_on_one_model():
    cfg = {**CFG, "agentic": {"critic": True, "routing": {"enabled": False}}}
    models = {s["model"] for s in forecast(classes(20), 12, cfg, provider="anthropic")["stages"]}
    assert models == {"claude-opus-4-8"}


def test_reused_classes_are_not_billed_again():
    full = forecast(classes(100), 60, CFG, provider="anthropic")
    partial = forecast(classes(100), 60, CFG, provider="anthropic", already_done=90)
    assert partial["cost"]["high"] < full["cost"]["high"] / 3
    assert any("reused" in a for a in partial["assumptions"])


def test_review_effort_scales_with_what_is_actually_regenerated():
    """A re-run of a tenth of the estate does not need the whole estate reviewed again —
    reporting otherwise would hide the main reason to re-run at all."""
    full = forecast(classes(100), 60, CFG, provider="anthropic")["review_hours"]
    partial = forecast(classes(100), 60, CFG, provider="anthropic", already_done=90)["review_hours"]
    assert partial["high"] < full["high"] / 3


def test_mechanical_layers_need_less_review_than_business_logic():
    dao = forecast(classes(50, layer="DAO"), 30, CFG, provider="anthropic")["review_hours"]["high"]
    svc = forecast(classes(50, layer="Service"), 30, CFG, provider="anthropic")["review_hours"]["high"]
    assert svc > dao


def test_concurrency_compresses_time_but_not_spend():
    slow = forecast(classes(60), 40, {**CFG, "concurrency": 1}, provider="anthropic")
    fast = forecast(classes(60), 40, {**CFG, "concurrency": 8}, provider="anthropic")
    assert fast["minutes"]["high"] < slow["minutes"]["high"]
    assert fast["cost"]["high"] == slow["cost"]["high"]
    assert any("compresses wall-clock, not spend" in a for a in fast["assumptions"])


def test_disabling_the_critic_removes_its_calls_and_cost():
    cfg = {**CFG, "agentic": {"critic": False, "routing": CFG["agentic"]["routing"]}}
    off = forecast(classes(20), 12, cfg, provider="anthropic")
    assert "critic" not in {s["stage"] for s in off["stages"]}
    assert off["cost"]["high"] < forecast(classes(20), 12, CFG, provider="anthropic")["cost"]["high"]


def test_an_unpriced_model_is_reported_rather_than_guessed():
    cfg = {**CFG, "model": "some-unreleased-model",
           "agentic": {"critic": True, "routing": {"enabled": False}}}
    f = forecast(classes(10), 6, cfg, provider="anthropic")
    assert "some-unreleased-model" in f["cost"]["unpriced"]


def test_an_empty_codebase_forecasts_nothing():
    f = forecast([], 0, CFG, provider="anthropic")
    assert f["calls"] == 0 and f["cost"]["high"] == 0


def test_the_report_states_why_it_is_a_range(tmp_path):
    f = forecast(classes(20), 12, CFG, provider="anthropic")
    text = open(write_forecast_md(str(tmp_path), f), encoding="utf-8").read()
    assert "range, deliberately" in text
    assert "No spend was incurred producing this" in text or "no model call" in text
    assert "## Assumptions" in text
