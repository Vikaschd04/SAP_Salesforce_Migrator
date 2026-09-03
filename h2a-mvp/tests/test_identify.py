"""What this codebase is, and which migrations are available for it. [4.1]

Every surface used to ask `preflight.inspect`, which answers *"is this Hybris?"*. So a
Magento project was rejected as "not a Hybris project" — by a tool holding an adapter that
recognised it at 100% confidence.

The three outcomes are genuinely different answers rather than degrees of one, and the
middle one is why this exists: "we know exactly what this is and cannot migrate it yet" is
useful; "unidentified" is not.
"""

from pathlib import Path

from src import pipeline

TESTING = Path(__file__).resolve().parents[2] / "Testing"


def test_a_hybris_project_is_runnable():
    r = pipeline.identify(str(TESTING / "acme-commerce-hybris"))
    assert r["status"] == "runnable"
    assert r["platform"] == "hybris"
    assert [p["id"] for p in r["pipelines"]] == ["hybris->salesforce"]


def test_a_magento_project_is_recognised_but_not_runnable():
    """The distinction this item exists for."""
    r = pipeline.identify(str(TESTING / "acme-commerce-magento"))
    assert r["status"] == "recognised"
    assert r["platform"] == "adobe-commerce"
    assert [p["id"] for p in r["pipelines"]] == ["adobe->hybris"]
    assert r["pipelines"][0]["implemented"] is False


def test_the_magento_summary_says_what_it_is_not_that_it_is_unknown():
    r = pipeline.identify(str(TESTING / "acme-commerce-magento"))
    assert "Adobe Commerce" in r["summary"]
    assert "not identified" not in r["summary"].lower()


def test_an_empty_directory_is_unrecognised(tmp_path):
    r = pipeline.identify(str(tmp_path))
    assert r["status"] == "unrecognised"
    assert r["pipelines"] == []


def test_a_refusal_is_not_a_default(tmp_path):
    """Guessing a platform starts a migration that was never going to work."""
    assert pipeline.identify(str(tmp_path))["platform"] == ""


def test_each_option_carries_what_a_run_could_claim():
    """`has_oracle` belongs beside the choice rather than in the report afterwards: it is
    the difference between "proven to compile" and "statically checked"."""
    opt = pipeline.identify(str(TESTING / "acme-commerce-hybris"))["pipelines"][0]
    assert opt["has_oracle"] is True and opt["shipped"] is True

    other = pipeline.identify(str(TESTING / "acme-commerce-magento"))["pipelines"][0]
    assert other["has_oracle"] is False


def test_identify_registers_the_pipelines_itself():
    """A surface calls this before anything else in the process has touched the registry.
    Without it every codebase came back unrecognised, including the shipped one."""
    pipeline._REGISTRY.clear()
    assert pipeline.identify(str(TESTING / "acme-commerce-hybris"))["status"] == "runnable"


def test_only_pipelines_from_the_detected_source_are_offered():
    """A dropdown pairing every source with every target is mostly invalid combinations."""
    r = pipeline.identify(str(TESTING / "acme-commerce-magento"))
    assert all(p["source"] == "adobe-commerce" for p in r["pipelines"])


def test_an_unrecognised_upload_gets_the_most_specific_refusal(tmp_path):
    """"Nothing to migrate" tells someone who uploaded the wrong folder what to do.
    "No registered source adapter recognised this codebase" tells them about our
    architecture, which is not their problem."""
    junk = tmp_path / "holiday"
    junk.mkdir()
    (junk / "photo.txt").write_text("not code", encoding="utf-8")

    r = pipeline.identify(str(junk))
    assert r["status"] == "unrecognised"
    assert "nothing to migrate" in r["summary"]


def test_an_empty_upload_says_it_is_empty(tmp_path):
    assert "empty" in pipeline.identify(str(tmp_path))["summary"].lower()
