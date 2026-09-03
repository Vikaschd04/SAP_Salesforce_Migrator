"""What `@Transactional` becomes, and when it becomes nothing. [1.21c]

The radar reported `@Transactional` and said to use a savepoint. That is right for one of
the two shapes and wrong for the other — and the other is the common one.

**Apex already has the transaction.** An uncaught exception from an entry point rolls the
whole request back, every DML statement, without a savepoint being set. So a method whose
rollback is driven purely by throwing needs none, and adding one is not free: each
`Database.setSavepoint()` spends one of the 150 DML statements the transaction is allowed.

A savepoint earns its place in exactly one shape — the method catches and carries on,
which is a partial rollback and has no other expression in Apex.
"""

import textwrap
from pathlib import Path

from src.adapters.java_transactions import CATCHES, THROWS, analyse, grounding_for

SERVICE = (Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris"
           / "core-customize/hybris/bin/custom/acmecore/src/com/acme/core/service/impl"
           / "DefaultOrderFulfilmentService.java")


def _wrap(body: str) -> str:
    return "public class T {\n" + textwrap.dedent(body) + "\n}"


def test_a_method_that_only_throws_needs_no_savepoint():
    src = _wrap("""
        @Transactional
        public void transition() {
            if (bad) { throw new IllegalStateException("no"); }
            modelService.save(order);
        }
        """)
    got = analyse(src)
    assert len(got) == 1 and got[0]["rollback"] == THROWS


def test_a_method_that_catches_needs_a_real_one():
    src = _wrap("""
        @Transactional
        public void transition() {
            try { modelService.save(order); }
            catch (final ModelSavingException e) { log.warn(e); }
        }
        """)
    assert analyse(src)[0]["rollback"] == CATCHES


def test_a_method_without_the_annotation_is_not_analysed():
    assert analyse(_wrap("public void plain() { modelService.save(o); }")) == []


def test_the_dml_in_the_method_is_counted():
    src = _wrap("""
        @Transactional
        public void f() { modelService.save(a); modelService.remove(b); }
        """)
    assert analyse(src)[0]["dml"] == 2


def test_unparseable_source_yields_nothing():
    assert analyse("not java {{{") == []


# ── the corpus ────────────────────────────────────────────────────────────────

def test_the_reference_method_is_the_throws_shape():
    got = analyse(SERVICE.read_text())
    assert [m["method"] for m in got] == ["transition"]
    assert got[0]["rollback"] == THROWS


def test_the_finding_says_a_savepoint_would_cost_a_dml_statement():
    from src.radar import scan

    hits = [f for f in scan(str(SERVICE.parents[5]))["findings"]
            if f["rule"] == "TRANSACTION_SHAPE"]
    assert len(hits) == 1
    assert "150 DML statements" in hits[0]["hazard"]
    assert hits[0]["severity"] == "medium", "not needing a savepoint is not a high risk"


def test_the_fix_warns_that_a_caller_can_turn_the_rollback_off():
    from src.radar import scan

    hit = [f for f in scan(str(SERVICE.parents[5]))["findings"]
           if f["rule"] == "TRANSACTION_SHAPE"][0]
    assert "does not swallow it" in hit["fix"]


def test_the_contradictory_rule_is_gone():
    """TRANSACTIONAL claimed a @Transactional method "will commit its earlier DML and then
    throw, leaving records half-written". That is true only if a caller catches — Apex
    rolls back the whole request on an uncaught exception — so the claim was wrong for the
    common shape and its advice was wrong with it."""
    from src.radar import scan

    assert not [f for f in scan(str(SERVICE.parents[5]))["findings"]
                if f["rule"] == "TRANSACTIONAL"]


# ── what the Builder is told ──────────────────────────────────────────────────

def test_the_builder_is_told_which_shape_it_is():
    """Left to the model, "translate @Transactional" reliably produces a savepoint."""
    block = grounding_for([SERVICE.read_text()])
    assert "without a savepoint" in block
    assert "spend one of the 150 DML statements for nothing" in block


def test_the_catching_shape_gets_the_savepoint_idiom():
    src = _wrap("""
        @Transactional
        public void f() { try { modelService.save(a); } catch (final Exception e) { } }
        """)
    block = grounding_for([src])
    assert "Database.setSavepoint()" in block
    assert "does not restore governor counters" in block


def test_a_source_with_no_transactions_contributes_nothing():
    assert grounding_for(["class Plain { void f() {} }"]) == ""


def test_the_two_shapes_are_not_the_same_severity():
    """The corpus method drops from high to medium because it needs nothing done. The
    catching shape stays high — a partial rollback silently becomes a full one."""
    from src.adapters.java_transactions import findings

    throws = _wrap("""
        @Transactional
        public void f() { modelService.save(a); }
        """)
    catches = _wrap("""
        @Transactional
        public void f() { try { modelService.save(a); } catch (final Exception e) { } }
        """)
    assert findings(throws, "A.java", "A", throws.splitlines())[0]["severity"] == "medium"
    assert findings(catches, "A.java", "A", catches.splitlines())[0]["severity"] == "high"


def test_the_catching_shape_warns_that_rollback_leaves_the_dml_count_spent():
    from src.adapters.java_transactions import findings

    src = _wrap("""
        @Transactional
        public void f() { try { modelService.save(a); } catch (final Exception e) { } }
        """)
    fix = findings(src, "A.java", "A", src.splitlines())[0]["fix"]
    assert "does **not** restore governor counters" in fix
