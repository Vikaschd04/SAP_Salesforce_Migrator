"""A forecast says which platform pair its numbers came from. [4.3]

Every constant in `forecast.py` was measured on **one** pair. Quoting a PHP→Java migration
from Java→Apex measurements produces a figure carrying a confidence nothing supports — and
the forecast is what a cost cap gets set against, so an over-confident one is not a
presentation problem.

The sharpest finding here is not about cost at all. `Model` means opposite things on the
two platforms: a Hybris `Model` is a class the platform *generated* from items.xml, and a
Magento `Model` holds business logic. Sharing one "mechanical layers" set called every
business class in a Magento estate a glance to review.
"""

import pytest

from src import runctx
from src.forecast import PROFILES, forecast, profile_for


@pytest.fixture
def as_adobe():
    token = runctx._pipeline_id.set("adobe->hybris")
    try:
        yield
    finally:
        runctx._pipeline_id.reset(token)


@pytest.fixture
def as_salesforce():
    token = runctx._pipeline_id.set("hybris->salesforce")
    try:
        yield
    finally:
        runctx._pipeline_id.reset(token)


def _classes(n, layer="Model"):
    return [{"class_name": f"C{i}", "layer": layer, "source": "x" * 3000}
            for i in range(n)]


CONFIG = {"model": "claude-opus-4-8"}


# ── the profiles ──────────────────────────────────────────────────────────────

def test_every_registered_pipeline_has_a_profile():
    from src import pipeline

    pipeline.ensure_registered()
    for p in pipeline.available():
        assert p.id in PROFILES, p.id


def test_the_shipped_pair_is_measured_and_the_new_one_is_not():
    assert PROFILES["hybris->salesforce"].measured is True
    assert PROFILES["adobe->hybris"].measured is False


def test_an_unknown_pipeline_falls_back_to_the_shipped_profile():
    assert profile_for("no-such-pipeline") is PROFILES["hybris->salesforce"]


# ── the semantic collision ────────────────────────────────────────────────────

def test_model_means_opposite_things_on_the_two_platforms():
    """A Hybris Model is generated from items.xml; a Magento Model holds business logic.
    `hybris_plan.py` says so in as many words when it routes one to a Service."""
    assert "Model" in PROFILES["hybris->salesforce"].mechanical_layers
    assert "Model" not in PROFILES["adobe->hybris"].mechanical_layers


def test_that_collision_would_have_understated_review_by_an_order_of_magnitude(
        as_salesforce):
    """Review hours are what a customer plans staffing around."""
    sf = forecast(_classes(20), 20, CONFIG)["review_hours"]
    token = runctx._pipeline_id.set("adobe->hybris")
    try:
        adobe = forecast(_classes(20), 20, CONFIG)["review_hours"]
    finally:
        runctx._pipeline_id.reset(token)

    assert sf["high"] <= 1.0
    assert adobe["high"] >= 6.0
    assert adobe["high"] / sf["high"] > 5


def test_a_genuinely_mechanical_magento_layer_is_still_routine(as_adobe):
    """The fix must be specific. Calling *everything* involved is as wrong as the
    opposite, just in the direction that flatters the estimate."""
    hours = forecast(_classes(20, layer="DAO"), 20, CONFIG)["review_hours"]
    assert hours["high"] <= 1.0


# ── the honesty ───────────────────────────────────────────────────────────────

def test_an_unmeasured_forecast_says_so_first(as_adobe):
    """A caveat that arrives after the number has been read is a caveat nobody read."""
    first = forecast(_classes(5), 5, CONFIG)["assumptions"][0]
    assert "not been measured for this platform pair" in first
    assert "order of magnitude rather than a quote" in first


def test_a_measured_forecast_does_not_carry_the_caveat(as_salesforce):
    joined = " ".join(forecast(_classes(5), 5, CONFIG)["assumptions"])
    assert "not been measured" not in joined


def test_the_basis_travels_with_the_forecast(as_adobe):
    basis = forecast(_classes(5), 5, CONFIG)["basis"]
    assert basis["measured"] is False
    assert "NOT measured on PHP→Java" in basis["detail"]


def test_the_report_warns_above_the_number_not_below_it(as_adobe, tmp_path):
    from src.forecast import write_forecast_md

    f = forecast(_classes(5), 5, CONFIG)
    write_forecast_md(str(tmp_path), f)
    text = (tmp_path / "FORECAST.md").read_text()
    assert "Not measured for this platform pair" in text
    assert text.index("Not measured") < text.index("## Assumptions")


def test_php_is_denser_per_token_than_java():
    """Sigils, `->`, and no type declarations to pad the text. The number is itself an
    estimate; reusing Java's silently would not have been."""
    assert (PROFILES["adobe->hybris"].chars_per_token
            < PROFILES["hybris->salesforce"].chars_per_token)
