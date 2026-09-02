"""The v2 seam: the IR contract and the pipeline registry.

The golden harness proves the seam preserves behaviour end to end. These prove the pieces
behave individually — most importantly that the IR does not quietly lose anything, which
is the failure mode that would make v2 subtly wrong rather than obviously broken.
"""
import os

import pytest

from src import ir, pipeline


# ── the version switch ────────────────────────────────────────────────────────

def test_v1_is_the_default(monkeypatch):
    """An existing user who upgrades must get the pipeline they had."""
    monkeypatch.delenv("H2A_ENGINE_VERSION", raising=False)
    assert pipeline.engine_version({}) == pipeline.V1
    assert pipeline.v2_enabled({}) is False


def test_env_selects_v2(monkeypatch):
    monkeypatch.setenv("H2A_ENGINE_VERSION", "v2")
    assert pipeline.v2_enabled({}) is True


def test_config_can_select_v2_and_env_wins(monkeypatch):
    monkeypatch.delenv("H2A_ENGINE_VERSION", raising=False)
    assert pipeline.engine_version({"engine_version": "v2"}) == pipeline.V2
    monkeypatch.setenv("H2A_ENGINE_VERSION", "v1")
    assert pipeline.engine_version({"engine_version": "v2"}) == pipeline.V1


def test_a_nonsense_version_falls_back_to_v1(monkeypatch):
    """Never fail open into an unproven engine because of a typo."""
    monkeypatch.setenv("H2A_ENGINE_VERSION", "v3")
    assert pipeline.engine_version({}) == pipeline.V1


# ── the registry ──────────────────────────────────────────────────────────────

def test_the_shipped_pipeline_is_registered_and_is_the_default():
    pipeline.ensure_registered()
    p = pipeline.default_pipeline()
    assert p.id == "hybris->salesforce"
    assert p.shipped is True
    assert (p.source_platform, p.target_platform) == ("hybris", "salesforce")


def test_salesforce_target_declares_an_oracle():
    """`verifiable` is what lets a run claim 'proven to run'. It is per-target, and the
    Hybris target will say False until a licensed platform is available."""
    pipeline.ensure_registered()
    assert pipeline.get("hybris->salesforce").verifiable is True


def test_unknown_pipeline_lists_what_is_available():
    pipeline.ensure_registered()
    with pytest.raises(KeyError, match="hybris->salesforce"):
        pipeline.get("magento->sap")


def test_detection_refuses_rather_than_guessing(tmp_path):
    """A folder that is not a supported source must not resolve to a platform."""
    (tmp_path / "notes.txt").write_text("holiday photos")
    platform, report = pipeline.detect(str(tmp_path))
    assert platform == ""
    assert report["verdict"] in ("reject", "warn")


def test_detection_recognises_the_reference_corpus():
    pipeline.ensure_registered()
    platform, report = pipeline.detect("../Testing/acme-commerce-hybris")
    assert platform == "hybris"
    assert report.get("confidence", 0) > 0


# ── the IR contract ───────────────────────────────────────────────────────────

def test_ingest_round_trip_is_lossless():
    """The precondition for v2 matching v1. If the IR drops a field here, generation
    silently changes downstream."""
    from src.ingest import ingest
    raw = ingest("../Testing/acme-commerce-hybris")
    back = ir.SourceModel.from_ingest(raw, platform="hybris").to_ingest()

    assert set(raw) <= set(back), f"top-level keys lost: {sorted(set(raw)-set(back))}"
    for a, b in zip(raw["classes"], back["classes"]):
        for k, v in a.items():
            assert k in b, f"{a.get('class_name')}: field {k!r} lost"
            assert b[k] == v, f"{a.get('class_name')}: field {k!r} changed"


def test_unmodelled_fields_survive_the_round_trip():
    """A frontend Component carries `selector`, `template`, `styles`… none of which mean
    anything to a Java class. Dropping them broke LWC generation, so they ride along."""
    u = ir.SourceUnit.from_dict({
        "class_name": "ProductListComponent", "layer": "Component",
        "selector": "acme-product-list", "template": "<div></div>", "styles": ".a{}",
        "inputs": ["productCode"], "outputs": ["added"],
    })
    assert u.name == "ProductListComponent"
    assert u.extra["selector"] == "acme-product-list"
    d = u.to_dict()
    assert d["template"] == "<div></div>" and d["inputs"] == ["productCode"]
    assert "extra" not in d, "the passthrough bag must not leak into the wire shape"


def test_class_name_is_emitted_for_existing_consumers():
    """Every current consumer reads `class_name`; dropping it would be a rewrite."""
    d = ir.SourceUnit.from_dict({"class_name": "OrderDao"}).to_dict()
    assert d["class_name"] == "OrderDao" and d["name"] == "OrderDao"


def test_validate_flags_duplicate_units():
    """Two units of the same name collide downstream — one silently wins the write."""
    m = ir.SourceModel(platform="hybris", units=[
        ir.SourceUnit(name="PricingService"), ir.SourceUnit(name="PricingService")])
    assert any("duplicate" in p for p in ir.validate(m))


def test_validate_flags_a_model_that_does_not_name_its_platform():
    assert any("platform" in p for p in ir.validate(ir.SourceModel()))


def test_validate_is_clean_on_the_reference_corpus():
    from src.ingest import ingest
    m = ir.SourceModel.from_ingest(ingest("../Testing/acme-commerce-hybris"),
                                   platform="hybris")
    assert ir.validate(m) == []


# ── the source adapter ────────────────────────────────────────────────────────

def test_hybris_source_adapter_reads_the_whole_model():
    from src.adapters import hybris_source
    m = hybris_source.ADAPTER.read("../Testing/acme-commerce-hybris")
    assert m.platform == "hybris"
    assert len(m.units) > 10
    assert m.tests, "JUnit tests must be held aside, not migrated"
    assert m.processes and m.processes[0].steps, "business processes must be read"
    assert m.hazards, "the radar must run through the adapter too"
    assert ir.validate(m) == []
