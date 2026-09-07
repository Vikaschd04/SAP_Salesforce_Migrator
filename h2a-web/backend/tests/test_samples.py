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
    assert set(samples["providers"]) >= {"anthropic", "unorouter"}
    assert all(isinstance(v, bool) for v in samples["providers"].values())


def test_no_credential_is_ever_returned(samples):
    """`server_fallbacks` reports a boolean by design. A regression to returning the key
    would leak it to every unauthenticated caller of this endpoint."""
    body = str(samples)
    assert "sk-" not in body


# ── readiness has to be true, not merely present [1.49] ──────────────────────

def test_readiness_is_asked_the_way_the_engine_answers_it(monkeypatch):
    """The engine falls back to `h2a-mvp/.env`; this checked only `os.environ`. A
    developer with a key in `.env` was told "no key configured" by a cockpit whose runs
    would then have worked. The 1.48 readiness indicator exists so nobody starts a run
    that silently produces stub output — one that is wrong is worse than none."""
    import keyvault

    monkeypatch.delenv("UNOROUTER_API_KEY", raising=False)
    monkeypatch.setattr("src.llm._get_api_key",
                        lambda var: "found-in-dotenv" if var == "UNOROUTER_API_KEY" else None)
    assert keyvault.server_fallbacks()["unorouter"] is True


def test_a_provider_with_no_key_anywhere_reports_false(monkeypatch):
    import keyvault

    monkeypatch.setattr("src.llm._get_api_key", lambda var: None)
    assert keyvault.server_fallbacks() == {"anthropic": False, "unorouter": False}


def test_the_answer_is_still_a_boolean_never_the_key(monkeypatch):
    """`server_fallbacks` is reachable unauthenticated through /api/samples."""
    import keyvault

    monkeypatch.setattr("src.llm._get_api_key", lambda var: "sk-super-secret-value")
    got = keyvault.server_fallbacks()
    assert all(v is True for v in got.values())
    assert "sk-" not in str(got)


# ── a migration's output is not a migration's input [1.60] ───────────────────

def test_generated_output_directories_are_not_offered(samples):
    """`Testing/out-appointment` is a *result* — and a valid Hybris codebase, so detection
    identified it and offered it as something to migrate. Offering someone yesterday's
    output as today's input is the kind of nonsense a client notices immediately."""
    for s in samples["samples"]:
        assert not s["path"].split("/")[-1].startswith(("out-", "out_")), s["path"]


def test_the_small_demo_slice_is_offered(samples):
    """A 20-target module is the wrong thing to run in front of an audience. The slice is
    real, unmodified third-party code and exercises every part of the pipeline once."""
    paths = {s["path"] for s in samples["samples"]}
    assert "Testing/appointment-demo" in paths
    assert "Testing/appointment-magento" in paths, "the full module stays, for coverage"


def test_whether_the_shared_key_may_be_spent_is_stated(samples):
    """"No key configured" means "add one" or "you cannot run this" depending on this,
    and the cockpit cannot tell the difference without being told."""
    assert isinstance(samples["server_allowed"], bool)
