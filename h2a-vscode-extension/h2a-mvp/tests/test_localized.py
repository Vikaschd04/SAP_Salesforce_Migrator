"""A localized attribute holds one value per locale. A Salesforce field holds one. [1.19]

Two failures, and the quieter one is the type bug. `localized:java.lang.Integer` never
matched the type table, so *every* localized attribute fell through to Text regardless of
what it actually held — a localized Integer became a Text field, and Apex doing
arithmetic against it would not compile.

The louder one is the reason the item exists: for an EU retailer most content is
translated, and a straight conversion keeps the default locale and drops the rest with
nothing in the output showing anything went missing.
"""

import textwrap

from src.generate import _build_mapping_md, _load_mappings
from src.schema import build_schema

ITEMS = [{"name": "Product", "fields": [
    {"name": "name", "type": "localized:java.lang.String"},
    {"name": "stock", "type": "localized:java.lang.Integer"},
    {"name": "plainStock", "type": "java.lang.Integer"},
]}]


def test_a_localized_attribute_keeps_its_real_type():
    """The quiet bug: the prefix was never stripped, so everything became Text."""
    fields = build_schema(ITEMS, [], [])["Product__c"]["fields"]
    assert fields["Stock__c"] == "Number", "a localized Integer is still an Integer"
    assert fields["Name__c"] == "Text"
    assert fields["PlainStock__c"] == "Number", "ordinary types are unaffected"


def test_a_localized_enum_still_becomes_a_picklist():
    items = [{"name": "Product", "fields": [{"name": "tier", "type": "localized:LoyaltyTier"}]}]
    enums = [{"name": "LoyaltyTier", "values": ["GOLD"], "dynamic": False}]
    obj = build_schema(items, [], enums)["Product__c"]
    assert obj["fields"]["Tier__c"] == "Picklist"
    assert "Tier__c" in obj["localized"]


def test_the_localized_fields_are_recorded():
    obj = build_schema(ITEMS, [], [])["Product__c"]
    assert obj["localized"] == {"Name__c", "Stock__c"}


def test_the_mapping_report_says_the_other_locales_are_gone():
    schema = build_schema(ITEMS, [], [])
    md = _build_mapping_md([], ITEMS, _load_mappings(), schema)
    row = next(l for l in md.splitlines() if l.startswith("| name "))
    assert "only the default locale is carried" in row
    plain = next(l for l in md.splitlines() if l.startswith("| plainStock "))
    assert "locale" not in plain, "the note must be specific or it stops being read"


def test_the_note_survives_alongside_a_rename():
    """Both facts matter; one must not silently replace the other."""
    items = [{"name": "P", "fields": [
        {"name": "n" * 45, "type": "localized:java.lang.String"}]}]
    schema = build_schema(items, [], [])
    md = _build_mapping_md([], items, _load_mappings(), schema)
    row = next(l for l in md.splitlines() if l.startswith("| nnn"))
    assert "only the default locale is carried" in row and "renamed" in row


def test_radar_reports_localized_attributes(tmp_path):
    from src.radar import scan

    ext = tmp_path / "bin" / "custom" / "acme" / "resources"
    ext.mkdir(parents=True)
    (ext / "acme-items.xml").write_text(textwrap.dedent("""\
        <items>
          <itemtype code="Product">
            <attributes>
              <attribute qualifier="name" type="localized:java.lang.String"/>
              <attribute qualifier="code" type="java.lang.String"/>
            </attributes>
          </itemtype>
        </items>
        """), encoding="utf-8")

    hits = [f for f in scan(str(tmp_path))["findings"] if f["rule"] == "LOCALIZED_ATTRIBUTE"]
    assert len(hits) == 1
    assert "name" in hits[0]["hazard"]
    assert "Translation Workbench" in hits[0]["fix"]
    assert "child object keyed by locale" in hits[0]["fix"], \
        "labels and content have different right answers; naming only one misleads"


def test_a_file_with_no_localized_attributes_is_silent(tmp_path):
    from src.radar import scan

    ext = tmp_path / "resources"
    ext.mkdir(parents=True)
    (ext / "acme-items.xml").write_text(
        '<items><itemtype code="P"><attributes>'
        '<attribute qualifier="code" type="java.lang.String"/>'
        "</attributes></itemtype></items>", encoding="utf-8")
    assert not [f for f in scan(str(tmp_path))["findings"]
                if f["rule"] == "LOCALIZED_ATTRIBUTE"]
