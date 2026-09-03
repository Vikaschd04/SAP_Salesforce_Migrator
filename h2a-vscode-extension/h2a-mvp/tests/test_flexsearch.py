"""FlexibleSearch is SQL; SOQL is not. [1.23]

The overlap is wide enough that a model asked to "convert this query" produces
SOQL-shaped text for cases SOQL cannot express. That text either fails to compile — the
good outcome — or compiles against the wrong relationship and quietly returns different
rows. So the query is parsed mechanically and answered honestly.
"""

import pytest

from src.adapters.hybris_flexsearch import analyse, find_queries

SIMPLE = "SELECT {o:pk} FROM {Order AS o} WHERE {o:code} = ?code"


# ── the cases SOQL can express ────────────────────────────────────────────────

def test_a_simple_query_is_translated_not_guessed():
    a = analyse(SIMPLE)
    assert a["verdict"] == "direct"
    assert a["soql"] == "SELECT Id FROM Order__c WHERE Code__c = :code"


def test_hybris_system_attributes_map_to_standard_fields():
    a = analyse("SELECT {c:pk} FROM {Cart AS c} WHERE {c:modifiedtime} < ?olderThan")
    assert a["soql"] == "SELECT Id FROM Cart__c WHERE LastModifiedDate < :olderThan"


def test_ordering_survives_translation():
    a = analyse("SELECT {o:pk} FROM {Order AS o} WHERE {o:user} = ?c "
                "ORDER BY {o:creationtime} DESC")
    assert a["soql"].endswith("ORDER BY CreatedDate DESC")


def test_positional_parameters_become_apex_binds():
    assert ":code" in analyse(SIMPLE)["soql"]
    assert "?code" not in analyse(SIMPLE)["soql"]


# ── the cases it cannot ───────────────────────────────────────────────────────

def test_a_join_is_blocked_and_not_attempted():
    a = analyse("SELECT {o:pk} FROM {Order AS o}, {Customer AS c} WHERE {o:user}={c:pk}")
    assert a["verdict"] == "blocked"
    assert a["soql"] is None, "an attempt would look like an answer"
    assert [r["code"] for r in a["reasons"]] == ["FS_JOIN"]


def test_an_explicit_join_keyword_is_blocked_too():
    a = analyse("SELECT {o:pk} FROM {Order AS o JOIN Customer AS c ON {o:user}={c:pk}}")
    assert a["verdict"] == "blocked"


def test_a_subquery_is_blocked():
    a = analyse("SELECT {o:pk} FROM {Order AS o} "
                "WHERE {o:pk} IN ({{ SELECT {p:order} FROM {Payment AS p} }})")
    assert "FS_SUBQUERY" in [r["code"] for r in a["reasons"]]


def test_a_leading_wildcard_is_blocked():
    a = analyse("SELECT {p:pk} FROM {Product AS p} WHERE {p:name} LIKE '%shoe%'")
    assert "FS_LEADING_WILDCARD" in [r["code"] for r in a["reasons"]]


def test_a_trailing_wildcard_is_fine():
    """`LIKE 'shoe%'` uses an index. Only the leading one is the problem."""
    a = analyse("SELECT {p:pk} FROM {Product AS p} WHERE {p:name} LIKE 'shoe%'")
    assert a["verdict"] == "direct"


def test_every_blocking_reason_is_reported_at_once():
    """Fixing one and rediscovering the next is a bad way to spend a migration."""
    a = analyse("SELECT {o:pk} FROM {Order AS o}, {Customer AS c} "
                "WHERE {o:pk} IN ({{ SELECT {p:order} FROM {Payment AS p} }}) "
                "AND {c:name} LIKE '%acme%'")
    assert {r["code"] for r in a["reasons"]} == {"FS_JOIN", "FS_SUBQUERY",
                                                 "FS_LEADING_WILDCARD"}


def test_every_reason_names_a_fix():
    a = analyse("SELECT {o:pk} FROM {Order AS o}, {Customer AS c}")
    assert all(r["fix"] and r["detail"] for r in a["reasons"])


# ── finding them in source ────────────────────────────────────────────────────

def test_queries_are_found_with_their_line_numbers():
    src = 'class A {\n  static final String Q =\n    "' + SIMPLE + '";\n}\n'
    assert find_queries(src) == [(3, SIMPLE)]


def test_an_ordinary_string_is_not_a_query():
    assert find_queries('String s = "hello from acme";') == []


def test_the_reference_corpus_queries_all_translate():
    from pathlib import Path

    dao = (Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris" /
           "core-customize/hybris/bin/custom/acmecore/src/com/acme/core/dao/impl/"
           "DefaultOrderDao.java")
    found = find_queries(dao.read_text(encoding="utf-8"))
    assert len(found) == 5
    assert all(analyse(q)["verdict"] == "direct" for _, q in found), \
        "the corpus is deliberately simple; a blocked query here would change golden"


# ── the derived SOQL reaching the Builder [1.23b] ─────────────────────────────

def _dao_source():
    from pathlib import Path

    return (Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris" /
            "core-customize/hybris/bin/custom/acmecore/src/com/acme/core/dao/impl/"
            "DefaultOrderDao.java").read_text(encoding="utf-8")


def test_every_translatable_query_reaches_the_builder():
    """The analyser derived correct SOQL from the first day of 1.23a and it went nowhere:
    only the blocking cases reached a report, and the Builder translated FlexibleSearch
    from raw source — generating the one part of this migration that can be derived."""
    from src.adapters.hybris_flexsearch import grounding_for

    block = grounding_for([_dao_source()])
    assert "SELECT Id FROM Order__c WHERE Code__c = :code" in block
    assert block.count("→") == 5


def test_the_block_tells_the_model_not_to_re_translate():
    from src.adapters.hybris_flexsearch import grounding_for

    assert "do not re-translate the original" in grounding_for([_dao_source()])


def test_a_blocked_query_is_named_rather_than_left_silent():
    """Silence invites the model to try. Naming what cannot be expressed is worth more."""
    from src.adapters.hybris_flexsearch import grounding_for

    src = ('class D { String Q = "SELECT {o:pk} FROM {Order AS o}, {Customer AS c} '
           'WHERE {o:user}={c:pk}"; }')
    block = grounding_for([src])
    assert "no SOQL equivalent" in block
    assert "FS_JOIN" in block
    assert "Do not invent one" in block


def test_a_source_with_no_queries_contributes_nothing():
    """An empty heading in the prompt is noise that costs tokens on every target."""
    from src.adapters.hybris_flexsearch import grounding_for

    assert grounding_for(["class Plain { void f() {} }"]) == ""
    assert grounding_for([]) == ""


def test_the_builder_asks_the_running_source_platform():
    """A Magento source has collections and raw SQL, not FlexibleSearch. Its own analyser
    is what would answer, and a platform with nothing to contribute returns nothing."""
    from src import runctx
    from src.agentic.builders import _derived_queries

    classes = [{"class_name": "DefaultOrderDao", "source": _dao_source()}]
    assert "SELECT Id FROM Order__c" in _derived_queries(classes)

    token = runctx._pipeline_id.set("adobe->hybris")
    try:
        assert _derived_queries(classes) == ""
    finally:
        runctx._pipeline_id.reset(token)
