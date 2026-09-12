"""
runctx.py — per-run settings that must not leak between concurrent runs.

The web backend used to select a provider by writing `os.environ["H2A_PROVIDER"]`,
which is process-global. With two migrations in flight that is a race: run B's
provider silently becomes run A's, and a mock run on a locked-down laptop could start
making real API calls. The old fix was a process-wide lock that allowed exactly one
migration at a time — correct, but it capped the product at a single user.

A `ContextVar` fixes the cause instead. Each run sets its own overrides; lookups see
their own run's value; nothing is shared. The one catch is that a `ContextVar` is NOT
inherited by `ThreadPoolExecutor` workers, and the engine does its LLM work on exactly
those — so `propagate()` captures the caller's context for a worker to re-enter.

Precedence is deliberate: an explicit per-run override beats the environment, which
beats config.yaml. The CLI and the extension set nothing here, so they keep reading the
environment exactly as before.
"""

from __future__ import annotations

import contextvars

_provider: contextvars.ContextVar[str | None] = contextvars.ContextVar("h2a_provider", default=None)
_model: contextvars.ContextVar[str | None] = contextvars.ContextVar("h2a_model", default=None)
# A tenant's own provider credential, so concurrent runs bill their own accounts.
_api_key: contextvars.ContextVar[str | None] = contextvars.ContextVar("h2a_api_key", default=None)
# A spend ceiling for this run alone. Per-run rather than global because concurrent runs
# belong to different tenants, and one tenant's budget must not throttle another's.
_cost_cap: contextvars.ContextVar[float | None] = contextvars.ContextVar("h2a_cost_cap", default=None)
# Which migration this run is. Read by `packs` to resolve prompts, mappings and RAG docs
# for the right platform pair. Per-run rather than global for the same reason as the
# credential: two concurrent runs can be different migrations, and a module-level variable
# would let one silently borrow the other's prompts.
_pipeline_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("h2a_pipeline_id", default=None)


def set_overrides(*, provider: str | None = None, model: str | None = None,
                  api_key: str | None = None, cost_cap: float | None = None,
                  pipeline_id: str | None = None) -> None:
    """Pin provider/model/credential/budget for this run (and anything it spawns via
    propagate)."""
    if provider:
        _provider.set(provider)
    if model:
        _model.set(model)
    if api_key:
        _api_key.set(api_key)
    if cost_cap is not None:
        _cost_cap.set(float(cost_cap))
    if pipeline_id:
        _pipeline_id.set(pipeline_id)


def provider_override() -> str | None:
    return _provider.get()


def model_override() -> str | None:
    return _model.get()


def api_key_override() -> str | None:
    return _api_key.get()


def cost_cap_override() -> float | None:
    return _cost_cap.get()


def pipeline_id() -> str | None:
    return _pipeline_id.get()


#: Every ContextVar this module owns, so `propagate()` cannot be partially correct.
#:
#: It was, for a long time, and the cost was high. `propagate` listed provider, model and
#: credential by hand and silently omitted `pipeline_id` and `cost_cap` — so inside every
#: `_map_parallel` worker (which is where *all* comprehension and generation happens, at
#: the default concurrency of 8) the run had no identity and no budget:
#:
#:   * `packs.pack_name()` fell back to the shipped pack, so an Adobe→Hybris run was given
#:     the Salesforce `generate`, `generate_system`, `comprehend` and `repair` prompts and
#:     the Salesforce `mappings.yaml`. The first line the model read was "Translate the
#:     following SAP Hybris class into Salesforce Apex", in a PHP→Java migration.
#:   * `pipeline.current_target()` returned None, so the Critic's objective floor and the
#:     Builder's repair loop ran the *Apex* validator over generated Java — raising
#:     `ERROR java_syntax_leak: Java 'package' statement found` on a correct Java package
#:     declaration, which then drove a frontier-model repair round against every artifact
#:     and left each one `needs_review` for a reason that did not exist.
#:   * `cost_cap_override()` returned None, so a per-run spend ceiling was not enforced on
#:     the calls that spend nearly all of the money.
#:
#: Enumerating the vars in one place is the fix, not a longer hand-written list: a new
#: per-run variable is propagated because it is a per-run variable, and cannot be
#: forgotten at the one call site that matters. [4.6]
_VARS = (_provider, _model, _api_key, _cost_cap, _pipeline_id)


def propagate(fn):
    """Wrap `fn` so a pool worker sees the submitting run's overrides.

    Without this the override is invisible to every parallel LLM call — which is most
    of them — and a concurrent run would quietly fall back to the process default.

    Note this copies the *values*, not the Context object. A single Context cannot be
    entered twice, and `pool.map` runs the wrapped callable many times over, often
    concurrently — so `ctx.run(...)` raises "context is already entered". Re-setting the
    values at the top of each call is both simpler and safe against pool-thread reuse.
    """
    captured = [(v, v.get()) for v in _VARS]

    def run(*a, **kw):
        for var, value in captured:
            if value is not None:
                var.set(value)
        return fn(*a, **kw)
    return run
