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

    def emit(self, output_dir: str, artifacts: list, data_model, config: dict) -> list:
        """Write the code package in this platform's own layout. Returns paths created.

        The layout is the platform's, not the pipeline's: Salesforce wants
        `force-app/main/default/classes`, a Hybris extension wants
        `bin/custom/<ext>/src/...`. Nothing above this method should know which.

        `data_model` is an `ir.DataModel` rather than a bare list, because emitting a
        package can need relations and enums as well as types — a Salesforce target
        happens to need only the types today.
        """

    def validate(self, code: str, filename: str, schema: dict, config: dict) -> list:
        """Objective checks for this platform — what a linter would catch, no model call.

        Apex means governor limits and schema-grounded SOQL; Java means imports resolving
        and no FlexibleSearch in a loop. Same question, different answers per platform.
        """

    def verify(self, request: "VerifyRequest", config: dict, log=print) -> dict:
        """Ask the oracle whether this output is real.

        Returns `{"ran": False, ...}` when there is no oracle to ask — which is a fact
        about the platform, not a failure, and the sign-off contract reports the
        difference rather than blurring it.
        """


@dataclass
class VerifyRequest:
    """Everything a target needs to ask its oracle whether the output is real.

    A request object rather than a widening parameter list, because what an oracle needs
    differs by platform and the difference is not cosmetic. Salesforce needs the generated
    artifacts, the SObject schema and the method signatures so its self-heal loop can
    rewrite a class and redeploy. A Hybris target will instead need the path to a licensed
    platform distribution and a Gradle invocation. Neither is a subset of the other, so a
    shared signature would be a union of two platforms' needs — which is exactly the
    coupling the adapters exist to remove.
    """
    output_dir: str
    artifacts: list = field(default_factory=list)
    schema: dict = field(default_factory=dict)
    signatures: list = field(default_factory=list)
    source_corpus: str = ""
    offline: bool = False


@dataclass(frozen=True)
class Pipeline:
    id: str                       # "hybris->salesforce"
    source: object                # SourceAdapter
    target: object                # TargetAdapter
    label: str = ""
    knowledge_pack: str = ""      # directory of prompts/mappings/RAG for this pair
    shipped: bool = False         # is this the path customers already run?
    #: Per-pair cost/effort constants for the forecast. Registered here rather than in
    #: `forecast.py` because they are measurements *about a pair*, and the assurance layer
    #: may not hold platform knowledge. None means the neutral default. [4.3]
    forecast_profile: object = None

    @property
    def implemented(self) -> bool:
        """Can this pipeline actually run a migration?

        A registered-but-scaffolded pipeline exercises detection, resolution and the pack
        machinery without being able to convert anything. Registering it is how the
        architecture is proven to hold two platforms; letting it *run* would produce a
        migration that reports success and emits nothing.
        """
        return (getattr(self.source, "implemented", True)
                and getattr(self.target, "implemented", True))

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


def identify(root: str) -> dict:
    """What this codebase is, and which migrations are available for it. [4.1]

    The single question a surface needs to ask before offering anything. Until now every
    surface asked `preflight.inspect`, which answers *"is this Hybris?"* — so a Magento
    project was rejected as "not a Hybris project" by a tool that had an adapter capable
    of recognising it precisely.

    Three outcomes, and they are genuinely different answers rather than degrees of one:

        unrecognised   no adapter claims it. A refusal, not a default — guessing a
                       platform starts a migration that was never going to work.
        recognised     an adapter identifies it and no pipeline from it can run yet.
                       "We know exactly what this is and cannot migrate it" is a useful
                       thing to be told; "unidentified" is not.
        runnable       identified, with at least one target that can actually run.
    """
    # A surface calls this before anything else in the process has touched the registry.
    ensure_registered()
    platform, report = detect(root)
    if not platform:
        # Nothing claimed it. Report the most *specific* refusal rather than the generic
        # one: "nothing to migrate — no Java sources and no items.xml" tells someone who
        # uploaded the wrong folder what to do, and "no registered source adapter
        # recognised this codebase" tells them about our architecture.
        best = report
        for p in available():
            try:
                r = p.source.detect(root)
            except Exception:
                continue
            if float(r.get("confidence") or 0) > float(best.get("confidence") or 0) or (
                    not best.get("summary") and r.get("summary")):
                best = r
            elif r.get("blockers") and not best.get("blockers"):
                best = r
        return {"status": "unrecognised", "platform": "", "report": best,
                "pipelines": [],
                "summary": best.get("summary")
                or "No registered source adapter recognised this codebase."}

    options = []
    for p in for_source(platform):
        options.append({
            "id": p.id,
            "source": p.source_platform,
            "target": p.target_platform,
            "label": p.label or f"{p.source_platform} → {p.target_platform}",
            "implemented": p.implemented,
            "shipped": p.shipped,
            # What a run would be able to claim about its output, which belongs next to
            # the choice rather than in the report afterwards.
            "has_oracle": bool(getattr(p.target, "has_oracle", False)),
        })
    runnable = [o for o in options if o["implemented"]]

    return {
        "status": "runnable" if runnable else "recognised",
        "platform": platform,
        "report": report,
        "pipelines": options,
        "summary": report.get("summary", ""),
    }


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


def require_runnable(p: "Pipeline") -> "Pipeline":
    """Refuse to start a migration on a pipeline that cannot perform one.

    Fails at the moment a run is resolved, before any file is read or any token spent,
    and names what is missing. The alternative is a run that walks every stage, converts
    nothing, and reports a clean ledger over an empty output.
    """
    if not p.implemented:
        missing = []
        if not getattr(p.source, "implemented", True):
            missing.append(f"{p.source_platform} source")
        if not getattr(p.target, "implemented", True):
            missing.append(f"{p.target_platform} target")
        raise NotImplementedError(
            f"{p.label} is registered but not implemented yet — the "
            f"{' and '.join(missing)} adapter(s) are scaffolds. "
            "See docs/V2_DELIVERY_PLAN.md phases 2 and 3.")
    return p


def current_target():
    """The target adapter for the run in progress, or None on the v1 path.

    Read from `runctx`, not from a passed argument, because the deepest callers — the
    Critic's objective floor and the Builder's repair loop — never see the Blackboard.
    Threading a pipeline id down to them would mean changing signatures that have nothing
    else to do with platforms.
    """
    from src import runctx
    pid = runctx.pipeline_id()
    if not pid:
        return None
    ensure_registered()
    return get(pid).target


def validate_artifact(code: str, filename: str, schema: dict,
                      config: dict | None = None) -> list:
    """Objective checks for the running pipeline's target platform.

    One function rather than the same three-line dance at four call sites — and the
    fallback keeps v1 calling the Salesforce validator directly, unchanged.
    """
    target = current_target()
    if target is not None:
        return target.validate(code, filename, schema, config or {})
    from src.validate import validate_all
    return validate_all(code, filename, schema)


def _register_builtins() -> None:
    """Import the shipped adapters. Deferred so importing this module stays cheap."""
    if _REGISTRY:
        return
    from src import forecast as _forecast
    from src.adapters import hybris_source, salesforce_target, adobe_source, hybris_target
    register(Pipeline(
        id="hybris->salesforce",
        source=hybris_source.ADAPTER,
        target=salesforce_target.ADAPTER,
        label="SAP Hybris → Salesforce",
        knowledge_pack="hybris_to_salesforce",
        shipped=True,
    ))
    # Registered while still scaffolded, on purpose: it is what proves detection,
    # resolution, pack loading and the purity rule work against two platforms rather than
    # one. `implemented` is False, so `require_runnable()` refuses to start a migration
    # with it — the architecture is exercised without anything being able to pretend.
    register(Pipeline(
        id="adobe->hybris",
        source=adobe_source.ADAPTER,
        target=hybris_target.ADAPTER,
        label="Adobe Commerce → SAP Hybris",
        knowledge_pack="adobe_to_hybris",
        # Not measured on PHP→Java. Carried over from the pair we have actually run, and
        # the forecast says so before it says the number. Two differences that are not
        # guesses: PHP is denser per token than Java, and a Magento `Model` holds business
        # logic where a Hybris one is generated from items.xml — sharing that label
        # understated review effort ninefold. [4.3]
        forecast_profile=_forecast.Profile(
            measured=False,
            basis="carried over from the Hybris→Salesforce pair; NOT measured on PHP→Java",
            chars_per_token=3.5,
            mechanical_layers={"DAO", "Helper", "Script"},
        ),
        shipped=False,
    ))


def ensure_registered() -> None:
    _register_builtins()
