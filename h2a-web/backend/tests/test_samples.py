"""Both migrations are offerable as a one-click dry run. [1.48]

A demo that can only show one of the two pipelines misrepresents the product, and asking
someone to go and find a Magento module before they can see anything is a poor first five
minutes. The samples are bundled; this is what makes them discoverable.

The labels are *derived* by the same detector a real run uses rather than written down
here, so a sample that drifts out of alignment with its pipeline surfaces as a wrong
label rather than as a run that fails after someone clicks it.

    cd h2a-web/backend && PYTHONPATH=.:../../h2a-mvp pytest tests -q
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
for p in (str(BACKEND), str(REPO / "h2a-mvp")):
    if p not in sys.path:
        sys.path.insert(0, p)

import app as backend                                          # noqa: E402


@pytest.fixture(scope="module")
def samples():
    r = TestClient(backend.app).get("/api/samples")
    assert r.status_code == 200
    return r.json()


def test_every_migration_this_build_runs_has_a_sample():
    """The point of the endpoint. If a pipeline ships without a corpus behind it, nobody
    can try it without supplying their own project first."""
    from src import pipeline

    pipeline.ensure_registered()
    runnable = {p.id for p in pipeline.available() if p.implemented}
    offered = {s["pipeline"] for s in
               TestClient(backend.app).get("/api/samples").json()["samples"]}
    assert runnable <= offered, f"no sample for: {runnable - offered}"


def test_both_pipelines_are_present(samples):
    got = {s["pipeline"] for s in samples["samples"]}
    assert "hybris->salesforce" in got and "adobe->hybris" in got


def test_a_sample_path_is_one_a_hosted_run_will_accept(samples):
    """`_resolve_input_path` refuses anything outside the repo on a public deploy. A
    sample the UI offers and the API then rejects is worse than no sample."""
    backend.HOSTED = True
    try:
        for s in samples["samples"]:
            backend._resolve_input_path(s["path"])      # raises HTTPException if refused
    finally:
        backend.HOSTED = False


def test_the_shipped_migration_is_listed_first(samples):
    """It is the one with a golden baseline and an org to deploy into. Ordering by that
    rather than alphabetically means the default choice is the defensible one."""
    assert samples["samples"][0]["shipped"] is True


def test_the_unshipped_migration_says_so(samples):
    """Adobe→Hybris has no oracle and no deploy verification. A demo presenting the two
    as equals is exactly the overclaim this product exists to prevent."""
    adobe = [s for s in samples["samples"] if s["pipeline"] == "adobe->hybris"]
    assert adobe and all(s["shipped"] is False for s in adobe)


def test_each_sample_carries_enough_to_choose_between_them(samples):
    for s in samples["samples"]:
        assert s["label"] and s["summary"]
        assert s["size"], f"{s['path']} reports no size at all"


def test_whether_a_real_model_is_reachable_is_stated(samples):
    """So the UI can say "this will run on the mock" up front, instead of letting someone
    start a dry run and read stub output as a result."""
    assert set(samples["providers"]) >= {"anthropic", "openrouter"}
    assert all(isinstance(v, bool) for v in samples["providers"].values())


def test_no_credential_is_ever_returned(samples):
    """`server_fallbacks` reports a boolean by design. A regression to returning the key
    would leak it to every unauthenticated caller of this endpoint."""
    body = str(samples)
    assert "sk-" not in body
