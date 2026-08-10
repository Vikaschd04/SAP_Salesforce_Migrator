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


def set_overrides(*, provider: str | None = None, model: str | None = None,
                  api_key: str | None = None, cost_cap: float | None = None) -> None:
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


def provider_override() -> str | None:
    return _provider.get()


def model_override() -> str | None:
    return _model.get()


def api_key_override() -> str | None:
    return _api_key.get()


def cost_cap_override() -> float | None:
    return _cost_cap.get()


def propagate(fn):
    """Wrap `fn` so a pool worker sees the submitting run's overrides.

    Without this the override is invisible to every parallel LLM call — which is most
    of them — and a concurrent run would quietly fall back to the process default.

    Note this copies the *values*, not the Context object. A single Context cannot be
    entered twice, and `pool.map` runs the wrapped callable many times over, often
    concurrently — so `ctx.run(...)` raises "context is already entered". Re-setting the
    values at the top of each call is both simpler and safe against pool-thread reuse.
    """
    prov, mdl, key = _provider.get(), _model.get(), _api_key.get()

    def run(*a, **kw):
        if prov is not None:
            _provider.set(prov)
        if mdl is not None:
            _model.set(mdl)
        if key is not None:
            _api_key.set(key)
        return fn(*a, **kw)
    return run
