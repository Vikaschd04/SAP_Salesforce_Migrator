"""
packs.py — the platform-pair knowledge a migration runs on.

Three things decide what a generated artifact looks like, and none of them are code:

    prompts/     how the model is asked to comprehend, generate, and repair
    mappings.yaml   which source layer becomes which target artifact kind
    knowledge/   the RAG corpus the Builder and Critic are grounded in

Together they are a **pack**, one per platform pair. Swapping the pack is most of what
"generate Java instead of Apex" means in practice — the agents, the assurance layer and
the orchestration do not change at all.

    packs/
      hybris_to_salesforce/     ← shipped
      adobe_to_hybris/          ← Phase 3 adds this directory, and nothing else

**Why the pipeline id comes from a ContextVar rather than an argument.** `comprehend.py`
and `generate.py` load their prompts several calls below anything that knows which
migration is running, and threading an id through every signature would touch a dozen
functions to move one string. `runctx` already carries per-run provider, model, credential
and spend cap for exactly this reason, and — being a ContextVar, not a global — two
concurrent runs of different pipelines cannot borrow each other's prompts.

Unset resolves to the shipped pack, so the v1 path behaves precisely as before.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent / "packs"

#: What an unqualified run means — the pipeline that shipped.
DEFAULT_PACK = "hybris_to_salesforce"

#: pipeline id → pack directory name.
#:
#: A *registered* pipeline missing from this map is an error, not a default. The old
#: behaviour — fall back to the shipped pack — is the single worst failure this system
#: can have: a run configured for one platform pair, quietly handed the other pair's
#: prompts, mappings and RAG corpus, producing fluent output for the wrong target. That
#: is not hypothetical. It is what happened on every Adobe→Hybris run for as long as the
#: pipeline id failed to reach the worker threads, and the first line the model read was
#: "Translate the following SAP Hybris class into Salesforce Apex". [4.6]
_PACK_FOR_PIPELINE = {
    "hybris->salesforce": "hybris_to_salesforce",
    "adobe->hybris": "adobe_to_hybris",
}


def available() -> list[str]:
    """Pack directories actually present on disk."""
    if not _ROOT.is_dir():
        return []
    return sorted(p.name for p in _ROOT.iterdir() if p.is_dir())


def pack_name(pipeline_id: str = "") -> str:
    """Which pack this run uses. Explicit argument wins, then the run context.

    No pipeline at all resolves to the shipped pack — that is the v1 path and a handful of
    tools that read a prompt outside a run. A pipeline that *is* named but has no pack
    raises: it means someone registered a platform pair and did not give it a pack, and
    the only safe answer to "which prompts does this pair use" is that nobody has said.
    """
    from src import runctx
    pid = pipeline_id or runctx.pipeline_id() or ""
    if not pid:
        return DEFAULT_PACK
    if pid not in _PACK_FOR_PIPELINE:
        raise KeyError(
            f"pipeline {pid!r} has no knowledge pack. Add it to packs._PACK_FOR_PIPELINE "
            f"and create packs/<name>/. Mapped: {sorted(_PACK_FOR_PIPELINE)}. "
            "Refusing to fall back to the shipped pack — that would generate for the "
            "wrong platform without saying so.")
    return _PACK_FOR_PIPELINE[pid]


def pack_dir(pipeline_id: str = "") -> Path:
    """The pack directory, verified to exist.

    Raises rather than silently falling back to the shipped pack: a run configured for
    Adobe→Hybris that quietly generated Apex because its pack was missing would be the
    worst possible failure — plausible output, entirely the wrong platform.
    """
    name = pack_name(pipeline_id)
    d = _ROOT / name
    if not d.is_dir():
        raise FileNotFoundError(
            f"knowledge pack {name!r} not found at {d}. Available: {available() or 'none'}")
    return d


def prompt(name: str, pipeline_id: str = "") -> str:
    """One prompt template, e.g. `prompt("generate")`."""
    path = pack_dir(pipeline_id) / "prompts" / f"{name}.txt"
    if not path.is_file():
        raise FileNotFoundError(
            f"pack {pack_name(pipeline_id)!r} has no prompt {name!r} at {path}")
    return path.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=8)
def _mappings_cached(pack: str) -> dict:
    path = _ROOT / pack / "mappings.yaml"
    if not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def mappings(pipeline_id: str = "") -> dict:
    """The layer→artifact mapping rules for this pair. Cached; they never change mid-run."""
    return _mappings_cached(pack_name(pipeline_id))


def knowledge_dir(pipeline_id: str = "") -> Path:
    """The RAG corpus for this pair. May not exist — RAG is optional, not required."""
    return pack_dir(pipeline_id) / "knowledge"
