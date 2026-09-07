"""Per-test isolation for the run context. [1.63]

`runctx` holds the provider, model, credential, budget and pipeline for a run, in
ContextVars. ContextVars have no scoping of their own here: whatever a test sets stays set
for every test that follows in the same process.

That has now bitten twice. A test that pinned a pipeline to check a prompt broke eight
provenance tests that pass in isolation; a test that *ran a migration* — which pins one as
a side effect — broke twenty-four. Both times the failures pointed at innocent code and
the diagnosis cost more than the fix.

So it is handled once, here, for every test rather than remembered in each. A test that
wants a pipeline pinned still pins it; it simply cannot leave it pinned for anyone else.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_run_context():
    from src import runctx

    saved = {name: var.get() for name, var in (
        ("provider", runctx._provider), ("model", runctx._model),
        ("api_key", runctx._api_key), ("cost_cap", runctx._cost_cap),
        ("pipeline", runctx._pipeline_id),
    )}
    yield
    runctx._provider.set(saved["provider"])
    runctx._model.set(saved["model"])
    runctx._api_key.set(saved["api_key"])
    runctx._cost_cap.set(saved["cost_cap"])
    runctx._pipeline_id.set(saved["pipeline"])
