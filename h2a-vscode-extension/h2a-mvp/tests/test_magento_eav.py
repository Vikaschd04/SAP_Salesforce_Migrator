"""Attributes that exist as rows, not as columns. [2.8, G1]

The single largest structural difference between the two platforms. A Magento EAV
attribute is a database row created when a data patch runs; a Hybris attribute is a
declaration in items.xml resolved at build time. Reading one and writing the other is not
a translation, it is a change of kind — and what makes it dangerous is that the source of
truth moves out of the code.

Three populations exist and only the first is in the repository:

    declared in a patch    read here, from the AST
    declared by a module   visible only if that module's source is in scope
    added by a person      created in the admin UI, in no file, unreadable by any tool

Most of these tests are about the third. A schema that presents the first population as
the whole entity is the failure: the migration looks complete, the customer's own custom
fields are missing, and nothing says a word about it.
"""

import textwrap
from pathlib import Path

import pytest

from src import ir
from src.adapters.magento_eav import as_data_types, read_attributes
from src.adapters.php_reader import available

pytestmark = pytest.mark.skipif(not available(), reason="tree-sitter-php not installed")

MAGENTO = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")


@pytest.fixture(scope="module")
def attrs():
    return read_attributes(MAGENTO)


def test_attributes_declared_by_a_data_patch_are_found(attrs):
    assert {a["code"] for a in attrs} == {"acme_loyalty_tier", "acme_points_balance"}


def test_the_entity_constant_is_resolved(attrs):
    """`Customer::ENTITY` names `customer`. A wrong entity attaches a field to the wrong object."""
    assert {a["entity"] for a in attrs} == {"customer"}


def test_an_unknown_entity_constant_keeps_its_raw_text(tmp_path):
    (tmp_path / "P.php").write_text(
        "<?php class P { function apply() { $s->addAttribute(Weird::THING, 'x', "
        "['type' => 'varchar']); } }", encoding="utf-8")
    assert read_attributes(str(tmp_path))[0]["entity"] == "Weird::THING"


def test_backend_types_map_to_the_neutral_types(attrs):
    by_code = {a["code"]: a for a in attrs}
    assert by_code["acme_loyalty_tier"]["type"] == "String"
    assert by_code["acme_points_balance"]["type"] == "Integer"


def test_the_options_array_is_read(attrs):
    tier = next(a for a in attrs if a["code"] == "acme_loyalty_tier")
    assert tier["input"] == "select"
    assert tier["label"] == "Loyalty Tier"
    assert tier["required"] is False


def test_a_source_model_is_kept_as_text_not_dropped(attrs):
    """`'source' => Tier::class` is what tells a reviewer this attribute is a picklist."""
    tier = next(a for a in attrs if a["code"] == "acme_loyalty_tier")
    assert "Tier::class" in tier["source"]


def test_an_attribute_code_built_at_runtime_is_recorded_as_a_gap(tmp_path):
    """"We saw one we could not read" is a different statement from "there are none"."""
    (tmp_path / "P.php").write_text(
        "<?php class P { function apply() { $s->addAttribute(Customer::ENTITY, "
        "$this->code, ['type' => 'varchar']); } }", encoding="utf-8")
    got = read_attributes(str(tmp_path))
    assert len(got) == 1
    assert got[0]["code"] == "" and got[0]["unreadable"]


def test_a_file_with_no_addattribute_is_skipped_cheaply(tmp_path):
    (tmp_path / "Plain.php").write_text("<?php class Plain { function f() {} }",
                                        encoding="utf-8")
    assert read_attributes(str(tmp_path)) == []


# ── grouping into the IR ──────────────────────────────────────────────────────

def test_attributes_group_into_one_data_type_per_entity(attrs):
    types = as_data_types(attrs)
    assert len(types) == 1
    assert isinstance(types[0], ir.DataType)
    assert types[0].code == "customer"
    assert len(types[0].attributes) == 2


def test_an_eav_type_extends_an_entity_rather_than_being_a_new_one(attrs):
    """On Hybris these are attributes added to an existing item type.

    Treating them as a new type would produce a parallel object holding half a customer.
    """
    t = as_data_types(attrs)[0]
    assert t.extends == "customer"
    assert t.deployment == "eav"


def test_every_eav_type_says_the_set_is_open(attrs):
    """The failure this item exists to prevent: a partial schema presented as complete."""
    note = as_data_types(attrs)[0].undeclared_note
    assert "admin UI" in note
    assert "no file at all" in note
    assert "exported from the live system" in note


def test_the_note_counts_what_could_not_be_read(tmp_path):
    (tmp_path / "P.php").write_text(
        "<?php class P { function apply() { "
        "$s->addAttribute(Customer::ENTITY, 'ok', ['type' => 'int']); "
        "$s->addAttribute(Customer::ENTITY, $dyn, ['type' => 'int']); } }",
        encoding="utf-8")
    t = as_data_types(read_attributes(str(tmp_path)))[0]
    assert len(t.attributes) == 1, "only the readable one becomes an attribute"
    assert "1 addAttribute call(s) build their code at runtime" in t.undeclared_note


def test_no_attributes_produces_no_types():
    assert as_data_types([]) == []
