"""MAPPING.md must describe the migration that happened. [1.31]

The report used to derive its Apex columns independently of the schema the metadata is
emitted from — a Java-type lookup with `Text(255)` as the fallback, and the source
attribute name with `__c` stapled on. Both were wrong wherever anything interesting
happened:

    reported                          emitted
    fulfilmentState__c · Text(255)    FulfilmentState__c · Picklist

and after 1.20a, a name adjusted for length or collision would have been reported under a
name that does not exist in the org at all.

A customer reads this file to understand what the migration did. These tests hold the
report and the metadata to the same source of truth, because two sources for one fact is
how a report starts describing a migration that did not happen.
"""

import re
from pathlib import Path

import pytest

from src.generate import _build_mapping_md, _load_mappings
from src.ingest import ingest
from src.schema import build_schema

CORPUS = Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris"


@pytest.fixture(scope="module")
def corpus():
    res = ingest(str(CORPUS))
    schema = build_schema(res["item_types"], res["relations"], res["enum_types"])
    md = _build_mapping_md([], res["item_types"], _load_mappings(), schema)
    return res, schema, md


def _rows(md: str):
    """(object, hybris_field, apex_field, apex_type) for every SObject-mapping row."""
    obj, out = None, []
    for line in md.splitlines():
        head = re.match(r"### \w+ -> (\w+__c)", line)
        if head:
            obj = head.group(1)
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if "|" in line else []
        if obj and len(cells) == 5 and cells[0] not in ("Hybris Field", "---"):
            out.append((obj, cells[0], cells[2], cells[3]))
    return out


def test_the_report_has_rows_at_all(corpus):
    _, _, md = corpus
    assert len(_rows(md)) > 10, "a parser that finds nothing would pass every test below"


def test_every_reported_field_is_a_field_the_schema_emits(corpus):
    """The exact failure: reporting a field name that does not exist in the org."""
    _, schema, md = corpus
    for obj, hybris, api, _ in _rows(md):
        assert api in schema[obj]["fields"], \
            f"{obj}.{hybris} reported as `{api}`, which the metadata never emits"


def test_every_reported_type_is_the_type_the_schema_emits(corpus):
    """The enum case: reported Text(255), emitted Picklist."""
    _, schema, md = corpus
    for obj, hybris, api, apex_type in _rows(md):
        assert apex_type == schema[obj]["fields"][api], \
            f"{obj}.{hybris} reported as {apex_type}, emitted as {schema[obj]['fields'][api]}"


def test_enum_fields_are_reported_as_picklists(corpus):
    """Named explicitly, because this is the row the old report always got wrong."""
    _, _, md = corpus
    row = next(r for r in _rows(md) if r[1] == "fulfilmentState")
    assert row[2] == "FulfilmentState__c"
    assert row[3] == "Picklist"


def test_a_renamed_field_is_reported_under_its_real_name_and_says_why():
    items = [{"name": "Delivery", "fields": [
        {"name": "trackingCode", "type": "java.lang.String"},
        {"name": "TrackingCode", "type": "java.lang.Integer"},
    ]}]
    schema = build_schema(items, [], [])
    md = _build_mapping_md([], items, _load_mappings(), schema)
    rows = _rows(md)
    assert {r[2] for r in rows} == set(schema["Delivery__c"]["fields"]), \
        "both renamed fields must be reported under the names actually emitted"
    assert all("renamed" in line for line in md.splitlines()
               if "TrackingCode_" in line and line.startswith("|"))


def test_an_object_with_no_schema_says_so_rather_than_inventing_a_column():
    items = [{"name": "Ghost", "fields": [{"name": "x", "type": "java.lang.String"}]}]
    md = _build_mapping_md([], items, _load_mappings(), {})
    assert "not in the emitted schema" in md
    assert "Ghost__c" in md
