"""Recognising an Adobe Commerce codebase, and being honest about it. [2.1, 2.2]

Detection and capability are two different questions, and conflating them produces the
worst possible answer. Before this, a Magento project came back as "not identified as any
supported source" — which reads as *we do not know what this is*, when in fact the tool
knew exactly what it was and simply could not migrate it yet.

So `detect()` identifies the project and the verdict says `not_yet_supported`. The run
still refuses to start, via `require_runnable()`; what changes is that the customer is told
the truth about why.
"""

import json

import pytest

from src import pipeline
from src.adapters.adobe_source import ADAPTER

from pathlib import Path

TESTING = Path(__file__).resolve().parents[2] / "Testing"
MAGENTO = TESTING / "acme-commerce-magento"
HYBRIS = TESTING / "acme-commerce-hybris"


# ── the fixture itself [2.1] ──────────────────────────────────────────────────

def test_the_reference_project_carries_the_constructs_phase_2_must_read():
    """Each of these is a register row. A fixture without them proves nothing."""
    mod = MAGENTO / "app/code/Acme/Loyalty"
    for rel, why in [
        ("etc/di.xml", "G5 preferences and plugin wiring"),
        ("etc/events.xml", "G3 observers"),
        ("etc/crontab.xml", "G9 cron"),
        ("etc/db_schema.xml", "declared tables"),
        ("Setup/Patch/Data/AddLoyaltyAttributes.php", "G1 EAV attributes"),
        ("Plugin/OrderTotalPlugin.php", "G2 around plugin"),
        ("view/frontend/layout/checkout_index_index.xml", "G6 layout XML"),
        ("etc/adminhtml/system.xml", "G7 store-view scoping"),
        ("Test/Unit/Model/PricingServiceTest.php", "2.9 PHPUnit mining"),
    ]:
        assert (mod / rel).exists(), f"missing {rel} — needed for {why}"


def test_the_around_plugin_actually_skips_proceed():
    """G2's whole point. A fixture where `$proceed` is always called tests nothing."""
    src = (MAGENTO / "app/code/Acme/Loyalty/Plugin/OrderTotalPlugin.php").read_text()
    assert "aroundGetGrandTotal" in src
    body = src.split("aroundGetGrandTotal", 1)[1].split("public function", 1)[0]
    assert "return 0.0;" in body and "$proceed()" in body, \
        "the around plugin must have a path that returns without calling $proceed"


def test_the_observer_mutates_the_event_payload():
    """G3: Magento observers are synchronous and can write back into the event."""
    src = (MAGENTO / "app/code/Acme/Loyalty/Observer/AwardPointsObserver.php").read_text()
    assert "$order->setData(" in src


def test_the_business_rules_match_the_hybris_corpus():
    """Same domain on both platforms, so the two pipelines are comparable end to end."""
    php = (MAGENTO / "app/code/Acme/Loyalty/Model/PricingService.php").read_text()
    for rule in ("GOLD_RATE = 0.12", "SILVER_RATE = 0.06", "discountThreshold"):
        assert rule in php


def test_the_module_is_a_valid_composer_package():
    data = json.loads((MAGENTO / "composer.json").read_text())
    assert data["type"] == "magento2-module"


# ── detection [2.2] ───────────────────────────────────────────────────────────

def test_a_magento_project_is_recognised():
    r = ADAPTER.detect(str(MAGENTO))
    assert r["confidence"] == 100
    assert r["is_magento"] is True
    assert r["project"]["modules"] == ["Acme_Loyalty"]


def test_recognised_is_not_the_same_as_supported():
    """The distinction this item exists to make."""
    r = ADAPTER.detect(str(MAGENTO))
    assert r["verdict"] == "not_yet_supported"
    assert r["implemented"] is False
    assert any("not implemented yet" in b for b in r["blockers"])


def test_a_hybris_project_is_not_mistaken_for_magento():
    r = ADAPTER.detect(str(HYBRIS))
    assert r["verdict"] == "reject" and r["confidence"] == 0


def test_an_empty_directory_is_rejected(tmp_path):
    assert ADAPTER.detect(str(tmp_path))["verdict"] == "reject"


def test_detection_never_raises_on_a_hostile_tree(tmp_path):
    """Detection runs across every adapter; one that throws breaks the others."""
    (tmp_path / "composer.json").write_text("{ not json", encoding="utf-8")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "module.xml").write_bytes(b"\xff\xfe\x00binary")
    assert ADAPTER.detect(str(tmp_path))["verdict"] in ("reject", "not_yet_supported")


def test_env_php_credentials_are_reported_before_anything_is_uploaded(tmp_path):
    (tmp_path / "composer.json").write_text('{"type": "magento2-project"}', encoding="utf-8")
    (tmp_path / "app" / "etc").mkdir(parents=True)
    (tmp_path / "app" / "etc" / "env.php").write_text("<?php return [];", encoding="utf-8")
    (tmp_path / "registration.php").write_text("<?php", encoding="utf-8")
    r = ADAPTER.detect(str(tmp_path))
    assert any("env.php" in s["file"] for s in r["secrets"])
    assert any("crypt key" in s["detail"] for s in r["secrets"])


def test_vendor_is_not_scanned(tmp_path):
    """A real project has tens of thousands of PHP files under vendor/."""
    (tmp_path / "vendor" / "magento" / "x").mkdir(parents=True)
    (tmp_path / "vendor" / "magento" / "x" / "registration.php").write_text("<?php", encoding="utf-8")
    assert ADAPTER.detect(str(tmp_path))["verdict"] == "reject"


# ── resolution, and the refusal that follows ──────────────────────────────────

def test_the_magento_project_resolves_to_the_adobe_pipeline():
    pipeline.ensure_registered()
    platform, report = pipeline.detect(str(MAGENTO))
    assert platform == "adobe-commerce"
    assert report["verdict"] == "not_yet_supported"


def test_the_hybris_corpus_still_resolves_to_hybris():
    """The regression that matters: a second detector must not shadow the shipped one."""
    pipeline.ensure_registered()
    platform, report = pipeline.detect(str(HYBRIS))
    assert platform == "hybris"
    assert report["verdict"] == "ok"


def test_a_recognised_but_unimplemented_pipeline_still_refuses_to_run():
    pipeline.ensure_registered()
    p = pipeline.resolve(str(MAGENTO))
    assert not p.implemented
    with pytest.raises(Exception):
        pipeline.require_runnable(p)
