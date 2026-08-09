"""
store.py — durable run history.

Runs lived in a module-level dict, so a restart, a redeploy, or a Render free-tier
sleep erased every migration anyone had done. That is fine for a demo and disqualifying
for real client work: a migration is a multi-hour, multi-thousand-dollar artifact and
losing its audit trail because a container recycled is not acceptable.

**Why SQLite and not Postgres.** The roadmap says Postgres, and for a multi-tenant SaaS
it should be. But the same code has to run on a laptop, in a VS Code extension host, and
in a container with no attached services — and requiring a database server to open the
dashboard would be a worse product for every one of those. SQLite is in the standard
library, needs no server, and handles this shape of load comfortably. Everything below
goes through a small interface so swapping the backend later touches this file only.

Writes are best-effort by design: persistence failing must degrade run history, never
kill a migration that is already running.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parents[2] / ".h2a" / "runs.db"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_enabled = True


def db_path() -> Path:
    """H2A_DB_PATH lets a deployment point this at a mounted volume."""
    return Path(os.environ.get("H2A_DB_PATH") or _DEFAULT)


def _connect() -> sqlite3.Connection | None:
    global _conn, _enabled
    if not _enabled:
        return None
    if _conn is not None:
        return _conn
    try:
        p = db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: every run has its own thread and they all write here,
        # serialised by _lock. WAL keeps a reader (the history page) from blocking them.
        c = sqlite3.connect(str(p), check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""CREATE TABLE IF NOT EXISTS runs (
                       id TEXT PRIMARY KEY,
                       started REAL, finished REAL, status TEXT,
                       provider TEXT, engine TEXT, verify INTEGER, supervised INTEGER,
                       input_dir TEXT, output_dir TEXT, error TEXT,
                       summary TEXT, events TEXT, owner TEXT)""")
        # Added after the first release; existing databases need the column.
        if "owner" not in {r[1] for r in c.execute("PRAGMA table_info(runs)")}:
            c.execute("ALTER TABLE runs ADD COLUMN owner TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS runs_owner ON runs(owner)")
        c.execute("CREATE INDEX IF NOT EXISTS runs_started ON runs(started DESC)")
        c.commit()
        _conn = c
        return c
    except Exception as e:                      # a read-only FS must not break the app
        print(f"  ⚠ run history disabled ({e})")
        _enabled = False
        return None


# Full event logs are the bulk of the payload and a long run produces thousands.
# Keeping the tail is enough to reconstruct what happened without unbounded growth.
_MAX_EVENTS = 4000


def save(run) -> None:
    """Persist a run. Safe to call repeatedly — the latest state wins."""
    c = _connect()
    if c is None:
        return
    try:
        s = run.summary()
        events = run.events[-_MAX_EVENTS:]
        with _lock:
            c.execute(
                "INSERT OR REPLACE INTO runs "
                "(id, started, finished, status, provider, engine, verify, supervised, "
                " input_dir, output_dir, error, summary, events, owner) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run.id, run.started, run.finished, run.status, run.provider, run.engine,
                 int(bool(run.verify)), int(bool(run.supervised)), run.input_dir,
                 run.output_dir, run.error, json.dumps(s), json.dumps(events),
                 getattr(run, "owner", None)))
            c.commit()
    except Exception:
        pass                                    # history is a convenience, never a blocker


def _row(summary_json: str, status: str, error: str | None) -> dict:
    """Merge the row's authoritative columns over the stored summary blob.

    The blob is a snapshot from when the run last saved itself, so a later column-only
    update (mark_interrupted) would otherwise be invisible to readers — history would
    keep showing a crashed run as 'complete'.
    """
    s = json.loads(summary_json)
    s["status"] = status
    if error and not s.get("error"):
        s["error"] = error
    return s


def load_all(limit: int = 100, owner: str | None = None) -> list[dict]:
    """Past runs, newest first — including ones from before the last restart.

    `owner` scoping is applied in SQL rather than filtered afterwards: a user must not
    be able to see another tenant's migrations, and the safest place to enforce that is
    the query, not the caller.
    """
    c = _connect()
    if c is None:
        return []
    try:
        with _lock:
            if owner is None:
                rows = c.execute("SELECT summary, status, error FROM runs "
                                 "ORDER BY started DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = c.execute("SELECT summary, status, error FROM runs WHERE owner = ? "
                                 "ORDER BY started DESC LIMIT ?", (owner, limit)).fetchall()
        return [_row(*r) for r in rows if r and r[0]]
    except Exception:
        return []


def owner_of(run_id: str) -> str | None:
    c = _connect()
    if c is None:
        return None
    try:
        with _lock:
            row = c.execute("SELECT owner FROM runs WHERE id = ?", (run_id,)).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def load_events(run_id: str) -> list[dict]:
    """The stored event log for a finished run, so its report survives a restart."""
    c = _connect()
    if c is None:
        return []
    try:
        with _lock:
            row = c.execute("SELECT events FROM runs WHERE id = ?", (run_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else []
    except Exception:
        return []


def load_one(run_id: str) -> dict | None:
    c = _connect()
    if c is None:
        return None
    try:
        with _lock:
            row = c.execute("SELECT summary, status, error FROM runs WHERE id = ?",
                            (run_id,)).fetchone()
        return _row(*row) if row and row[0] else None
    except Exception:
        return None


def mark_interrupted() -> int:
    """A run recorded as 'running' at startup cannot be running — its process is gone.

    Without this, history shows phantom in-flight migrations forever after a crash.
    """
    c = _connect()
    if c is None:
        return 0
    try:
        with _lock:
            cur = c.execute(
                "UPDATE runs SET status='interrupted', finished=?, "
                "error=COALESCE(error,'the server restarted while this run was in progress') "
                "WHERE status IN ('queued','running')", (time.time(),))
            c.commit()
            return cur.rowcount or 0
    except Exception:
        return 0
