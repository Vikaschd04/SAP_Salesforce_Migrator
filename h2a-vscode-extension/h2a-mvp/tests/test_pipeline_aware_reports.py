"""Reports name the pipeline that ran, not the one that shipped first. [4.4]

Every assurance report said "Apex" and "Java" unconditionally. On the shipped pipeline
that is correct and invisible; on an Adobe Commerce → SAP Hybris run it would have told
the reader about "Java method(s) with no Apex counterpart" while emitting Java from PHP.

That is not a cosmetic problem. A report naming the wrong platform is the clearest signal
a reader has about whether the tool understood what it just did — and the reader is
someone deciding whether to trust a migration.
"""

import pytest

from src import runctx
from src.agentic.blackboard import Blackboard


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


def _bb():
    bb = Blackboard("in", "out")
    bb.approvals = []
    return bb


PROV = {"methods": 10, "linked": 4, "coverage": 40,
        "source_without_target": 6, "target_without_origin": 2}


# ── the languages come from the adapters ──────────────────────────────────────

def test_each_pipeline_reports_its_own_languages(as_adobe):
    from src.provenance import _languages

    assert _languages() == ("PHP", "Java")


def test_the_shipped_pipeline_is_unchanged(as_salesforce):
    from src.provenance import _languages

    assert _languages() == ("Java", "Apex")


def test_both_halves_of_the_pair_declare_a_language():
    """A missing one degrades to "source"/"target", which reads as a bug rather than a
    platform name — so every registered adapter has to carry one."""
    from src import pipeline

    pipeline.ensure_registered()
    for p in pipeline.available():
        assert getattr(p.source, "code_language", "")
        assert getattr(p.target, "code_language", "")


# ── provenance ────────────────────────────────────────────────────────────────

def test_provenance_headline_names_the_running_pair(as_adobe):
    from src.provenance import headline

    text = headline(PROV)
    assert "PHP method(s) with no Java counterpart" in text
    assert "Apex" not in text


def test_provenance_report_names_the_running_pair(as_adobe, tmp_path):
    from src.provenance import write_provenance_md

    write_provenance_md(str(tmp_path), {"summary": PROV, "artifacts": []})
    text = (tmp_path / "PROVENANCE.md").read_text()
    assert "PHP method(s) have no Java counterpart" in text
    assert "Apex" not in text


# ── sign-off ──────────────────────────────────────────────────────────────────

def test_signoff_caveats_name_the_running_pair(as_adobe, monkeypatch):
    from src import provenance, signoff

    monkeypatch.setattr(provenance, "build_provenance", lambda bb: {"summary": PROV})
    c = signoff.build_signoff(_bb())
    joined = " ".join(c["caveats"])
    assert "PHP method(s) have no traceable Java" in joined
    assert "Apex" not in joined


def test_the_shipped_pipeline_still_says_java_and_apex(as_salesforce, monkeypatch):
    from src import provenance, signoff

    monkeypatch.setattr(provenance, "build_provenance", lambda bb: {"summary": PROV})
    c = signoff.build_signoff(_bb())
    joined = " ".join(c["caveats"])
    assert "Java method(s) have no traceable Apex" in joined


# ── alignment ─────────────────────────────────────────────────────────────────

def test_alignment_report_names_the_running_pair(as_adobe, tmp_path):
    from src.alignment import write_alignment_md

    write_alignment_md(str(tmp_path), {"rows": [], "summary": {
        "rules": 0, "aligned": 0, "proven": 0, "replayed": 0, "broken": 0}})
    text = (tmp_path / "ALIGNMENT.md").read_text()
    assert "Java method → PHP method is provenance" in text
    assert "Apex" not in text


# ── the ratchet ───────────────────────────────────────────────────────────────

def test_no_assurance_module_carries_platform_vocabulary_any_more():
    """The ratchet is empty. 1.13 cleared characterize, 3.9 took `salesforce` out of
    signoff, 4.4 took the last of the prose — and a module absent from the debt map must
    carry none at all, so adding one back fails CI."""
    from tests.test_assurance_purity import KNOWN_DEBT

    assert KNOWN_DEBT == {}
