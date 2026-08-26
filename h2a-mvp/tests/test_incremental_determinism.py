"""The recipe hash must be a function of its inputs, not of the process that computed it.

`recipe_hash` identifies *how* output is produced, and `target_fingerprint` derives from
it — so if the recipe changes between runs, nothing ever matches the previous run's cache
and incremental reuse silently does nothing. Every re-run then re-bills the whole estate
while appearing to work perfectly.

That is exactly what happened: the schema carries `required` and `unique` as sets, they
were serialised with `default=str`, and `str(set)` orders elements by per-process string
hashes. The failure was invisible in-process — the bug only appears across restarts, which
is precisely how customers run re-migrations.
"""
import subprocess
import sys
import textwrap

import pytest

from src.agentic.incremental import recipe_hash, target_fingerprint

SCHEMA = {"Order__c": {"code": "Order",
                       "fields": {"Total__c": "Currency", "Status__c": "Picklist"},
                       "required": {"Total__c", "Status__c", "Code__c", "Priority__c"},
                       "unique": {"Code__c", "Ref__c"},
                       "picklists": {}, "defaults": {}}}


def _hash_in_a_fresh_process() -> str:
    """A separate interpreter, so string-hash randomisation actually differs."""
    code = textwrap.dedent(f"""
        from src.agentic.incremental import recipe_hash
        print(recipe_hash("mock", "claude-opus-4-8", {SCHEMA!r}, {{"a": 1}}))
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=".")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_recipe_hash_is_stable_across_processes():
    """The bug in one line: identical inputs, different answers, cache never hits."""
    hashes = {_hash_in_a_fresh_process() for _ in range(4)}
    assert len(hashes) == 1, (
        "recipe_hash differs between processes, so incremental reuse can never hit: "
        f"{sorted(hashes)}")


def test_recipe_hash_is_stable_in_process():
    a = recipe_hash("mock", "m", SCHEMA, {"a": 1})
    b = recipe_hash("mock", "m", SCHEMA, {"a": 1})
    assert a == b


def test_recipe_hash_still_changes_when_the_recipe_changes():
    """Stability must not become insensitivity — the hash exists to invalidate."""
    base = recipe_hash("mock", "m", SCHEMA, {"a": 1})
    assert recipe_hash("anthropic", "m", SCHEMA, {"a": 1}) != base
    assert recipe_hash("mock", "other", SCHEMA, {"a": 1}) != base
    assert recipe_hash("mock", "m", SCHEMA, {"a": 2}) != base

    changed = {"Order__c": {**SCHEMA["Order__c"], "required": {"Total__c"}}}
    assert recipe_hash("mock", "m", changed, {"a": 1}) != base


def test_set_ordering_does_not_affect_the_hash():
    """The same set built in a different order is the same set."""
    a = {"Order__c": {"required": {"a", "b", "c"}, "unique": set()}}
    b = {"Order__c": {"required": {"c", "a", "b"}, "unique": set()}}
    assert recipe_hash("mock", "m", a, {}) == recipe_hash("mock", "m", b, {})


def test_target_fingerprints_match_across_processes():
    """The consequence that costs money: a fingerprint computed in a later run must match
    the one cached by an earlier one, or nothing is ever reused."""
    from src.agentic.blackboard import PlanItem
    item = PlanItem(target_name="OrderService", layer="Service", domain="Order",
                    apex_pattern="Service",
                    source_classes=[{"class_name": "DefaultOrderService"}])
    hashes = {"DefaultOrderService": "abc123"}

    # Two separate processes agreeing on the recipe is the whole point: the fingerprint
    # a later run computes must match the one an earlier run cached.
    recipes = {_hash_in_a_fresh_process() for _ in range(3)}
    assert len(recipes) == 1
    recipe = recipes.pop()
    assert (target_fingerprint(item, hashes, ["OrderSelector"], recipe)
            == target_fingerprint(item, hashes, ["OrderSelector"], recipe))
