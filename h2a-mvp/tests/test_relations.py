"""Relations that survive the crossing, and relations that quietly did not. [1.32, A6]

The engine converted one relation shape and dropped the rest without a word. On the
reference corpus that is one of three: `Order2FulfilmentEvent` became a Lookup,
`Customer2LoyaltyAccount` and `PromotionRule2Product` vanished. Both objects on each side
converted, so every report showed a clean run and the data model was missing two thirds of
its relationships — a schema that deploys 106/106 and is wrong.

Two facts decide the rest, and neither was being read: `partof`, which separates a
relationship that cascades from one that does not, and whether the other end is a type
this extension actually declares.
"""

from pathlib import Path

import pytest

from src.ingest import _parse_items_xml, _parse_relations
from src.relations import (JUNCTION, LOOKUP, MASTER_DETAIL, MD_CEILING, UNRESOLVED,
                           decide, unresolved)
from src.schema import build_schema

ITEMS = next((Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris")
             .rglob("*-items.xml"))

DECLARED = {"Order", "FulfilmentEvent", "Customer", "LoyaltyAccount", "Rule", "Zone"}


def _rel(**kw):
    base = {"code": "R", "source_type": "Order", "target_type": "FulfilmentEvent",
            "source_card": "one", "target_card": "many"}
    base.update(kw)
    return base


def _one(**kw):
    return decide([_rel(**kw)], DECLARED)[0]


# ── the parser keeps what the decision needs ──────────────────────────────────

def test_partof_survives_parsing():
    """It used to be discarded, which made the composition unrecoverable downstream."""
    rels = {r["code"]: r for r in _parse_relations(str(ITEMS))}
    assert rels["Order2FulfilmentEvent"]["target_partof"] is True
    assert rels["Order2FulfilmentEvent"]["source_optional"] is False
    assert rels["Customer2LoyaltyAccount"]["target_partof"] is False


def test_an_end_with_no_modifiers_block_is_optional_and_not_partof():
    """Hybris defaults, not a parse failure — `Customer2LoyaltyAccount` has no modifiers."""
    rels = {r["code"]: r for r in _parse_relations(str(ITEMS))}
    r = rels["Customer2LoyaltyAccount"]
    assert r["source_optional"] is True and r["source_partof"] is False


def test_qualifiers_and_code_survive():
    rels = {r["code"]: r for r in _parse_relations(str(ITEMS))}
    assert rels["Order2FulfilmentEvent"]["target_qualifier"] == "fulfilmentEvents"


def test_an_unparseable_file_yields_nothing():
    assert _parse_relations("/nonexistent/items.xml") == []


# ── cascade, or not ───────────────────────────────────────────────────────────

def test_a_composition_becomes_master_detail():
    """`partof` means Hybris deletes the children with the parent, and master-detail is
    the only Salesforce relationship that does that."""
    row = _one(target_partof=True)
    assert row["kind"] == MASTER_DETAIL and row["cascade"] is True


def test_an_association_stays_a_lookup():
    """Not `partof` — the children outlive the parent in Hybris too, so imposing a
    cascade delete would invent a rule the source never had."""
    row = _one(target_partof=False)
    assert row["kind"] == LOOKUP and row["cascade"] is False
    assert row["lost"] == ""


def test_the_mirrored_direction_finds_the_same_child():
    """many-to-one is one-to-many written the other way round; the `many` end holds the
    children either way."""
    row = decide([_rel(source_card="many", target_card="one", source_partof=True)],
                 DECLARED)[0]
    assert row["kind"] == MASTER_DETAIL
    assert row["child"] == "Order" and row["parent"] == "FulfilmentEvent"


def test_an_optional_parent_on_a_composition_is_called_out():
    """A master-detail child is required by definition. If the source allowed no parent,
    those rows are rejected on load — better said now than discovered at cutover."""
    assert "will be rejected on load" in _one(target_partof=True, source_optional=True)["lost"]


def test_a_required_parent_gets_no_such_warning():
    assert "rejected on load" not in _one(target_partof=True, source_optional=False)["lost"]


# ── shapes Salesforce has no type for ─────────────────────────────────────────

def test_many_to_many_becomes_a_junction_object():
    row = decide([_rel(source_type="Rule", target_type="Zone",
                       source_card="many", target_card="many")], DECLARED)[0]
    assert row["kind"] == JUNCTION


def test_the_junction_carries_two_master_details_and_an_auto_number():
    """A junction row is identified by the pair it links, not a name anyone types."""
    schema = build_schema(
        [{"name": "Rule", "fields": []}, {"name": "Zone", "fields": []}],
        [_rel(source_type="Rule", target_type="Zone",
              source_card="many", target_card="many")], [])
    j = schema["RuleZone__c"]
    assert j["junction"] is True
    assert j["fields"] == {"Rule__c": MASTER_DETAIL, "Zone__c": MASTER_DETAIL}
    assert j["sharing"] == "ControlledByParent"


def test_one_to_one_says_nothing_enforces_the_one():
    """Salesforce has no one-to-one type. A Lookup is the closest shape, and it permits
    exactly what the source forbade."""
    row = _one(source_card="one", target_card="one")
    assert row["kind"] == LOOKUP
    assert "Nothing enforces the *one*" in row["lost"]


# ── relations that cannot be built ────────────────────────────────────────────

def test_a_relation_to_an_out_of_the_box_type_is_not_invented():
    """`Customer__c` will not exist in the org. A lookup to it fails the deploy; inventing
    the object deploys something the source never described."""
    row = decide([_rel(source_type="Customer", target_type="LoyaltyAccount",
                       source_card="one", target_card="one")], {"LoyaltyAccount"})[0]
    assert row["kind"] == UNRESOLVED
    assert "Account" in row["why"] and "Contact" in row["why"]


def test_an_ambiguous_standard_target_is_left_ambiguous():
    """Collapsing "Account or Contact" to one guess is how a wrong data model gets built
    confidently. The source does not say, so neither does the report."""
    row = decide([_rel(source_type="Customer")], {"FulfilmentEvent"})[0]
    assert " or " in row["why"]


def test_an_unknown_type_is_reported_rather_than_guessed():
    row = decide([_rel(source_type="AcmeWidget")], {"FulfilmentEvent"})[0]
    assert row["kind"] == UNRESOLVED
    assert "no known standard counterpart" in row["why"]


def test_unresolved_relations_are_easy_to_ask_for():
    rows = decide([_rel(), _rel(code="X", source_type="Customer")], {"Order", "FulfilmentEvent"})
    assert [r["code"] for r in unresolved(rows)] == ["X"]


# ── the ceiling ───────────────────────────────────────────────────────────────

def test_master_details_past_the_ceiling_demote_to_lookup():
    """Salesforce allows two per object. A third has to give, and the deploy has to land."""
    parents = ["P1", "P2", "P3"]
    rows = decide([_rel(code=f"R{i}", source_type=p, target_type="Child",
                        target_partof=True) for i, p in enumerate(parents)],
                  set(parents) | {"Child"})
    assert [r["kind"] for r in rows] == [MASTER_DETAIL] * MD_CEILING + [LOOKUP]
    assert rows[-1]["demoted"] is True


def test_a_demotion_says_what_it_costs_and_what_to_do():
    rows = decide([_rel(code=f"R{i}", source_type=p, target_type="Child", target_partof=True)
                   for i, p in enumerate(["P1", "P2", "P3"])],
                  {"P1", "P2", "P3", "Child"})
    lost = rows[-1]["lost"]
    assert "Cascade delete is not carried across" in lost
    assert "re-model" in lost


def test_the_ceiling_is_per_object_not_per_run():
    rows = decide([_rel(code="A", source_type="P1", target_type="C1", target_partof=True),
                   _rel(code="B", source_type="P2", target_type="C2", target_partof=True),
                   _rel(code="C", source_type="P3", target_type="C3", target_partof=True)],
                  {"P1", "P2", "P3", "C1", "C2", "C3"})
    assert all(r["kind"] == MASTER_DETAIL for r in rows)


def test_lookups_do_not_count_against_the_ceiling():
    rows = decide([_rel(code=f"R{i}", source_type=p, target_type="Child")
                   for i, p in enumerate(["P1", "P2", "P3"])],
                  {"P1", "P2", "P3", "Child"})
    assert all(r["kind"] == LOOKUP and not r["demoted"] for r in rows)


# ── what reaches the schema ───────────────────────────────────────────────────

def test_a_master_detail_child_is_controlled_by_its_parent():
    """Not cosmetic: a deploy with ReadWrite sharing on a master-detail child is rejected
    outright with "sharing model must be ControlledByParent"."""
    schema = build_schema([{"name": "Order", "fields": []},
                           {"name": "FulfilmentEvent", "fields": []}],
                          [_rel(target_partof=True)], [])
    child = schema["FulfilmentEvent__c"]
    assert child["fields"]["Order__c"] == MASTER_DETAIL
    assert child["sharing"] == "ControlledByParent"
    assert "Order__c" in child["required"], "a master-detail field is required by definition"


def test_a_lookup_child_keeps_its_own_sharing():
    schema = build_schema([{"name": "Order", "fields": []},
                           {"name": "FulfilmentEvent", "fields": []}],
                          [_rel(target_partof=False)], [])
    assert "sharing" not in schema["FulfilmentEvent__c"]


def test_the_decision_is_recorded_on_both_ends():
    """A customer reading either object's section should find the relation there."""
    schema = build_schema([{"name": "Order", "fields": []},
                           {"name": "FulfilmentEvent", "fields": []}],
                          [_rel(target_partof=True)], [])
    for obj in ("Order__c", "FulfilmentEvent__c"):
        assert [n["code"] for n in schema[obj]["relation_notes"]] == ["R"]


# ── the corpus, end to end ────────────────────────────────────────────────────

def test_the_corpus_converts_one_relation_and_reports_the_other_two():
    """Before 1.32 the same corpus converted one and reported none."""
    schema = build_schema(_parse_items_xml(str(ITEMS)), _parse_relations(str(ITEMS)), [])
    rows = {n["code"]: n for meta in schema.values()
            for n in meta.get("relation_notes", [])}
    assert rows["Order2FulfilmentEvent"]["kind"] == MASTER_DETAIL
    assert rows["Customer2LoyaltyAccount"]["kind"] == UNRESOLVED
    assert rows["PromotionRule2Product"]["kind"] == UNRESOLVED


def test_the_corpus_emits_no_object_for_an_out_of_the_box_type():
    """`Customer__c` and `Product__c` must not appear — they are standard objects on the
    target, and a custom twin of a standard object is a data model nobody asked for."""
    schema = build_schema(_parse_items_xml(str(ITEMS)), _parse_relations(str(ITEMS)), [])
    assert "Customer__c" not in schema and "Product__c" not in schema


@pytest.mark.parametrize("code", ["Customer2LoyaltyAccount", "PromotionRule2Product"])
def test_a_dropped_relation_reaches_the_sign_off(code):
    """The one place a customer is guaranteed to look before a cutover."""
    from src import assurance
    from src.signoff import _caveats

    schema = build_schema(_parse_items_xml(str(ITEMS)), _parse_relations(str(ITEMS)), [])
    notes = [n for meta in schema.values() for n in meta.get("relation_notes", [])]
    claim = {"rung": assurance.REPLAYED, "claim": "", "limit": ""}
    text = "\n".join(_caveats({}, {}, {}, {}, {}, [], claim, relation_notes=notes))
    assert code in text
    assert "not in the output" in text
