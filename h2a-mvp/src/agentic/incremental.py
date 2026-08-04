"""
incremental.py — delta migration for the agentic engine.

Migrations are iterative: you run, review, fix one class, run again. Re-doing every
LLM call each time is the single biggest waste in the pipeline. This module lets a
re-run reuse the previous result for anything that provably hasn't changed.

**Correctness is the whole game here** — serving a stale artifact is far worse than
being slow. A cached result is reused only when its full *fingerprint* matches, which
covers everything that can change the output:

  · the source of the class(es) being converted
  · the source of every class in its transitive dependency domains
    (generated Apex calls those signatures — if a dependency's API moved, this is stale)
  · the SObject schema (injected into every generation prompt)
  · the mapping rules
  · the plan decision for the target (pattern / Convert-vs-Skip / native flag) — a
    reviewer override at the plan gate must force a rebuild
  · the provider + model (a different model produces different code)

Anything unrecognised or mismatched degrades to a normal full build.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

STATE_FILE = ".h2a_agentic_state.json"
VERSION = 1


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", "replace")).hexdigest()


def recipe_hash(provider: str, model: str, schema: dict, mappings: dict) -> str:
    """Identity of *how* output is produced. Changing any of it invalidates everything."""
    return _md5("|".join([
        f"v{VERSION}", provider or "", model or "",
        _md5(json.dumps(schema or {}, sort_keys=True, default=str)),
        _md5(json.dumps(mappings or {}, sort_keys=True, default=str)),
    ]))


def class_hashes(all_classes: list) -> dict:
    """class_name → hash of its source text."""
    return {c.get("class_name", ""): _md5(c.get("source", "") or "") for c in all_classes}


def target_fingerprint(plan_item, hashes: dict, dep_class_names, recipe: str) -> str:
    """Everything that, if changed, must invalidate this target's cached artifact."""
    own = sorted((c.get("class_name", "") for c in plan_item.source_classes))
    deps = sorted(set(dep_class_names) - set(own))
    parts = [
        recipe,
        f"{plan_item.target_name}|{plan_item.apex_pattern}|{plan_item.target_kind}"
        f"|{plan_item.native_recommendation}|{plan_item.layer}",
        *[f"{n}:{hashes.get(n, '')}" for n in own],
        *[f"dep:{n}:{hashes.get(n, '')}" for n in deps],
    ]
    return _md5("||".join(parts))


# ── persistence ───────────────────────────────────────────────────────────────

def load_state(output_dir: str, recipe: str) -> dict:
    """Previous run's reusable results, or an empty state if absent/stale/unreadable."""
    empty = {"comprehensions": {}, "artifacts": {}}
    path = Path(output_dir) / STATE_FILE
    if not path.exists():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return empty
    if data.get("version") != VERSION or data.get("recipe") != recipe:
        return empty                      # provider/model/schema/mappings changed
    return {"comprehensions": data.get("comprehensions") or {},
            "artifacts": data.get("artifacts") or {}}


def save_state(output_dir: str, recipe: str, comprehensions: dict, artifacts: dict) -> None:
    path = Path(output_dir) / STATE_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "version": VERSION, "recipe": recipe,
            "comprehensions": comprehensions, "artifacts": artifacts,
        }, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)                 # atomic
    except Exception as e:                # never let caching break a successful run
        print(f"  ⚠ could not save incremental state: {e}")


# ── artifact (de)serialisation ────────────────────────────────────────────────

_CACHED_FIELDS = ("target_name", "layer", "apex_pattern", "main_class", "test_class",
                  "mapping_notes", "sobject_refs", "business_rules", "critic_findings",
                  "review_flags", "lwc_bundle", "apex_controller", "status")


def artifact_to_cache(art) -> dict:
    """Persist only what can't be recovered from the repo. `source_classes` is
    deliberately excluded — it's re-attached from the fresh plan item on reuse, which
    keeps the state file small and the source always current."""
    return {f: getattr(art, f) for f in _CACHED_FIELDS}


def artifact_from_cache(data: dict, plan_item):
    """Rebuild an Artifact from a cached payload, re-attaching live source classes."""
    from src.agentic.blackboard import Artifact
    art = Artifact(target_name=data.get("target_name", plan_item.target_name),
                   layer=data.get("layer", plan_item.layer))
    for f in _CACHED_FIELDS:
        if f in data and f not in ("target_name", "layer"):
            setattr(art, f, data[f])
    art.source_classes = [{"class_name": c.get("class_name", ""), "layer": c.get("layer", ""),
                           "source": c.get("source", "")} for c in plan_item.source_classes]
    return art
