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
import threading
import time
import uuid
import traceback
from pathlib import Path

# Make the existing engine importable. It resolves config.yaml, mappings/ and cache/
# against its own package root, so it needs no particular cwd — verified by running a
# migration from an unrelated directory and diffing the output.
ENGINE_ROOT = Path(__file__).resolve().parents[2] / "h2a-mvp"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))


class Run:
    def __init__(self, run_id: str, input_dir: str, output_dir: str, provider: str,
                 engine: str, verify: bool):
        self.id = run_id
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
            "elapsed": round((self.finished or time.time()) - self.started, 2),
            "result": self.result, "event_count": len(self.events),
            "supervised": self.supervised, "awaiting_gate": self.awaiting_gate,
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
        if self.awaiting_gate is not None and not self._gate_event.is_set():
            self._gate_decision = {"action": "approve"}   # unblock the wait; _ck() then aborts
            self._gate_event.set()
        with self._cond:
            self._cond.notify_all()


_runs: dict[str, Run] = {}


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
              state_dir: str | None = None) -> Run:
    """Start a migration. Runs are independent — starting one no longer cancels another."""
    run_id = uuid.uuid4().hex[:12]
    run = Run(run_id, input_dir, output_dir, provider, engine, verify)
    run.supervised = supervised
    _runs[run_id] = run

    def worker():
        run.status = "running"
        # Per-run provider, not os.environ. Two concurrent runs previously raced over
        # one process-global variable — a mock run could inherit another run's real
        # provider and start making live API calls.
        from src.runctx import set_overrides
        set_overrides(provider=provider)
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
            run.finished = time.time()
            with run._cond:
                run._cond.notify_all()

    threading.Thread(target=worker, daemon=True).start()
    return run


def get_run(run_id: str) -> Run | None:
    return _runs.get(run_id)


def list_runs() -> list[dict]:
    return [r.summary() for r in sorted(_runs.values(), key=lambda r: r.started, reverse=True)]
