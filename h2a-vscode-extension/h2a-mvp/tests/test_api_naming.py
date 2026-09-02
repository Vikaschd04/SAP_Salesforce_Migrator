"""Two attributes must never become one field. [1.20]

This is the silent-data-loss case in the register, and before this existed the engine had
it: four source attributes went into `build_schema` and three fields came out. The
survivor kept the *later* attribute's type, the metadata deployed cleanly, and one column
of data had nowhere to land. Nothing in the run said so.

Long names fail earlier and louder — a name over 40 characters is rejected at deploy —
but they fail at the very last step of a migration, which is the worst moment to discover
a naming problem.
"""

from src.schema import _api_names, build_schema

LONG_A = "deliveryModeForAlternativeDeliveryAddress"      # 41 -> 44 with __c
LONG_B = "deliveryModeForAlternativeBillingAddresses"     # 42 -> 45 with __c


def test_nothing_is_lost_when_two_attributes_collide():
    names, notes = _api_names(["trackingCode", "TrackingCode"])
    assert len(set(names.values())) == 2, "two attributes, two distinct fields"
    assert all(n["reason"] == "collision" for n in notes)


def test_a_collision_tags_both_sides_not_just_the_loser():
    """Otherwise the winner depends on iteration order, and two runs disagree."""
    names, _ = _api_names(["trackingCode", "TrackingCode"])
    assert all(v != "TrackingCode__c" for v in names.values())


def test_collision_handling_is_order_independent():
    a, _ = _api_names(["trackingCode", "TrackingCode"])
    b, _ = _api_names(["TrackingCode", "trackingCode"])
    assert a == b


def test_names_are_stable_across_processes():
    """md5, not hash() — a salted hash would make every re-run look like a schema change."""
    names, _ = _api_names(["trackingCode", "TrackingCode"])
    assert names["trackingCode"] == "TrackingCode_0847__c"


def test_long_names_are_brought_within_the_platform_limit():
    names, notes = _api_names([LONG_A, LONG_B])
    assert all(len(v) <= 40 for v in names.values())
    assert all(n["reason"] == "length" for n in notes)


def test_two_long_names_do_not_truncate_onto_each_other():
    """They share a 31-character prefix. Plain truncation would merge them."""
    names, _ = _api_names([LONG_A, LONG_B])
    assert len(set(names.values())) == 2


def test_ordinary_names_are_left_completely_alone():
    """The common case must stay clean, or every field in every migration gets uglier."""
    names, notes = _api_names(["code", "tier", "pointsBalance", "lifetimeSpend"])
    assert names == {"code": "Code__c", "tier": "Tier__c",
                     "pointsBalance": "PointsBalance__c",
                     "lifetimeSpend": "LifetimeSpend__c"}
    assert notes == [], "no adjustment means nothing to report"


def test_every_adjustment_is_explained():
    _, notes = _api_names(["trackingCode", "TrackingCode", LONG_A])
    for n in notes:
        assert n["detail"] and n["qualifier"] and n["api"]
        assert "Salesforce" in n["detail"], "say what the platform rule is"


def test_the_schema_keeps_all_four_fields_and_both_types():
    items = [{"name": "Delivery", "fields": [
        {"name": LONG_A, "type": "java.lang.String"},
        {"name": LONG_B, "type": "java.lang.String"},
        {"name": "trackingCode", "type": "java.lang.String"},
        {"name": "TrackingCode", "type": "java.lang.Integer"},
    ]}]
    obj = build_schema(items, [], [])["Delivery__c"]
    assert len(obj["fields"]) == 4, "four attributes in, four fields out"
    assert sorted(obj["fields"].values()) == ["Number", "Text", "Text", "Text"], \
        "the colliding attributes had different types; both must survive"
    assert len(obj["name_notes"]) == 4


def test_the_reference_corpus_needs_no_adjustment_at_all():
    """Its attributes are short and unique, so the migration output is unchanged."""
    from pathlib import Path

    from src.ingest import ingest

    corpus = Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris"
    res = ingest(str(corpus))
    schema = build_schema(res["item_types"], res["relations"], res["enum_types"])
    assert not any(o["name_notes"] for o in schema.values())
