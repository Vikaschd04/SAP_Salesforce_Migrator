"""
pipeline.py — which migration are we running, and who does the work.

A **pipeline** is a source adapter + a target adapter + a knowledge pack. Exactly two are
supported, by decision rather than by limitation:

    hybris   → salesforce      shipped, must not regress
    adobe    → hybris          in build

**The engine-version switch is the safety mechanism, and also the proof.** `H2A_ENGINE_VERSION`
selects whether a run goes through the original code path (`v1`) or through these adapters
(`v2`). v1 remains reachable and byte-identical for as long as anyone wants it, which is
what makes adopting v2 a decision rather than a leap.

It is also how the seam gets proven rather than asserted: because the v2 adapters delegate
to the *same* functions v1 calls, running the reference migration both ways must produce
identical output. `tests/test_golden.py` checks exactly that. A difference means the
refactor changed behaviour — which is the one thing it is not allowed to do.

Adapters are deliberately thin. They own *dispatch*, never logic: an adapter that
reimplemented generation would be a second copy to keep correct, and the whole point is
that there is one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

V1 = "v1"
V2 = "v2"


def engine_version(config: dict | None = None) -> str:
    """Which engine path this run uses. `v1` unless explicitly asked otherwise.

    Defaulting to v1 is the promise: an existing user who upgrades gets the pipeline they
    had, until they opt in.
    """
    env = (os.environ.get("H2A_ENGINE_VERSION") or "").strip().lower()
    if env in (V1, V2):
        return env
    cfg = str(((config or {}).get("engine_version") or "")).strip().lower()
    return cfg if cfg in (V1, V2) else V1


def v2_enabled(config: dict | None = None) -> bool:
    return engine_version(config) == V2


# ── adapter contracts ─────────────────────────────────────────────────────────
# Protocols rather than base classes: an adapter is a bundle of functions, and inheritance
# would buy nothing but a place for shared state to accumulate.

@runtime_checkable
class SourceAdapter(Protocol):
    platform: str
    label: str

    def detect(self, root: str) -> dict:
        """Is this that platform? Verdict, confidence, blockers — no model calls."""

    def read(self, root: str) -> object:
        """The whole source, as an `ir.SourceModel`."""


@runtime_checkable
class TargetAdapter(Protocol):
    platform: str
    label: str
    #: Can generated output be compiled/deployed by an authoritative oracle?
    has_oracle: bool

    def plan(self, units: list, config: dict) -> list:
        """Source units → the targets this platform would build from them.

        Takes a *slice* of units rather than a whole SourceModel, because the Planner
        asks per dependency-domain rather than for the estate at once. Units are dicts —
        the wire format the pipeline already passes around (see `ir.SourceUnit.to_dict`).
        """

    def emit(self, output_dir: str, artifacts: list, model, config: dict) -> list:
        """Write the package in the target's own layout. Returns paths created."""

    def verify(self, output_dir: str, config: dict) -> dict:
        """Ask the oracle. `{"ran": False}` when there is none to ask."""


@dataclass(frozen=True)
class Pipeline:
    id: str                       # "hybris->salesforce"
    source: object                # SourceAdapter
    target: object                # TargetAdapter
    label: str = ""
    knowledge_pack: str = ""      # directory of prompts/mappings/RAG for this pair
    shipped: bool = False         # is this the path customers already run?

    @property
    def source_platform(self) -> str:
        return getattr(self.source, "platform", "")

    @property
    def target_platform(self) -> str:
        return getattr(self.target, "platform", "")

    @property
    def verifiable(self) -> bool:
        """Whether this pipeline can say *proven to run* rather than *generated*.

        Surfaced as a property because it is a claim the sign-off contract makes, and it
        differs per target: Salesforce lends us a hosted compiler, SAP does not.
        """
        return bool(getattr(self.target, "has_oracle", False))


_REGISTRY: dict[str, Pipeline] = {}


def register(p: Pipeline) -> Pipeline:
    _REGISTRY[p.id] = p
    return p


def get(pipeline_id: str) -> Pipeline:
    if pipeline_id not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "none registered"
        raise KeyError(f"unknown pipeline {pipeline_id!r}. Available: {known}")
    return _REGISTRY[pipeline_id]


def available() -> list[Pipeline]:
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def for_source(platform: str) -> list[Pipeline]:
    """Pipelines that can migrate *from* this platform.

    The cockpit detects the source and offers the valid targets, rather than presenting a
    dropdown pair whose combinations are mostly invalid.
    """
    return [p for p in available() if p.source_platform == platform]


def detect(root: str) -> tuple[str, dict]:
    """Ask every registered source adapter what this codebase is.

    Returns `(platform, report)` for the most confident acceptable answer, or `("", report)`
    when nothing recognises it — which is a refusal, not a default. Guessing a platform
    here would start a migration that was never going to work.
    """
    best, best_report, best_conf = "", {}, -1.0
    for p in available():
        try:
            report = p.source.detect(root)
        except Exception as e:                          # an adapter must never break detection
            report = {"verdict": "reject", "summary": f"{p.source_platform}: {e}"}
        conf = float(report.get("confidence") or 0)
        if report.get("verdict") != "reject" and conf > best_conf:
            best, best_report, best_conf = p.source_platform, report, conf
    return best, (best_report or {"verdict": "reject",
                                  "summary": "no registered source adapter recognised this codebase"})


def default_pipeline() -> Pipeline:
    """The shipped path. What an unqualified run means."""
    for p in available():
        if p.shipped:
            return p
    if not _REGISTRY:
        raise RuntimeError("no pipelines registered")
    return available()[0]


def resolve(root: str = "", pipeline_id: str = "") -> Pipeline:
    """Which pipeline should run: an explicit id, else detection, else the shipped default."""
    if pipeline_id:
        return get(pipeline_id)
    if root:
        platform, _ = detect(root)
        matches = for_source(platform) if platform else []
        if len(matches) == 1:
            return matches[0]
        # More than one target for a source is a question for the user, not a coin flip.
        if len(matches) > 1:
            raise ValueError(
                f"{platform} can migrate to "
                + " or ".join(m.target_platform for m in matches)
                + " — choose one with --pipeline")
    return default_pipeline()


def _register_builtins() -> None:
    """Import the shipped adapters. Deferred so importing this module stays cheap."""
    if _REGISTRY:
        return
    from src.adapters import hybris_source, salesforce_target
    register(Pipeline(
        id="hybris->salesforce",
        source=hybris_source.ADAPTER,
        target=salesforce_target.ADAPTER,
        label="SAP Hybris → Salesforce",
        knowledge_pack="hybris_to_salesforce",
        shipped=True,
    ))


def ensure_registered() -> None:
    _register_builtins()
