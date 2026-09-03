"""A getter's result dereferenced without a guard. [1.30]

Split out of 1.17 for a reason that still holds: deciding whether a getter *can* return
null needs type resolution across files, and a regex over call sites is noisy in both
directions. A noisy rule gets ignored, which is worse than no rule.

So this asks a narrower question the AST answers exactly — is the result dereferenced in a
method that never checks it against null? Most of these tests are the *guarded* shapes,
because a rule that fires on correct code is the failure mode being avoided, and the
reference corpus has four of them within a few lines of the unguarded ones.
"""

import textwrap
from pathlib import Path

import pytest

from src.adapters.java_nullability import find_unguarded

CORE = (Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris"
        / "core-customize/hybris/bin/custom/acmecore/src/com/acme/core")


def _wrap(body: str) -> str:
    return "public class T {\n" + textwrap.dedent(body) + "\n}"


# ── the shapes that must stay silent ──────────────────────────────────────────

def test_a_ternary_guard_is_a_guard():
    src = _wrap("""
        void f() {
            total = order.getTotalPrice() == null ? BigDecimal.ZERO
                  : BigDecimal.valueOf(order.getTotalPrice().doubleValue());
        }
        """)
    assert find_unguarded(src) == []


def test_a_short_circuit_guard_is_a_guard():
    src = _wrap("""
        void f() {
            if (order.getCode() == null || order.getCode().trim().isEmpty()) { return; }
        }
        """)
    assert find_unguarded(src) == []


def test_a_not_null_guard_counts_too():
    src = _wrap("""
        void f() {
            if (order.getUser() != null) { name = order.getUser().getUid(); }
        }
        """)
    assert find_unguarded(src) == []


def test_a_guard_later_in_the_method_still_counts():
    """Tracking whether the check dominates the use needs flow analysis, and being wrong
    about that produces false positives on correct code — the direction that gets a rule
    ignored."""
    src = _wrap("""
        void f() {
            x = order.getUser().getUid();
            if (order.getUser() == null) { return; }
        }
        """)
    assert find_unguarded(src) == []


def test_a_guard_in_a_different_method_does_not_count():
    src = _wrap("""
        void guarded() { if (order.getUser() == null) { return; } }
        void other() { x = order.getUser().getUid(); }
        """)
    hits = find_unguarded(src)
    assert [h["method"] for h in hits] == ["other"]


def test_a_getter_that_is_not_dereferenced_is_not_a_finding():
    """`getX()` on its own cannot throw. Only the call *into* its result can."""
    assert find_unguarded(_wrap("void f() { x = order.getTotalPrice(); }")) == []


def test_a_non_getter_call_is_not_a_finding():
    assert find_unguarded(_wrap("void f() { x = service.calculate().doubleValue(); }")) == []


def test_is_and_has_accessors_are_not_getters():
    """They return primitives in practice, so they cannot produce the null in question."""
    assert find_unguarded(_wrap("void f() { x = o.isActive().toString(); }")) == []


def test_unparseable_source_yields_nothing_rather_than_raising():
    assert find_unguarded("not java at all {{{") == []


# ── the shapes that must fire ─────────────────────────────────────────────────

def test_an_unguarded_dereference_is_found():
    src = _wrap("void f() { final OrderModel o = event.getProcess().getOrder(); }")
    hits = find_unguarded(src)
    assert len(hits) == 1
    assert hits[0]["expression"] == "event.getProcess().getOrder()"
    assert hits[0]["method"] == "f"


def test_the_finding_carries_a_usable_line():
    src = _wrap("""
        void f() {
            int a = 1;
            x = order.getUser().getUid();
        }
        """)
    assert find_unguarded(src)[0]["line"] > 1


# ── against the real corpus ───────────────────────────────────────────────────

def test_the_corpus_guarded_cases_do_not_fire():
    """Four real guards sit within a few lines of the unguarded ones. Flagging any of them
    would make this rule the kind nobody reads."""
    listener = (CORE / "event" / "OrderPlacedEventListener.java").read_text()
    flagged = {h["expression"] for h in find_unguarded(listener)}
    assert not any("getTotalPrice" in e for e in flagged)
    assert not any("getPointsBalance" in e for e in flagged)


def test_the_corpus_unguarded_cases_do_fire():
    listener = (CORE / "event" / "OrderPlacedEventListener.java").read_text()
    assert any("getProcess" in h["expression"] for h in find_unguarded(listener))


def test_radar_reports_them_with_a_runtime_explanation():
    from src.radar import scan

    hits = [f for f in scan(str(CORE.parents[3]))["findings"]
            if f["rule"] == "UNGUARDED_NULL"]
    assert len(hits) == 3
    assert all(h["severity"] == "high" for h in hits)
    assert "at *runtime*" in hits[0]["hazard"]
    assert "deploys cleanly" in hits[0]["hazard"]


def test_the_fix_points_at_the_evidence_that_would_settle_it():
    from src.radar import scan

    hit = [f for f in scan(str(CORE.parents[3]))["findings"]
           if f["rule"] == "UNGUARDED_NULL"][0]
    assert 'optional="false"' in hit["fix"]
