"""
run_manager.py — drives the existing H2A engine for the web dashboard.

Each migration runs in a background thread. The engine's `on_event` hook feeds
structured progress events into a per-run event log; the API streams them to the
browser (SSE) and exposes the resulting Salesforce project for browsing/download.

The engine itself is imported and reused unchanged — this is a thin driver, not a
second implementation.
"""

from __future__ import annotations

import sys
import os
import threading
import time
import uuid
import traceback
from pathlib import Path

import store

# Make the existing engine importable. It resolves config.yaml, mappings/ and cache/
# against its own package root, so it needs no particular cwd — verified by running a
# migration from an unrelated directory and diffing the output.
ENGINE_ROOT = Path(__file__).resolve().parents[2] / "h2a-mvp"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))


class Run:
    def __init__(self, run_id: str, input_dir: str, output_dir: str, provider: str,
                 engine: str, verify: bool, owner: str | None = None):
        self.id = run_id
        self.owner = owner              # user id; None when auth is off
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.provider = provider
        self.engine = engine
        self.verify = verify
        self.status = "queued"          # queued | running | complete | error | cancelled
        self.error: str | None = None
        self.cancelled = False          # cooperative-stop flag (checked by the engine)
        self.bb = None                  # captured Blackboard (for source↔generated diff)
        self.started = time.time()
        self.finished: float | None = None
        self.events: list[dict] = []
        self.result: dict = {}          # payload of the run_complete event
        self._cond = threading.Condition()
        # Human-in-the-loop gate state
        self.supervised = False
        self.awaiting_gate: str | None = None   # name of the open gate, or None
        self._gate_event = threading.Event()
        self._gate_decision: dict | None = None

    # ── event log (thread-safe, supports multiple live readers) ──
    def emit(self, ev: dict) -> None:
        with self._cond:
            ev = {**ev, "seq": len(self.events), "ts": round(time.time() - self.started, 2)}
            self.events.append(ev)
            if ev.get("type") == "run_complete":
                self.result = ev
            self._cond.notify_all()

    _HEARTBEAT_SECONDS = 10   # < typical corporate-proxy/load-balancer idle timeout (~15-30s)

    def stream(self):
        """Yield events from the start, then block for new ones until the run ends.

        Yields None during a heartbeat tick — a supervised run can sit silent at a
        review gate for minutes with zero new events, and a fully idle SSE connection
        gets killed by most corporate proxies/load balancers within ~15-30s (they
        assume it's dead). The caller (api_stream) turns a None into an SSE comment
        line so the connection keeps producing bytes and never looks idle, without
        the frontend needing to know or care."""
        idx = 0
        while True:
            with self._cond:
                while idx >= len(self.events) and self.status in ("queued", "running"):
                    if not self._cond.wait(timeout=self._HEARTBEAT_SECONDS):
                        break   # timed out with nothing new — heartbeat, then re-wait
                new = self.events[idx:]
                idx = len(self.events)
                done = self.status not in ("queued", "running")
            if new:
                for ev in new:
                    yield ev
            elif not done:
                yield None
            if done and idx >= len(self.events):
                break

    def summary(self) -> dict:
        return {
            "id": self.id, "status": self.status, "provider": self.provider,
            "engine": self.engine, "verify": self.verify, "error": self.error,
            "input_dir": self.input_dir, "output_dir": self.output_dir,
            "started": self.started,
            "elapsed": round((self.finished or time.time()) - self.started, 2),
            "result": self.result, "event_count": len(self.events),
            "supervised": self.supervised, "awaiting_gate": self.awaiting_gate,
            "owner": self.owner,
            "queue_position": queue_position(self.id) if self.status == "queued" else 0,
        }

    # ── human-in-the-loop gate (blocks the engine thread until a decision arrives) ──
    def gate_cb(self, name: str, payload: dict) -> dict:
        self._gate_event.clear()
        self._gate_decision = None
        self.awaiting_gate = name
        with self._cond:
            self._cond.notify_all()          # wake summary/stream watchers
        self._gate_event.wait()              # ← engine pauses here until submit_gate()
        self.awaiting_gate = None
        return self._gate_decision or {"action": "approve"}

    def submit_gate(self, decision: dict) -> bool:
        if self.awaiting_gate is None:
            return False
        self._gate_decision = decision or {"action": "approve"}
        self._gate_event.set()
        return True

    def request_cancel(self) -> None:
        """Stop this run cleanly. Sets the cooperative-cancel flag the engine checks,
        and unblocks it if it's paused at a review gate — so the thread can exit and
        release the global run lock (otherwise a run abandoned at a gate wedges the UI)."""
        self.cancelled = True
        with _qlock:                    # wake it if it is still waiting for a slot
            _qlock.notify_all()
        if self.awaiting_gate is not None and not self._gate_event.is_set():
            self._gate_decision = {"action": "approve"}   # unblock the wait; _ck() then aborts
            self._gate_event.set()
        with self._cond:
            self._cond.notify_all()


_runs: dict[str, Run] = {}          # live, in-process runs

# ── admission control ─────────────────────────────────────────────────────────
# Removing the old process-global lock made runs concurrent with no ceiling, which
# traded "one user at a time" for "ten users exhaust the box". A migration holds a
# whole Blackboard in memory and fans out to `concurrency` parallel LLM calls, so N
# simultaneous runs is N x that. Admission is FIFO — a semaphore alone would let a
# late arrival jump a run that has been waiting.
def _max_concurrent() -> int:
    try:
        return max(1, int(os.environ.get("H2A_MAX_CONCURRENT_RUNS", "3")))
    except (TypeError, ValueError):
        return 3


_qlock = threading.Condition()
_pending: list[str] = []            # run ids waiting for a slot, oldest first
_active = 0


def queue_position(run_id: str) -> int:
    """1 = next to start; 0 = running or finished."""
    with _qlock:
        return _pending.index(run_id) + 1 if run_id in _pending else 0


def queue_state() -> dict:
    with _qlock:
        return {"active": _active, "waiting": len(_pending), "capacity": _max_concurrent()}


def _admit(run) -> bool:
    """Block until this run may start. False if it was cancelled while waiting."""
    global _active
    with _qlock:
        _pending.append(run.id)
        while True:
            if run.cancelled:
                if run.id in _pending:
                    _pending.remove(run.id)
                _qlock.notify_all()
                return False
            if _active < _max_concurrent() and _pending and _pending[0] == run.id:
                _pending.pop(0)
                _active += 1
                _qlock.notify_all()
                return True
            # Timed wait so a cancel that races the notify still gets noticed.
            _qlock.wait(timeout=0.5)


def _release() -> None:
    global _active
    with _qlock:
        _active = max(0, _active - 1)
        _qlock.notify_all()


def _sweep_interrupted() -> None:
    """Anything recorded as in-flight died with the previous process.

    Deliberately at import, before a single run can exist. Doing it lazily on first
    read would let a run started earlier in this process be marked interrupted while
    it is still happily running.
    """
    n = store.mark_interrupted()
    if n:
        print(f"  · marked {n} interrupted run(s) from a previous process")


_sweep_interrupted()


def list_runs(owner: str | None = None) -> list[dict]:
    """Live runs first, then history from disk — so a restart no longer erases it.

    With `owner` set, only that user's runs are returned. Live runs are filtered here
    and history is filtered in SQL; both must hold or a tenant could see another's work.
    """
    live = {r.id: r.summary() for r in _runs.values()
            if owner is None or r.owner == owner}
    history = [s for s in store.load_all(owner=owner) if s.get("id") not in live]
    return sorted(live.values(), key=lambda s: s.get("started", 0), reverse=True) + history


def owns(run_id: str, owner: str | None) -> bool:
    """Is this run visible to this user? Unowned runs (auth off) are visible to all."""
    if owner is None:
        return True
    run = _runs.get(run_id)
    holder = run.owner if run else store.owner_of(run_id)
    return holder is None or holder == owner


def cancel_active_runs() -> int:
    """Stop every queued/running migration. Runs are independent now, so this is an
    explicit operator action (shutdown, "stop everything") rather than something a new
    run does to its predecessor."""
    n = 0
    for r in list(_runs.values()):
        if r.status in ("queued", "running"):
            r.request_cancel()
            n += 1
    return n


def start_run(input_dir: str, output_dir: str, *, provider: str = "mock",
              engine: str = "agentic", verify: bool = False, supervised: bool = False,
              state_dir: str | None = None, owner: str | None = None,
              api_key: str | None = None, cost_cap: float | None = None) -> Run:
    """Start a migration. Runs are independent — starting one no longer cancels another."""
    run_id = uuid.uuid4().hex[:12]
    run = Run(run_id, input_dir, output_dir, provider, engine, verify, owner=owner)
    run.supervised = supervised
    _runs[run_id] = run

    def worker():
        if not _admit(run):                      # cancelled before it ever started
            run.status = "cancelled"
            run.finished = time.time()
            run.emit({"type": "cancelled", "message": "run stopped before it started"})
            store.save(run)
            with run._cond:
                run._cond.notify_all()
            return
        run.status = "running"
        store.save(run)
        # Per-run provider, not os.environ. Two concurrent runs previously raced over
        # one process-global variable — a mock run could inherit another run's real
        # provider and start making live API calls.
        from src.runctx import set_overrides
        # The cap rides the same per-run channel as the credential, and for the same
        # reason: two tenants running at once must not share one budget.
        set_overrides(provider=provider, api_key=api_key, cost_cap=cost_cap)
        try:
            if engine == "linear":
                from src.pipeline_driver import run_repo_migration
                run.emit({"type": "run_started", "input": input_dir, "note": "linear engine"})
                run_repo_migration(input_dir, output_dir, verify=verify or None)
                run.emit({"type": "run_complete", "note": "linear run finished"})
            else:
                from src.agentic.orchestrator import run_agentic_migration
                run.bb = run_agentic_migration(
                    input_dir, output_dir, verify=verify or None,
                    on_event=run.emit,
                    gate=(run.gate_cb if run.supervised else None),
                    should_cancel=lambda: run.cancelled,
                    # available immediately, so the UI can view code and regenerate a
                    # single file while the run is paused at a review gate
                    on_blackboard=lambda b: setattr(run, "bb", b),
                    # per-run output dirs keep history; incremental state is keyed to
                    # the codebase so a re-run of the same repo still reuses results
                    state_dir=state_dir)
            run.status = "cancelled" if run.cancelled else "complete"
        except Exception as e:
            if run.cancelled:                 # RunCancelled (or any error after a cancel)
                run.status = "cancelled"
                run.emit({"type": "cancelled", "message": "run stopped"})
            else:
                run.error = f"{e}\n{traceback.format_exc()}"
                run.status = "error"
                run.emit({"type": "error", "message": str(e)})
        finally:
            _release()               # let the next queued run in, whatever happened here
            run.finished = time.time()
            store.save(run)          # the run's permanent record
            with run._cond:
                run._cond.notify_all()

    threading.Thread(target=worker, daemon=True).start()
    return run


def get_run(run_id: str) -> Run | None:
    return _runs.get(run_id)


def get_run_record(run_id: str) -> dict | None:
    """A finished run's stored summary + events, for one that is no longer in memory."""
    rec = store.load_one(run_id)
    if rec is None:
        return None
    return {**rec, "events": store.load_events(run_id)}



