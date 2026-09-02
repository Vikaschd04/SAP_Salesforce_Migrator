"""A Hybris enum is a closed set — unless it isn't. [1.18]

Both kinds become a Salesforce picklist, so a converter that stops at "emit the values"
looks finished. The difference is whether the target *enforces* the set, and getting it
backwards fails in a different direction each way:

  static enum → unrestricted picklist   accepts a typo the legacy platform rejected,
                                        silently, forever
  dynamic enum → restricted picklist    rejects values the legacy system happily stored,
                                        which surfaces as a failed data load at go-live
                                        on records that were always valid

Neither failure is visible in generated code review. Both are visible in this file.
"""

import textwrap

from src.ingest import _parse_enum_types
from src.metadata_generator import _custom_field_xml
from src.schema import build_schema

ITEMS = textwrap.dedent("""\
    <items>
      <enumtypes>
        <enumtype code="LoyaltyTier" dynamic="true">
          <value code="BRONZE"/><value code="GOLD"/>
        </enumtype>
        <enumtype code="FulfilmentState">
          <value code="PENDING"/><value code="SHIPPED"/>
        </enumtype>
      </enumtypes>
    </items>
    """)


def _enums(tmp_path):
    f = tmp_path / "acme-items.xml"
    f.write_text(ITEMS, encoding="utf-8")
    return _parse_enum_types(str(f))


def test_the_dynamic_attribute_survives_ingest(tmp_path):
    """It used to be dropped here, which made the distinction unrecoverable downstream."""
    got = {e["name"]: e["dynamic"] for e in _enums(tmp_path)}
    assert got == {"LoyaltyTier": True, "FulfilmentState": False}


def test_an_enum_with_no_dynamic_attribute_is_closed(tmp_path):
    """Absent means static in Hybris. Defaulting the other way would unenforce every set."""
    assert _parse_enum_types.__doc__  # sanity: the reasoning is documented
    assert [e for e in _enums(tmp_path) if e["name"] == "FulfilmentState"][0]["dynamic"] is False


def _schema(tmp_path):
    items = [{"name": "Order", "fields": [
        {"name": "tier", "type": "LoyaltyTier"},
        {"name": "state", "type": "FulfilmentState"},
    ]}]
    return build_schema(items, [], _enums(tmp_path))


def test_only_the_dynamic_enum_is_marked_open(tmp_path):
    obj = _schema(tmp_path)["Order__c"]
    assert obj["open_picklists"] == {"Tier__c"}
    assert set(obj["picklists"]) == {"Tier__c", "State__c"}, "both are still picklists"


def test_a_static_enum_emits_a_restricted_picklist(tmp_path):
    xml = _custom_field_xml("State__c", "Picklist", _schema(tmp_path)["Order__c"])
    assert "<restricted>true</restricted>" in xml
    assert "<fullName>PENDING</fullName>" in xml


def test_a_dynamic_enum_emits_an_unrestricted_picklist(tmp_path):
    """The one that would break a go-live data load if we enforced it."""
    xml = _custom_field_xml("Tier__c", "Picklist", _schema(tmp_path)["Order__c"])
    assert "<restricted>false</restricted>" in xml
    assert "<fullName>BRONZE</fullName>" in xml


def test_restricted_precedes_the_value_set_definition(tmp_path):
    """Metadata API element order is the WSDL sequence, not alphabetical."""
    xml = _custom_field_xml("State__c", "Picklist", _schema(tmp_path)["Order__c"])
    assert xml.index("<restricted>") < xml.index("<valueSetDefinition>")


def test_a_picklist_with_no_open_set_recorded_stays_enforced():
    """Missing information must not quietly unenforce a set."""
    xml = _custom_field_xml("State__c", "Picklist",
                            {"picklists": {"State__c": ["A", "B"]}})
    assert "<restricted>true</restricted>" in xml
