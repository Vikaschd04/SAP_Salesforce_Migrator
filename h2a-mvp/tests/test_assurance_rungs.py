"""How strongly the output was actually checked. [3.9]

Verification used to be a boolean. That worked while there was one target and it lent us
a free compiler; it stops working the moment a second target cannot be compiled at all,
because "not verified" then covers two very different situations — a Salesforce run where
nobody asked, and a Hybris run where verification is *not available*.

Giving those one word misleads in the direction that flatters us, which is the direction
that matters.
"""

import pytest

from src import assurance


def test_the_ladder_is_ordered():
    assert assurance.ORDER == ("none", "static", "typechecked", "compiled", "replayed")


def test_typechecked_sits_below_compiled_and_says_why():
    """A real compiler against a stand-in API surface catches strictly more than parsing
    and strictly less than the platform's own build — and where the stand-in is wrong it
    accepts wrong code just as confidently. That caveat is the rung's whole point. [1.37]"""
    claim, limit = assurance.CLAIMS[assurance.TYPECHECKED]
    assert assurance.ORDER.index(assurance.TYPECHECKED) < assurance.ORDER.index(
        assurance.COMPILED)
    assert "not {platform} itself" in claim
    assert "accepts wrong code" in limit
    assert "not yet as evidence it builds" in limit


def test_at_least_compares_by_strength():
    assert assurance.at_least({"rung": "compiled"}, "static")
    assert not assurance.at_least({"rung": "static"}, "compiled")
    assert assurance.at_least({"rung": "replayed"}, "replayed")


def test_an_unknown_rung_defaults_down_not_up():
    """Defaulting up would let a typo promote a claim."""
    assert assurance.rung_of({"rung": "verified-ish"}) == "none"
    assert assurance.rung_of(None) == "none"
    assert assurance.rung_of({}) == "none"


def test_a_legacy_boolean_result_means_compiled_and_no_more():
    """Results predating the ladder said yes/no. Yes never meant behaviour was checked."""
    assert assurance.rung_of({"verified": True}) == "compiled"
    assert assurance.rung_of({"ran": True, "success": True}) == "compiled"
    assert assurance.rung_of({"ran": True, "success": False}) == "none"


def test_every_rung_states_what_it_does_not_establish():
    """The limit is the more important half. A claim with no limit invites the reader to
    supply their own, and they will supply a generous one."""
    for rung in assurance.ORDER:
        d = assurance.describe({"rung": rung}, platform="X", language="Y")
        assert d["claim"] and d["limit"]
    assert "says nothing about whether it behaves" in \
        assurance.describe({"rung": "compiled"})["limit"]
    assert "No compiler ran" in assurance.describe({"rung": "static"})["limit"]


def test_the_claim_names_the_running_platform():
    d = assurance.describe({"rung": "compiled"}, platform="SAP Hybris", language="Java")
    assert "SAP Hybris" in d["claim"]
    assert "Salesforce" not in d["claim"]


# ── what each target reports ──────────────────────────────────────────────────

def test_a_target_with_no_oracle_reports_none_rather_than_failure():
    """"Verification is not available here" is not the same as "verification failed"."""
    from src.adapters.hybris_target import ADAPTER

    r = ADAPTER.verify(None, {}, log=lambda *a, **k: None)
    assert r["rung"] == "none"
    assert r["ran"] is False
    assert "no hosted compile oracle" in r["message"]


def test_running_the_generated_tests_is_a_higher_rung_than_compiling():
    """A dry-run deploy compiles. Only running the tests touches behaviour."""
    from src import assurance as a

    assert a.ORDER.index(a.REPLAYED) > a.ORDER.index(a.COMPILED)


# ── the contract ──────────────────────────────────────────────────────────────

def _bb():
    from src.agentic.blackboard import Blackboard

    bb = Blackboard("in", "out")
    bb.approvals = []
    return bb


def test_the_signoff_reports_the_rung_and_its_limit():
    from src.signoff import build_signoff

    c = build_signoff(_bb(), verified={"rung": "static"})
    assert c["assurance"]["rung"] == "static"
    assert any("statically checked, not compiled" in x for x in c["caveats"])


def test_only_the_top_rung_escapes_a_caveat():
    from src.signoff import build_signoff

    top = build_signoff(_bb(), verified={"rung": "replayed"})
    assert not any("was compiled by" in x for x in top["caveats"])
    for lower in ("none", "static", "compiled"):
        c = build_signoff(_bb(), verified={"rung": lower})
        assert any(c["assurance"]["claim"] in x for x in c["caveats"]), lower
