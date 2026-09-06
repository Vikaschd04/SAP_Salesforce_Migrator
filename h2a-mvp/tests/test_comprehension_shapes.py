"""A model that answers differently must cost accuracy, never the run. [1.49]

Swapping the provider to a different gateway found this in ten minutes: the comprehension
schema declares `business_rules` as a list of strings, one model answered with a list of
objects, nothing validated it, and the dicts travelled untouched as far as the Planner's
`", ".join(rules)` — which raised `TypeError` and took the whole migration down, after
eight API calls and ten minutes of comprehension work.

Every consumer downstream (the rule ledger, alignment, parity, blast radius, the LWC
generator) assumes strings. Coercing at the boundary fixes all of them at once; fixing the
`join` would have left the same landmine in each of the others.

"Three swappable AI providers" is on the front page of the PRD. It is only as true as the
narrowest assumption between the model and the report.
"""

import pytest

from src.comprehend import _as_strings, comprehend_class


# ── what the schema asks for ──────────────────────────────────────────────────

def test_a_list_of_strings_is_unchanged():
    assert _as_strings(["a", "b"]) == ["a", "b"]


def test_nothing_becomes_an_empty_list():
    assert _as_strings(None) == []
    assert _as_strings([]) == []


# ── what a model actually returned ────────────────────────────────────────────

def test_an_object_gives_up_its_rule():
    """The shape that broke the run."""
    assert _as_strings([{"rule": "Orders over 100 get 10% off"}]) == \
        ["Orders over 100 get 10% off"]


@pytest.mark.parametrize("field", ["rule", "description", "text", "statement",
                                   "detail", "summary", "condition", "name", "title"])
def test_the_rule_is_found_whatever_the_object_calls_it(field):
    assert _as_strings([{field: "the rule"}]) == ["the rule"]


def test_an_unrecognised_object_is_kept_whole_rather_than_dropped():
    """Losing a business rule is the failure this product exists to prevent. An odd shape
    is worth reporting awkwardly; it is not worth discarding."""
    got = _as_strings([{"when": "cart > 100", "then": "10% off"}])
    assert len(got) == 1
    assert "cart > 100" in got[0] and "10% off" in got[0]


def test_the_most_rule_shaped_field_wins_over_a_label():
    got = _as_strings([{"name": "DiscountRule", "description": "10% over 100"}])
    assert got == ["10% over 100"], "`name` labels the rule; `description` is the rule"


# ── other ways a model wanders off the schema ─────────────────────────────────

def test_a_bare_string_becomes_a_one_item_list():
    assert _as_strings("just one rule") == ["just one rule"]


def test_a_bare_object_becomes_a_one_item_list():
    assert _as_strings({"rule": "r"}) == ["r"]


def test_a_nested_list_is_flattened_to_text():
    assert _as_strings([["a", "b"]]) == ["a b"]


def test_a_number_is_kept_as_text():
    assert _as_strings([42]) == ["42"]


def test_a_null_in_the_list_is_dropped_not_stringified():
    """`str(None)` is the word "None", which reads in a report as a rule that says
    nothing — worse than an absent rule, because it is counted."""
    assert _as_strings(["a", None, "b"]) == ["a", "b"]


def test_blank_entries_are_dropped():
    assert _as_strings(["a", "", "   "]) == ["a"]


# ── the boundary itself ───────────────────────────────────────────────────────

def test_every_list_field_is_normalised(monkeypatch):
    """Not just `business_rules`. The same model returned objects there; nothing says the
    next one will not do it in `queries` or `migration_risks`."""
    import src.comprehend as mod

    monkeypatch.setattr(mod, "call_structured", lambda *a, **kw: {
        "parsed": {"purpose": "p",
                   "business_rules": [{"rule": "r"}],
                   "queries": [{"text": "SELECT 1"}],
                   "migration_risks": [{"description": "risky"}],
                   "inputs": None, "outputs": ["o"],
                   "side_effects": [{"detail": "writes"}],
                   "dependencies": [{"name": "Dep"}]},
        "content": "", "provider": "x", "model": "m",
        "prompt_tokens": 0, "completion_tokens": 0})

    got = comprehend_class({"class_name": "C", "layer": "Service", "source": "x",
                            "methods": [], "referenced_types": []})
    for key in ("business_rules", "queries", "migration_risks", "inputs", "outputs",
                "side_effects", "dependencies"):
        assert all(isinstance(x, str) for x in got[key]), f"{key} leaked a non-string"
    assert got["business_rules"] == ["r"]
    assert got["queries"] == ["SELECT 1"]


def test_the_planner_can_join_what_comprehension_returns(monkeypatch):
    """The exact call that raised: `", ".join(rules)` at planner.py:186."""
    import src.comprehend as mod

    monkeypatch.setattr(mod, "call_structured", lambda *a, **kw: {
        "parsed": {"purpose": "p", "business_rules": [{"rule": "a"}, {"rule": "b"}]},
        "content": "", "provider": "x", "model": "m",
        "prompt_tokens": 0, "completion_tokens": 0})
    got = comprehend_class({"class_name": "C", "layer": "Service", "source": "x",
                            "methods": [], "referenced_types": []})
    assert ", ".join(got["business_rules"]) == "a, b"
