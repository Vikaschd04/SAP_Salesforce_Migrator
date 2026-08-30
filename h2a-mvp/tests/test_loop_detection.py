"""SOQL/DML in a loop must be caught wherever it is written, not only where it is
conventionally formatted.

The detector walked each line, updated a brace stack, and *then* asked whether it was
inside a loop. A loop that opened and closed on the same line pushed its frame and popped
it again before that question was asked, so the query was invisible to the rule whose
whole purpose is to catch it:

    for (String c : codes) { Product__c p = [SELECT Id FROM Product__c]; }

Legal Apex, a governor limit breached at real volume, and silently passed. Found while
routing validation through the target adapter — the fixture written to exercise the
routing did not trip the rule, which is how the gap surfaced.
"""
import pytest

from src.validate import validate_tier1


def _rules(code: str) -> list:
    return [i["rule"] for i in validate_tier1(code, "A.cls")]


# ── the hazards, however they are written ────────────────────────────────────

def test_multi_line_loop_body():
    code = """public class A {
        public void m(List<String> cs) {
            for (String c : cs) {
                Product__c p = [SELECT Id FROM Product__c];
            }
        }
    }"""
    assert "soql_in_loop" in _rules(code)


def test_single_line_loop_body():
    """The regression: opened and closed on one line."""
    code = """public class A {
        public void m(List<String> cs) {
            for (String c : cs) { Product__c p = [SELECT Id FROM Product__c]; }
        }
    }"""
    assert "soql_in_loop" in _rules(code)


def test_brace_less_single_statement_loop():
    """`for (...) statement;` never pushes a brace frame at all."""
    code = """public class A {
        public void m(List<String> cs) {
            for (String c : cs) Product__c p = [SELECT Id FROM Product__c];
        }
    }"""
    assert "soql_in_loop" in _rules(code)


def test_while_loop_counts_too():
    code = """public class A {
        public void m() {
            while (hasMore) { Product__c p = [SELECT Id FROM Product__c]; }
        }
    }"""
    assert "soql_in_loop" in _rules(code)


def test_dml_in_a_single_line_loop():
    code = """public class A {
        public void m(List<Account> accs) {
            for (Account a : accs) { insert a; }
        }
    }"""
    assert "dml_in_loop" in _rules(code)


# ── and no false positives, which is what keeps the rule trusted ─────────────

def test_soql_after_the_loop_closes_on_the_same_line():
    """Position matters. A rule that cries wolf gets muted, which costs more than the
    rule is worth."""
    code = """public class A {
        public void m(List<String> cs) {
            for (String c : cs) { doThing(c); }
            Product__c p = [SELECT Id FROM Product__c];
        }
    }"""
    assert "soql_in_loop" not in _rules(code)


def test_soql_outside_any_loop():
    code = """public class A {
        public void m() {
            Product__c p = [SELECT Id FROM Product__c];
        }
    }"""
    assert "soql_in_loop" not in _rules(code)


def test_bulkified_query_before_a_loop_is_fine():
    """The pattern the rule exists to encourage must not itself be flagged."""
    code = """public class A {
        public void m(Set<String> codes) {
            List<Product__c> ps = [SELECT Id FROM Product__c WHERE Code__c IN :codes];
            for (Product__c p : ps) { process(p); }
        }
    }"""
    assert "soql_in_loop" not in _rules(code)
