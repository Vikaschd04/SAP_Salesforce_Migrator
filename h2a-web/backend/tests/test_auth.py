"""Accounts, sessions, and tenant isolation.

The isolation tests matter most: a migration contains the customer's uploaded source
code, so one tenant reading another's run is the worst failure this product can have.
Those are asserted at the HTTP boundary, because that is where an attacker sits — not
at the function that the UI happens to call.
"""

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
for p in (str(BACKEND), str(REPO / "h2a-mvp")):
    if p not in sys.path:
        sys.path.insert(0, p)

PW = "correct-horse-battery"


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A server with auth on and its own empty database."""
    monkeypatch.setenv("H2A_DB_PATH", str(tmp_path / "runs.db"))
    monkeypatch.setenv("H2A_AUTH", "1")
    monkeypatch.setenv("H2A_ALLOW_SIGNUP", "1")
    monkeypatch.delenv("H2A_HOSTED", raising=False)
    import store, auth as A, run_manager, app as appmod
    for m in (store, A, run_manager, appmod):
        store._conn, store._enabled = None, True
        importlib.reload(m)
    run_manager._runs.clear()
    return appmod


def client(api):
    return TestClient(api.app)


def register(c, email, password=PW):
    r = c.post("/api/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["user"]


# ── accounts ──────────────────────────────────────────────────────────────────

def test_signup_then_me_returns_the_user(api):
    c = client(api)
    user = register(c, "ada@example.com")
    assert user["email"] == "ada@example.com"
    assert user["role"] == "admin", "the first account should own the instance"
    assert c.get("/api/auth/me").json()["user"]["email"] == "ada@example.com"


def test_second_account_is_an_ordinary_member(api):
    c = client(api)
    register(c, "ada@example.com")
    assert register(client(api), "bob@example.com")["role"] == "member"


def test_password_is_never_stored_in_plaintext(api, tmp_path):
    register(client(api), "ada@example.com", "hunter2-hunter2")
    blob = (tmp_path / "runs.db").read_bytes()
    assert b"hunter2-hunter2" not in blob


def test_login_rejects_a_wrong_password(api):
    c = client(api)
    register(c, "ada@example.com")
    r = client(api).post("/api/auth/login",
                         json={"email": "ada@example.com", "password": "wrong-password"})
    assert r.status_code == 401


def test_login_does_not_reveal_whether_an_account_exists(api):
    c = client(api)
    register(c, "ada@example.com")
    fresh = client(api)
    a = fresh.post("/api/auth/login", json={"email": "ada@example.com", "password": "nope-nope-nope"})
    b = fresh.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_short_passwords_are_refused(api):
    r = client(api).post("/api/auth/signup", json={"email": "ada@example.com", "password": "short"})
    assert r.status_code == 400


def test_duplicate_email_is_refused(api):
    c = client(api)
    register(c, "ada@example.com")
    r = client(api).post("/api/auth/signup", json={"email": "ADA@example.com", "password": PW})
    assert r.status_code == 400, "email comparison must be case-insensitive"


# ── sessions ──────────────────────────────────────────────────────────────────

def test_api_is_closed_without_a_session(api):
    assert client(api).get("/api/runs").status_code == 401


def test_health_and_config_stay_reachable(api):
    c = client(api)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/config").status_code == 200


def test_logout_invalidates_the_session_server_side(api):
    c = client(api)
    register(c, "ada@example.com")
    assert c.get("/api/runs").status_code == 200
    token = c.cookies.get("h2a_session")
    c.post("/api/auth/logout")

    # Replay the stolen cookie: it must be dead on the server, not merely dropped.
    replay = client(api)
    replay.cookies.set("h2a_session", token)
    assert replay.get("/api/runs").status_code == 401


def test_a_forged_token_is_rejected(api):
    c = client(api)
    register(c, "ada@example.com")
    forged = client(api)
    forged.cookies.set("h2a_session", "not-a-real-token")
    assert forged.get("/api/runs").status_code == 401


def test_the_session_cookie_is_httponly(api):
    c = client(api)
    r = c.post("/api/auth/signup", json={"email": "ada@example.com", "password": PW})
    assert "httponly" in r.headers["set-cookie"].lower(), "JS must not be able to read it"


# ── tenant isolation — the one that really matters ────────────────────────────

def _start_run(c, api):
    demo = str(REPO / "Testing" / "demo-hybris-ordermgmt" / "acmeordermanagement")
    r = c.post("/api/runs", data={"provider": "mock", "engine": "agentic", "input_path": demo})
    assert r.status_code == 200, r.text
    rid = r.json()["run_id"]
    import run_manager
    run = run_manager.get_run(rid)
    import time
    end = time.time() + 90
    while run.status in ("queued", "running") and time.time() < end:
        time.sleep(0.05)
    return rid


def test_one_tenant_cannot_see_anothers_run(api):
    ada = client(api)
    register(ada, "ada@example.com")
    rid = _start_run(ada, api)

    bob = client(api)
    register(bob, "bob@example.com")
    assert bob.get(f"/api/runs/{rid}").status_code == 404, \
        "another tenant read a migration containing uploaded source code"
    assert bob.get(f"/api/runs/{rid}/files").status_code == 404
    assert bob.get(f"/api/runs/{rid}/package").status_code == 404


def test_history_only_lists_your_own_runs(api):
    ada = client(api)
    register(ada, "ada@example.com")
    rid = _start_run(ada, api)

    bob = client(api)
    register(bob, "bob@example.com")
    assert [r["id"] for r in bob.get("/api/runs").json()["runs"]] == []
    assert rid in [r["id"] for r in ada.get("/api/runs").json()["runs"]]


def test_a_tenant_cannot_cancel_anothers_run(api):
    ada = client(api)
    register(ada, "ada@example.com")
    rid = _start_run(ada, api)
    bob = client(api)
    register(bob, "bob@example.com")
    assert bob.post(f"/api/runs/{rid}/cancel").status_code == 404


# ── the local single-user path stays unchanged ────────────────────────────────

def test_auth_off_locally_leaves_the_dashboard_open(tmp_path, monkeypatch):
    """Forcing a login on a single-user laptop would be theatre, and would make the
    dashboard behave differently from the CLI for no security gain."""
    monkeypatch.setenv("H2A_DB_PATH", str(tmp_path / "runs.db"))
    monkeypatch.delenv("H2A_AUTH", raising=False)
    monkeypatch.delenv("H2A_HOSTED", raising=False)
    import store, auth as A, run_manager, app as appmod
    for m in (store, A, run_manager, appmod):
        store._conn, store._enabled = None, True
        importlib.reload(m)
    run_manager._runs.clear()

    c = TestClient(appmod.app)
    assert c.get("/api/runs").status_code == 200
    assert c.get("/api/auth/me").json()["required"] is False


def test_hosted_deploys_always_require_auth(monkeypatch):
    monkeypatch.setenv("H2A_HOSTED", "1")
    monkeypatch.delenv("H2A_AUTH", raising=False)
    import auth as A
    importlib.reload(A)
    assert A.auth_required() is True, "a public deploy must never be open"


def test_signup_closes_after_the_first_account_unless_opened(tmp_path, monkeypatch):
    """An open public deploy is a door to your API credits and other tenants' source."""
    monkeypatch.setenv("H2A_DB_PATH", str(tmp_path / "runs.db"))
    monkeypatch.setenv("H2A_AUTH", "1")
    monkeypatch.delenv("H2A_ALLOW_SIGNUP", raising=False)
    monkeypatch.delenv("H2A_HOSTED", raising=False)
    import store, auth as A, run_manager, app as appmod
    for m in (store, A, run_manager, appmod):
        store._conn, store._enabled = None, True
        importlib.reload(m)
    run_manager._runs.clear()

    c = TestClient(appmod.app)
    assert A.signup_open() is True                    # bootstrap: someone must be first
    register(c, "ada@example.com")
    assert A.signup_open() is False
    r = TestClient(appmod.app).post("/api/auth/signup",
                                    json={"email": "bob@example.com", "password": PW})
    assert r.status_code == 403
