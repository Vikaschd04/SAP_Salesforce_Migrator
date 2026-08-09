"""Platform guarantees: runs are concurrent, isolated, and outlive their process.

These are the properties that separate "a demo" from "something two people can use",
so they are asserted rather than assumed. Run with:

    cd h2a-web/backend && PYTHONPATH=.:../../h2a-mvp pytest tests -q
"""

import importlib
import sys
import threading
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
for p in (str(BACKEND), str(REPO / "h2a-mvp")):
    if p not in sys.path:
        sys.path.insert(0, p)

DEMO = str(REPO / "Testing" / "demo-hybris-ordermgmt" / "acmeordermanagement")


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """A run manager with its own empty database."""
    monkeypatch.setenv("H2A_DB_PATH", str(tmp_path / "runs.db"))
    import store
    import run_manager as rm
    store._conn, store._enabled = None, True
    importlib.reload(store)
    importlib.reload(rm)
    rm._runs.clear()
    return rm


def _await(run, timeout=90):
    end = time.time() + timeout
    while run.status in ("queued", "running") and time.time() < end:
        time.sleep(0.05)
    return run.status


# ── concurrency + isolation ───────────────────────────────────────────────────

def test_two_runs_execute_concurrently(fresh, tmp_path):
    """The process-global lock used to serialise these — one user at a time."""
    a = fresh.start_run(DEMO, str(tmp_path / "a"), provider="mock")
    b = fresh.start_run(DEMO, str(tmp_path / "b"), provider="mock")
    time.sleep(0.25)
    overlapped = a.status == "running" and b.status == "running"
    assert _await(a) == "complete" and _await(b) == "complete"
    assert overlapped, "runs were serialised, not concurrent"


def test_starting_a_run_no_longer_cancels_the_previous_one(fresh, tmp_path):
    a = fresh.start_run(DEMO, str(tmp_path / "a"), provider="mock")
    fresh.start_run(DEMO, str(tmp_path / "b"), provider="mock")
    assert _await(a) == "complete", "the first run was cancelled by the second"


def test_a_runs_provider_never_leaks_into_another(fresh, tmp_path):
    """Selecting a provider used to write os.environ, so a mock run could inherit a
    real provider and start making live API calls — the exact thing a locked-down
    corporate laptop must never do."""
    from src.llm import _get_provider, _load_config
    import src.agentic.orchestrator as O

    seen, lock = {}, threading.Lock()
    real = O.comprehend_class

    def spy(cls, **kw):
        with lock:
            seen.setdefault(threading.current_thread().name, set()).add(
                _get_provider(_load_config()))
        return real(cls, **kw)

    O.comprehend_class = spy
    try:
        a = fresh.start_run(DEMO, str(tmp_path / "a"), provider="mock")
        b = fresh.start_run(DEMO, str(tmp_path / "b"), provider="openrouter")
        _await(a), _await(b)
    finally:
        O.comprehend_class = real

    resolved = {p for s in seen.values() for p in s}
    assert resolved == {"mock", "openrouter"}, f"provider leaked between runs: {resolved}"


# ── durability ────────────────────────────────────────────────────────────────

def test_a_finished_run_outlives_its_process(fresh, tmp_path):
    run = fresh.start_run(DEMO, str(tmp_path / "a"), provider="mock")
    rid = run.id
    assert _await(run) == "complete"

    fresh._runs.clear()                      # the restart
    assert fresh.get_run(rid) is None

    assert any(h["id"] == rid and h["status"] == "complete" for h in fresh.list_runs())
    rec = fresh.get_run_record(rid)
    assert rec and len(rec["events"]) > 10
    assert any(e.get("type") == "run_complete" for e in rec["events"]), \
        "the completion payload — reports, ledger, cost — was not persisted"


def test_a_run_killed_mid_flight_is_not_left_looking_alive(fresh, tmp_path):
    """A crash used to leave a phantom 'running' migration in history forever."""
    import store
    run = fresh.start_run(DEMO, str(tmp_path / "a"), provider="mock")
    assert _await(run) == "complete"

    # Exactly what a kill -9 leaves behind: a row still claiming to be in flight.
    conn = store._connect()
    conn.execute("UPDATE runs SET status='running' WHERE id=?", (run.id,))
    conn.commit()

    importlib.reload(fresh)              # a restart re-imports, which sweeps
    statuses = {h["id"]: h["status"] for h in fresh.list_runs()}
    assert statuses[run.id] == "interrupted"


def test_the_sweep_never_touches_a_run_that_is_still_alive(fresh, tmp_path):
    """Sweeping lazily on first read would mark a live run interrupted. It happens at
    import instead, before any run can exist."""
    run = fresh.start_run(DEMO, str(tmp_path / "a"), provider="mock")
    statuses = {h["id"]: h["status"] for h in fresh.list_runs()}
    assert statuses[run.id] != "interrupted"
    assert _await(run) == "complete"


def test_history_survives_a_reconnect_but_live_runs_come_first(fresh, tmp_path):
    old = fresh.start_run(DEMO, str(tmp_path / "a"), provider="mock")
    assert _await(old) == "complete"
    fresh._runs.clear()
    new = fresh.start_run(DEMO, str(tmp_path / "b"), provider="mock")
    ids = [h["id"] for h in fresh.list_runs()]
    assert ids[0] == new.id, "the live run should lead the list"
    assert old.id in ids, "history was lost"
    _await(new)


def test_an_unwritable_database_degrades_instead_of_breaking_runs(tmp_path, monkeypatch):
    """Persistence is a convenience. A read-only filesystem must cost you history,
    never the migration itself."""
    monkeypatch.setenv("H2A_DB_PATH", "/proc/nonexistent/cannot-write/runs.db")
    import store
    import run_manager as rm
    store._conn, store._enabled = None, True
    importlib.reload(store)
    importlib.reload(rm)
    rm._runs.clear()

    run = rm.start_run(DEMO, str(tmp_path / "a"), provider="mock")
    assert _await(run) == "complete"
    assert rm.list_runs()[0]["id"] == run.id      # still served from memory
