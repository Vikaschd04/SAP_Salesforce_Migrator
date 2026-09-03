"""A dependency cycle is cut somewhere. Say where. [1.27]

A cycle has to be broken or nothing can be scheduled at all — the wavefront planner has
always done that, returning depth 0 for a domain already on the stack. Breaking it is not
the problem. Breaking it *silently* is: the domain that gets cut loose is built without its
dependency's signatures, so the Builder sees less than it otherwise would, and the
difference reaches the output as a weaker artifact with nothing attached to explain it.
"""

import pytest

from src.agentic.blackboard import Blackboard
from src.agentic.orchestrator import _domain_levels


def test_an_acyclic_graph_reports_no_cuts():
    levels, cuts = _domain_levels(["a", "b"], {"a": ["b"], "b": []})
    assert cuts == []
    assert levels == [["b"], ["a"]]


def test_a_cycle_is_still_scheduled():
    """The old behaviour, which was right: progress beats correctness of ordering when the
    ordering is impossible."""
    levels, _ = _domain_levels(["a", "b", "c"], {"a": ["b"], "b": ["c"], "c": ["a"]})
    assert sorted(d for lv in levels for d in lv) == ["a", "b", "c"]


def test_the_cut_names_both_ends():
    _, cuts = _domain_levels(["a", "b", "c"], {"a": ["b"], "b": ["c"], "c": ["a"]})
    assert len(cuts) == 1
    assert cuts[0] == {"domain": "c", "depends_on": "a"}


def test_a_two_domain_cycle_is_reported():
    _, cuts = _domain_levels(["a", "b"], {"a": ["b"], "b": ["a"]})
    assert cuts and {cuts[0]["domain"], cuts[0]["depends_on"]} == {"a", "b"}


def test_the_same_cycle_is_reported_once():
    """Depth is memoised and the graph is walked from every root; a cut reported per visit
    would put the same pairing in the document four times."""
    adj = {"a": ["b"], "b": ["a"], "c": ["a"], "d": ["a"]}
    _, cuts = _domain_levels(["a", "b", "c", "d"], adj)
    assert len(cuts) == 1


def test_two_separate_cycles_are_both_reported():
    adj = {"a": ["b"], "b": ["a"], "x": ["y"], "y": ["x"]}
    _, cuts = _domain_levels(["a", "b", "x", "y"], adj)
    assert len(cuts) == 2


def test_a_self_dependency_is_not_a_cycle():
    """A domain listing itself is noise in the adjacency, not a cycle to report."""
    _, cuts = _domain_levels(["a"], {"a": ["a"]})
    assert cuts == []


def test_the_contract_says_which_artifact_was_built_with_less():
    from src.signoff import build_signoff

    bb = Blackboard("in", "out")
    bb.approvals = []
    bb.cycle_cuts = [{"domain": "orders", "depends_on": "pricing"}]

    caveats = " ".join(build_signoff(bb)["caveats"])
    assert "`orders` and `pricing` depend on each other" in caveats
    assert "cut at `orders`" in caveats
    assert "check that artifact more closely" in caveats


def test_no_cycle_means_no_caveat():
    from src.signoff import build_signoff

    bb = Blackboard("in", "out")
    bb.approvals = []
    assert not any("depend on each other" in c for c in build_signoff(bb)["caveats"])
