"""Whose key paid for this run. [1.50]

Before this, a run whose user had stored no key quietly used the *server's*. Two things
were wrong with that, and only one of them is about money. The cockpit said "no key
configured" beside the provider and then started the run anyway, so the interface and the
system disagreed in front of the user — the same failure shape as an extension full of
`UnsupportedOperationException` reported as nine conversions.

Resolution is ordered by how deliberate the choice was: a key typed for this run beats one
saved on the account, which beats the deployment's shared key — and the shared one is only
reachable when an operator has explicitly turned it on.

    cd h2a-web/backend && PYTHONPATH=.:../../h2a-mvp pytest tests -q
"""

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
for p in (str(BACKEND), str(REPO / "h2a-mvp")):
    if p not in sys.path:
        sys.path.insert(0, p)

import app as backend                                          # noqa: E402
import keyvault                                                # noqa: E402


@pytest.fixture(autouse=True)
def _no_server_key(monkeypatch):
    """Default posture: the shared key is off and nothing is stored."""
    monkeypatch.delenv("H2A_ALLOW_SERVER_KEY", raising=False)
    monkeypatch.setattr(keyvault, "get_key", lambda uid, provider: None)
    monkeypatch.setattr(keyvault, "server_fallbacks", lambda: {"anthropic": True,
                                                               "unorouter": True})


# ── the keyless mode stays keyless ────────────────────────────────────────────

def test_mock_needs_no_credential():
    """Requiring a key for the offline dry run would make the safest mode the hardest to
    start, on exactly the locked-down laptop it exists for."""
    assert backend._credential_for("mock", "u1", "") == (None, "none")


# ── ordered by how deliberate the choice was ──────────────────────────────────

def test_a_key_typed_for_this_run_is_used():
    got, source = backend._credential_for("anthropic", "u1", "sk-ant-typed")
    assert got == "sk-ant-typed" and source == "this run only"


def test_a_saved_key_is_used_when_none_was_typed(monkeypatch):
    monkeypatch.setattr(keyvault, "get_key",
                        lambda uid, provider: "sk-ant-saved" if uid == "u1" else None)
    assert backend._credential_for("anthropic", "u1", "") == ("sk-ant-saved",
                                                              "your saved key")


def test_the_typed_key_wins_over_the_saved_one(monkeypatch):
    """Typing a key is a deliberate act for this run. Silently preferring the stored one
    would make the dialog a lie."""
    monkeypatch.setattr(keyvault, "get_key", lambda uid, provider: "sk-ant-saved")
    got, source = backend._credential_for("anthropic", "u1", "sk-ant-typed")
    assert got == "sk-ant-typed" and source == "this run only"


def test_whitespace_is_not_a_key():
    with pytest.raises(backend.NeedsKey):
        backend._credential_for("anthropic", "u1", "   ")


# ── the shared key is opt-in ──────────────────────────────────────────────────

def test_without_a_key_the_run_is_refused():
    with pytest.raises(backend.NeedsKey) as e:
        backend._credential_for("anthropic", "u1", "")
    assert e.value.status_code == 402
    assert e.value.detail["code"] == "needs_key"
    assert e.value.detail["provider"] == "anthropic"


def test_the_shared_key_is_used_only_when_an_operator_allows_it(monkeypatch):
    monkeypatch.setenv("H2A_ALLOW_SERVER_KEY", "1")
    got, source = backend._credential_for("anthropic", "u1", "")
    assert got is None, "None lets the engine read the deployment's own environment"
    assert source == "the server's shared key"


def test_allowing_a_shared_key_the_server_does_not_have_still_refuses(monkeypatch):
    """Permission is not possession. Starting here would fail deep inside the run with a
    provider error instead of at the door with a sentence a person can act on."""
    monkeypatch.setenv("H2A_ALLOW_SERVER_KEY", "1")
    monkeypatch.setattr(keyvault, "server_fallbacks", lambda: {"anthropic": False})
    with pytest.raises(backend.NeedsKey):
        backend._credential_for("anthropic", "u1", "")


# ── what the refusal says ─────────────────────────────────────────────────────

def test_a_signed_out_visitor_is_told_to_sign_in():
    with pytest.raises(backend.NeedsKey) as e:
        backend._credential_for("anthropic", None, "")
    assert "Sign in" in e.value.detail["message"]


def test_when_storage_is_off_the_message_says_so_and_offers_the_way_through(monkeypatch):
    """"Add a key to your account" is useless advice on a server that cannot store one."""
    monkeypatch.setattr(keyvault, "available", lambda: False)
    monkeypatch.setattr(keyvault, "why_unavailable", lambda: "H2A_SECRET_KEY is not set")
    with pytest.raises(backend.NeedsKey) as e:
        backend._credential_for("anthropic", "u1", "")
    msg = e.value.detail["message"]
    assert "H2A_SECRET_KEY" in msg and "this run only" in msg


def test_the_refusal_never_repeats_the_key_back():
    """It is a 402 body that reaches a browser and any proxy in between."""
    monkeypatch_free = backend._credential_for
    with pytest.raises(backend.NeedsKey) as e:
        monkeypatch_free("anthropic", "u1", "")
    assert "sk-" not in str(e.value.detail)


# ── the flow a browser actually walks ─────────────────────────────────────────

from fastapi.testclient import TestClient                      # noqa: E402

DEMO = str(REPO / "Testing" / "acme-commerce-magento")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("H2A_ALLOW_SERVER_KEY", raising=False)
    monkeypatch.setattr(keyvault, "get_key", lambda uid, provider: None)
    return TestClient(backend.app)


def _start(client, **extra):
    return client.post("/api/runs", data={"input_path": DEMO, "supervised": "false",
                                          **extra})


def test_a_mock_run_starts_with_no_key_at_all(client):
    r = _start(client, provider="mock")
    assert r.status_code == 200, r.text
    assert r.json()["credential"] == "none"


def test_a_real_provider_without_a_key_is_refused_before_any_work(client):
    """402 rather than 400: the request is fine, something is needed before it can run.
    The cockpit opens its key dialog on exactly this."""
    r = _start(client, provider="anthropic")
    assert r.status_code == 402, r.text
    d = r.json()["detail"]
    assert d["code"] == "needs_key" and d["provider"] == "anthropic"


def test_no_run_is_created_by_a_refusal(client):
    """A refused start must leave nothing behind — a run row in `queued` that never moves
    is indistinguishable from one that is stuck."""
    before = len(client.get("/api/runs").json()["runs"])
    _start(client, provider="anthropic")
    assert len(client.get("/api/runs").json()["runs"]) == before


def test_a_key_supplied_for_the_run_starts_it(client):
    r = _start(client, provider="anthropic", api_key="sk-ant-" + "x" * 30)
    assert r.status_code == 200, r.text
    assert r.json()["credential"] == "this run only"


def test_the_run_record_never_carries_the_key(client):
    """It rides one request and lives as a closure variable in the worker. Anything that
    persisted it — the run list, the history store, an event — would put a plaintext
    credential somewhere it can be read back."""
    secret = "sk-ant-" + "z" * 30
    run_id = _start(client, provider="anthropic", api_key=secret).json()["run_id"]
    assert secret not in client.get("/api/runs").text
    assert secret not in client.get(f"/api/runs/{run_id}").text


def test_the_shared_key_is_named_in_the_response_when_it_is_used(client, monkeypatch):
    """Allowed is not the same as hidden. A run on someone else's credit says so."""
    monkeypatch.setenv("H2A_ALLOW_SERVER_KEY", "1")
    monkeypatch.setattr(keyvault, "server_fallbacks", lambda: {"anthropic": True})
    r = _start(client, provider="anthropic")
    assert r.status_code == 200, r.text
    assert r.json()["credential"] == "the server's shared key"


def test_the_keys_endpoint_reports_whether_the_shared_key_may_be_spent(client, monkeypatch):
    assert client.get("/api/keys").json()["server_allowed"] is False
    monkeypatch.setenv("H2A_ALLOW_SERVER_KEY", "1")
    assert client.get("/api/keys").json()["server_allowed"] is True
