"""Item 1.8 — the Planner asks the target adapter for candidate targets.

Before this, `PlannerAgent` imported `generate.plan_targets` directly, which knows about
Apex, Selectors and LWC. That hard-wired the Planner to one target platform: adding a
Hybris target would have meant editing the Planner itself.

The v1 path is unchanged and stays reachable. The point of these tests is to prove the v2
path is *actually* taken — a golden-harness pass would look identical if v2 silently fell
back to v1, so "output matches" is necessary but not sufficient evidence.
"""
import pytest

from src.agentic.planner import _candidate_targets

CLASSES = [
    {"class_name": "OrderDao", "layer": "DAO", "source": "public class OrderDao {}"},
    {"class_name": "DefaultOrderService", "layer": "Service",
     "source": "public class DefaultOrderService {}"},
]


class _BB:
    def __init__(self, pipeline_id=""):
        self.pipeline_id = pipeline_id


def _spy_on_adapter(monkeypatch):
    """Count calls to the target adapter without changing what it returns."""
    import src.adapters.salesforce_target as st
    calls = []
    original = st.SalesforceTarget.plan

    def spy(self, units, config):
        calls.append(len(units))
        return original(self, units, config)

    monkeypatch.setattr(st.SalesforceTarget, "plan", spy)
    return calls


def test_v2_routes_through_the_target_adapter(monkeypatch):
    calls = _spy_on_adapter(monkeypatch)
    targets = _candidate_targets(_BB("hybris->salesforce"), CLASSES)
    assert calls == [2], "the target adapter was not consulted on the v2 path"
    assert targets, "the adapter returned no candidate targets"


def test_v1_does_not_touch_the_adapter(monkeypatch):
    """The shipped path must keep calling plan_targets directly — no new indirection."""
    calls = _spy_on_adapter(monkeypatch)
    targets = _candidate_targets(_BB(""), CLASSES)
    assert calls == [], "the v1 path should not consult the adapter"
    assert targets


def test_both_paths_produce_identical_targets(monkeypatch):
    """The adapter delegates to the same function, so routing cannot change the plan.
    If this ever fails, the seam has altered behaviour — which it is not allowed to do."""
    v2 = _candidate_targets(_BB("hybris->salesforce"), CLASSES)
    v1 = _candidate_targets(_BB(""), CLASSES)
    assert v2 == v1


def test_planner_does_not_import_plan_targets_at_module_level():
    """The Planner must not know its target platform. A module-level import of
    `generate.plan_targets` is exactly that knowledge, so it is asserted absent —
    the v1 fallback imports it lazily, inside the branch that needs it."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parent.parent / "src/agentic/planner.py"
    header = src.read_text().split("class PlannerAgent")[0]
    module_level = [
        ln for ln in header.splitlines()
        if ln.startswith("from src.generate import") or ln.startswith("import src.generate")
    ]
    assert not module_level, f"planner.py imports generate at module level: {module_level}"


def test_it_works_without_the_orchestrator_registering_first(monkeypatch):
    """The Planner is reachable by routes that never call ensure_registered().

    An earlier draft looked up the pipeline without ensuring the registry was populated
    and raised `KeyError: unknown pipeline` — caught by exercising this directly rather
    than only through a full run, where the orchestrator happens to register first.
    """
    import src.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "_REGISTRY", {})       # simulate a cold registry
    targets = _candidate_targets(_BB("hybris->salesforce"), CLASSES)
    assert targets, "a cold registry must self-populate rather than raise"


def test_an_unknown_pipeline_id_still_fails_loudly(monkeypatch):
    """Self-populating the registry must not become 'silently accept anything'. A
    pipeline id that does not exist is a bug, and must not fall back to v1 quietly."""
    with pytest.raises(KeyError, match="unknown pipeline"):
        _candidate_targets(_BB("magento->sap"), CLASSES)
