"""Fields that collide, and objects too wide to deploy. [1.20b]

1.20a made attribute names collision-safe. It did not cover the *other* way a field
arrives: a relation. Those were written straight into the field map, so a relation from
`Order` onto a type that already had an `order` attribute replaced it — two source facts,
one field, and the survivor typed `Lookup` instead of `Text`. Same silent loss, one path
over.

The ceiling is a different kind of problem. 505 fields on an object is not a quality
caveat, it is a deploy that cannot land, and it belongs where someone reads it before
scheduling a cutover.
"""

import pytest

from src.schema import FIELD_CEILING, build_schema

ENTRY = [{"name": "OrderEntry", "fields": [
    {"name": "order", "type": "java.lang.String"},
    {"name": "quantity", "type": "java.lang.Integer"},
]}]
REL = [{"source_type": "Order", "target_type": "OrderEntry",
        "source_card": "one", "target_card": "many"}]


# ── a relation must not overwrite an attribute ────────────────────────────────

def test_an_attribute_survives_a_relation_of_the_same_name():
    obj = build_schema(ENTRY, REL, [])["OrderEntry__c"]
    assert obj["fields"]["Order__c"] == "Text", "the declared attribute keeps its type"
    assert sum(1 for t in obj["fields"].values() if t == "Lookup") == 1


def test_both_facts_are_kept():
    obj = build_schema(ENTRY, REL, [])["OrderEntry__c"]
    assert len(obj["fields"]) == 3, "two attributes and one relation"


def test_the_rename_says_which_side_moved_and_why():
    """The attribute was declared on this type; the relation was declared elsewhere. That
    asymmetry is the reason the relation is the one renamed, and it is written down."""
    note = build_schema(ENTRY, REL, [])["OrderEntry__c"]["name_notes"][0]
    assert note["reason"] == "collision"
    assert "declared on this type" in note["detail"]
    assert "relation was declared elsewhere" in note["detail"]


def test_a_relation_with_no_clash_keeps_the_plain_name():
    items = [{"name": "OrderEntry", "fields": [{"name": "quantity", "type": "java.lang.Integer"}]}]
    obj = build_schema(items, REL, [])["OrderEntry__c"]
    assert obj["fields"]["Order__c"] == "Lookup"
    assert obj["name_notes"] == []


def test_the_schema_gains_no_key_nothing_reads():
    """The recipe hash is taken over the schema, so an unused key invalidates every
    customer's incremental cache for no change in any prompt."""
    obj = build_schema(ENTRY, REL, [])["OrderEntry__c"]
    assert "relations" not in obj


def test_an_object_that_exists_only_as_a_relation_target_is_whole():
    """It used to be created as `{code, fields}` alone, so every reader had to guess
    whether `picklists` or `name_notes` would be there."""
    obj = build_schema([], REL, [])["OrderEntry__c"]
    for key in ("picklists", "open_picklists", "name_notes", "localized", "field_api",
                "required", "unique", "defaults"):
        assert key in obj, key


# ── the field ceiling ─────────────────────────────────────────────────────────

def _wide(n):
    return [{"name": "Product",
             "fields": [{"name": f"a{i}", "type": "java.lang.String"} for i in range(n)]}]


def test_an_object_within_the_ceiling_says_nothing():
    assert not build_schema(_wide(50), [], [])["Product__c"].get("shape_notes")


def test_an_object_over_the_ceiling_is_reported():
    note = build_schema(_wide(FIELD_CEILING + 5), [], [])["Product__c"]["shape_notes"][0]
    assert note["kind"] == "field_ceiling"
    assert note["count"] == FIELD_CEILING + 5 and note["limit"] == FIELD_CEILING


def test_the_ceiling_is_not_resolved_automatically():
    """Which attributes to drop, merge or move is a modelling decision. Trimming would
    silently discard whichever ones happened to sort last."""
    obj = build_schema(_wide(FIELD_CEILING + 5), [], [])["Product__c"]
    assert len(obj["fields"]) == FIELD_CEILING + 5, "nothing was quietly removed"


def test_the_note_names_the_ways_out():
    note = build_schema(_wide(FIELD_CEILING + 5), [], [])["Product__c"]["shape_notes"][0]
    assert "split the type" in note["detail"]
    assert "child object" in note["detail"]


def test_the_contract_leads_with_a_deploy_that_cannot_land():
    from src.agentic.blackboard import Blackboard
    from src.signoff import build_signoff

    bb = Blackboard("in", "out")
    bb.approvals = []
    bb.schema = build_schema(_wide(FIELD_CEILING + 5), [], [])

    caveats = build_signoff(bb)["caveats"]
    assert any("Salesforce allows 500 per object" in c for c in caveats)


def test_a_healthy_schema_adds_no_caveat():
    from src.agentic.blackboard import Blackboard
    from src.signoff import build_signoff

    bb = Blackboard("in", "out")
    bb.approvals = []
    bb.schema = build_schema(_wide(10), [], [])
    assert not any("per object" in c for c in build_signoff(bb)["caveats"])
