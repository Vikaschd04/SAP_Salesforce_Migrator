"""An audit says which migration it was. [4.2]

A contract that certifies facts about a migration and does not say *which* migration is a
contract about nothing in particular. That mattered less with one pipeline, because there
was only one answer — which is exactly why it was never recorded.

The checkpoint half matters more than it looks. A checkpoint is resumed into a live run,
and resuming an Adobe→Hybris one into a Hybris→Salesforce run would reuse comprehensions
of PHP as though they described Java. The state loads, the run continues, and every
artifact after that point is built on an understanding of a different language.
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


def _bb(tmp_path=None):
    bb = Blackboard(str(tmp_path or "in"), "out")
    bb.approvals = []
    return bb


# ── the contract ──────────────────────────────────────────────────────────────

def test_the_contract_records_which_migration_ran():
    from src.signoff import build_signoff

    p = build_signoff(_bb())["pipeline"]
    assert p == {"id": "hybris->salesforce", "source": "hybris", "target": "salesforce"}


def test_it_records_the_other_pipeline_when_that_one_runs(as_adobe):
    from src.signoff import build_signoff

    p = build_signoff(_bb())["pipeline"]
    assert p["id"] == "adobe->hybris" and p["target"] == "hybris"


def test_the_engine_version_is_deliberately_not_recorded():
    """v1 and v2 are asserted byte-identical on every commit. Recording which one ran
    states a difference that does not exist — and it broke that very test, because the
    two runs then differed by this field."""
    from src.signoff import build_signoff

    assert "engine" not in build_signoff(_bb())["pipeline"]


def test_which_migration_it_was_is_a_certified_fact_not_metadata():
    """Two runs certifying the same facts about *different* pipelines must not share an
    id. Leaving it out of the hash would make the contract id claim more than it knows."""
    from src.signoff import build_signoff

    a = build_signoff(_bb())["contract_id"]
    token = runctx._pipeline_id.set("adobe->hybris")
    try:
        b = build_signoff(_bb())["contract_id"]
    finally:
        runctx._pipeline_id.reset(token)
    assert a != b


def test_the_document_shows_it(tmp_path):
    from src.signoff import build_signoff, write_signoff_md

    write_signoff_md(str(tmp_path), build_signoff(_bb()))
    text = (tmp_path / "SIGN_OFF.md").read_text()
    assert "| **Migration** | `hybris` → `salesforce` |" in text


# ── checkpoints ───────────────────────────────────────────────────────────────

def test_a_checkpoint_records_its_pipeline(tmp_path):
    from src import checkpoint

    checkpoint.save(_bb(tmp_path), "after-plan", root=str(tmp_path))
    saved = checkpoint.list_all(str(tmp_path))
    assert saved and saved[0]["pipeline"]["id"] == "hybris->salesforce"


def test_resuming_across_pipelines_warns_loudly(tmp_path):
    """It loads. That is the problem: the comprehensions describe a different language and
    nothing downstream would say so."""
    from src import checkpoint

    checkpoint.save(_bb(tmp_path), "after-plan", root=str(tmp_path))
    cid = checkpoint.list_all(str(tmp_path))[0]["id"]

    token = runctx._pipeline_id.set("adobe->hybris")
    try:
        _, warnings = checkpoint.load(str(tmp_path), cid)
    finally:
        runctx._pipeline_id.reset(token)

    joined = " ".join(warnings)
    assert "hybris->salesforce" in joined and "adobe->hybris" in joined
    assert "nothing below this point is trustworthy" in joined


def test_resuming_into_the_same_pipeline_is_silent_about_it(tmp_path):
    from src import checkpoint

    checkpoint.save(_bb(tmp_path), "after-plan", root=str(tmp_path))
    cid = checkpoint.list_all(str(tmp_path))[0]["id"]
    _, warnings = checkpoint.load(str(tmp_path), cid)
    assert not any("resumed into" in w for w in warnings)
