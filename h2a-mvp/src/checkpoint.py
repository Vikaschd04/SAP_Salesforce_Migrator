"""
checkpoint.py — "restore to before I approved the plan".

A review gate is a decision made once, on incomplete information, and lived with for the
rest of the run. The reviewer who excludes a domain at the plan gate and regrets it two
stages later has exactly one option today: run the whole migration again from zero, and
pay for it again. That cost is what stops people exploring alternatives, which is a shame,
because comparing two plans is the single most useful thing a reviewer can do.

The Blackboard is already one serializable object, so a checkpoint is a snapshot of it.
Taken automatically at each gate — *before* the decision is applied, which is what makes
"before I approved the plan" a real position rather than an approximation — and on demand.

**What a checkpoint does not restore, and why that matters.** It captures the run's state,
not the output directory. Generated files on disk belong to whatever ran last, so a
restored checkpoint can describe a plan that the `.cls` files beside it do not implement.
Pretending otherwise would produce the exact failure this product exists to prevent: a
confident, coherent, wrong picture. So `load()` reports the mismatch, `restore_files` is a
separate deliberate step, and the source fingerprint is checked on the way back in — a
checkpoint restored against a repo that has since changed is reported as drifted rather
than silently blending an old plan with new source.
"""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import json
import time
from pathlib import Path

# Everything on the Blackboard that is plain data. `on_decision` is a live callback and is
# deliberately absent: it belongs to the process that created it, not to the state.
_FIELDS = [
    "input_dir", "output_dir", "offline",
    "domains", "adjacency", "schedule", "all_classes", "item_types", "relations",
    "enum_types", "schema", "source_corpus", "frontend_skipped", "test_classes",
    "preflight", "unreadable", "radar", "orgfit", "forecast",
    "characterization", "rule_ledger", "approvals",
    "comprehensions", "validation_results", "reconciliation", "verify_result", "parity",
    "decisions", "open_questions",
]

_DIRNAME = "checkpoints"
FORMAT = 1
# Snapshots are self-sufficient — they carry the source they were taken against, so a
# restore does not depend on the repository still being there. That makes them roughly
# four times the size of the corpus, several times per run, and per-run output dirs keep
# every one. Source text compresses about tenfold, which is what makes carrying it
# affordable rather than a choice between self-sufficiency and disk.
_SUFFIX = ".json.gz"


# The schema carries `required` and `unique` as sets. JSON has no set, and letting them
# come back as lists would be the quiet kind of wrong: membership still works, so nothing
# fails, right up until something does a set operation on them. Tagged on the way out and
# rebuilt on the way in, so a restored Blackboard is the same shape as a live one rather
# than merely a similar-looking one.
def _encode(o):
    if isinstance(o, (set, frozenset)):
        return {"__set__": sorted(o, key=str)}
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(f"cannot checkpoint {type(o).__name__}")


def _decode(d: dict):
    if len(d) == 1 and "__set__" in d:
        return set(d["__set__"])
    return d


def _dir(root: str) -> Path:
    return Path(root) / _DIRNAME


def source_fingerprint(bb) -> str:
    """A hash over the source the run was built from, so a restore can tell whether the
    repository still says what it said when the checkpoint was taken."""
    h = hashlib.sha256()
    for c in sorted(bb.all_classes or [], key=lambda c: c.get("class_name", "")):
        h.update((c.get("class_name") or "").encode("utf-8"))
        h.update(hashlib.sha256((c.get("source") or "").encode("utf-8")).digest())
    return h.hexdigest()[:16]


def save(bb, name: str, *, phase: str = "", root: str | None = None,
         note: str = "") -> dict:
    """Snapshot the Blackboard. Returns the checkpoint's metadata."""
    root = root or bb.output_dir
    d = _dir(root)
    d.mkdir(parents=True, exist_ok=True)

    # Millisecond-keyed so ids sort chronologically, but never only that: two snapshots
    # taken in the same millisecond would otherwise share a name and one would overwrite
    # the other — losing a checkpoint silently, which is the one thing a checkpoint must
    # not do. Rare in a real run and certain in a fast one.
    base = f"{int(time.time() * 1000):x}"
    cid, n = base, 0
    while (d / f"{cid}{_SUFFIX}").exists():
        n += 1
        cid = f"{base}-{n}"

    payload = {
        "format": FORMAT,
        "id": cid,
        "name": name,
        "phase": phase,
        "note": note,
        "at": time.time(),
        "source_fingerprint": source_fingerprint(bb),
        "state": {f: getattr(bb, f, None) for f in _FIELDS},
        "plan": [dataclasses.asdict(p) for p in (bb.plan or [])],
        "artifacts": [dataclasses.asdict(a) for a in (bb.artifacts or [])],
    }
    blob = json.dumps(payload, default=_encode).encode("utf-8")
    # Written whole, then moved into place: a checkpoint half-written by an interrupted
    # run must not look like one that can be restored.
    tmp = d / f".{cid}.tmp"
    tmp.write_bytes(gzip.compress(blob, 6))
    tmp.replace(d / f"{cid}{_SUFFIX}")
    return summarise(payload)


def summarise(payload: dict) -> dict:
    """The metadata a reviewer picks from — never the whole state, which is large."""
    plan = payload.get("plan") or []
    arts = payload.get("artifacts") or []
    state = payload.get("state") or {}
    return {
        "id": payload.get("id", ""),
        "name": payload.get("name", ""),
        "phase": payload.get("phase", ""),
        "note": payload.get("note", ""),
        "at": payload.get("at", 0),
        "source_fingerprint": payload.get("source_fingerprint", ""),
        "classes": len(state.get("all_classes") or []),
        "plan_items": len(plan),
        "convert": sum(1 for p in plan if p.get("target_kind") != "Skip"),
        "skip": sum(1 for p in plan if p.get("target_kind") == "Skip"),
        "artifacts": len(arts),
        "failed": sum(1 for a in arts if a.get("status") == "error"),
    }


def list_all(root: str) -> list[dict]:
    """Every checkpoint under a run's output, newest first."""
    d = _dir(root)
    if not d.is_dir():
        return []
    out = []
    for f in d.glob(f"*{_SUFFIX}"):
        try:
            out.append(summarise(json.loads(gzip.decompress(f.read_bytes()),
                                            object_hook=_decode)))
        except (OSError, ValueError, gzip.BadGzipFile):
            # A corrupt checkpoint must not hide the intact ones beside it.
            continue
    return sorted(out, key=lambda c: c["at"], reverse=True)


def _read(root: str, cid: str) -> dict:
    path = _dir(root) / f"{cid}{_SUFFIX}"
    if not path.is_file():
        raise FileNotFoundError(f"no checkpoint {cid} under {root}")
    payload = json.loads(gzip.decompress(path.read_bytes()), object_hook=_decode)
    if payload.get("format") != FORMAT:
        raise ValueError(f"checkpoint {cid} was written by a different version "
                         f"(format {payload.get('format')}, expected {FORMAT})")
    return payload


def load(root: str, cid: str, *, on_decision=None) -> tuple:
    """Rebuild a Blackboard from a checkpoint.

    Returns `(bb, warnings)`. The warnings are the point: a checkpoint restored into a
    changed world is still useful, and a restore that hid that would be a trap.
    """
    from src.agentic.blackboard import Blackboard, PlanItem, Artifact

    payload = _read(root, cid)
    state = payload.get("state") or {}

    bb = Blackboard(input_dir=state.get("input_dir", ""),
                    output_dir=state.get("output_dir", ""))
    for f in _FIELDS:
        if f in state and state[f] is not None:
            setattr(bb, f, state[f])
    bb.plan = [PlanItem(**_only_fields(PlanItem, p)) for p in payload.get("plan") or []]
    bb.artifacts = [Artifact(**_only_fields(Artifact, a))
                    for a in payload.get("artifacts") or []]
    bb.on_decision = on_decision

    warnings = []
    now = source_fingerprint(bb)
    if payload.get("source_fingerprint") and now != payload["source_fingerprint"]:
        # Can only happen if the checkpoint's own class list was edited, but the check is
        # cheap and the failure it catches is silent.
        warnings.append("The snapshot's source no longer hashes to what was recorded — "
                        "this checkpoint may have been modified.")

    src = Path(bb.input_dir)
    if bb.input_dir and not src.exists():
        warnings.append(f"The source repository `{bb.input_dir}` no longer exists, so "
                        "this state cannot be rebuilt from it.")

    out = Path(root)
    generated = list(out.glob("force-app/**/*.cls")) if out.is_dir() else []
    if generated:
        warnings.append(
            f"{len(generated)} generated file(s) are already on disk and belong to "
            "whatever ran last, not to this checkpoint. Restoring state does not rewrite "
            "them — the plan you are looking at may not be the plan they implement.")
    return bb, warnings


def _only_fields(cls, data: dict) -> dict:
    """Drop keys a dataclass no longer has, so an older checkpoint still loads."""
    known = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in (data or {}).items() if k in known}


def diff(root: str, a_id: str, b_id: str) -> dict:
    """What changed between two checkpoints — the reason to keep more than one.

    Answers "I planned it the other way, what did that actually change?" without needing
    both runs open side by side.
    """
    a, b = _read(root, a_id), _read(root, b_id)

    def _plan(p):
        return {i["target_name"]: i for i in p.get("plan") or []}

    def _arts(p):
        return {i["target_name"]: i for i in p.get("artifacts") or []}

    pa, pb = _plan(a), _plan(b)
    aa, ab = _arts(a), _arts(b)

    decisions = []
    for name in sorted(set(pa) | set(pb)):
        x, y = pa.get(name), pb.get(name)
        if x and y and (x.get("target_kind") != y.get("target_kind")
                        or x.get("native_recommendation") != y.get("native_recommendation")):
            decisions.append({"target": name, "kind": "changed",
                              "from": x.get("target_kind"), "to": y.get("target_kind"),
                              "from_native": x.get("native_recommendation", ""),
                              "to_native": y.get("native_recommendation", "")})
        elif x and not y:
            decisions.append({"target": name, "kind": "removed",
                              "from": x.get("target_kind"), "to": None})
        elif y and not x:
            decisions.append({"target": name, "kind": "added",
                              "from": None, "to": y.get("target_kind")})

    built = []
    for name in sorted(set(aa) | set(ab)):
        x, y = aa.get(name), ab.get(name)
        if x and y:
            if _code(x) != _code(y):
                built.append({"target": name, "kind": "regenerated",
                              "from_status": x.get("status"), "to_status": y.get("status")})
            elif x.get("status") != y.get("status"):
                built.append({"target": name, "kind": "status",
                              "from_status": x.get("status"), "to_status": y.get("status")})
        elif x and not y:
            built.append({"target": name, "kind": "gone", "from_status": x.get("status"),
                          "to_status": None})
        else:
            built.append({"target": name, "kind": "new", "from_status": None,
                          "to_status": y.get("status")})

    sa, sb = summarise(a), summarise(b)
    return {
        "a": sa, "b": sb,
        "plan_changes": decisions,
        "artifact_changes": built,
        "same_source": a.get("source_fingerprint") == b.get("source_fingerprint"),
        "summary": {
            "plan_changed": len(decisions),
            "artifacts_changed": len(built),
            "convert_delta": sb["convert"] - sa["convert"],
            "failed_delta": sb["failed"] - sa["failed"],
        },
    }


def _code(art: dict) -> str:
    return (art.get("main_class") or "") + "\x00" + (art.get("test_class") or "")


def headline(d: dict) -> str:
    s = d["summary"]
    if not s["plan_changed"] and not s["artifacts_changed"]:
        # Same plan from different source is the interesting case, not the boring one:
        # the repository moved and the decisions did not, which a reviewer needs to know
        # before concluding the two runs are interchangeable.
        return ("Identical — these two checkpoints planned and built the same thing."
                if d["same_source"] else
                "Same plan and artifacts, but taken against different source — the "
                "repository changed and these decisions did not follow it.")
    bits = []
    if s["plan_changed"]:
        bits.append(f"{s['plan_changed']} plan decision(s) differ")
    if s["artifacts_changed"]:
        bits.append(f"{s['artifacts_changed']} artifact(s) differ")
    tail = ""
    if s["convert_delta"]:
        tail = f" · {s['convert_delta']:+d} converted"
    if s["failed_delta"]:
        tail += f" · {s['failed_delta']:+d} failed"
    warn = "" if d["same_source"] else " ⚠ different source"
    return " · ".join(bits) + tail + warn
