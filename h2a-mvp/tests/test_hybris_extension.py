"""The SAP Hybris extension an Adobe Commerce project becomes. [3.1, 3.4]

Everything here is deterministic — no model is asked what a table should be called or
which Java type a decimal maps to. Those are lookups, and a lookup routed through an LLM
is one that can be wrong in a way nobody notices.

Most of these tests are about a single distinction that decides whether the migration
splits an entity in two: a *declared table* becomes a new item type, and a Magento **EAV
extension** contributes attributes to a type SAP already owns. Emitting the second as the
first produces a parallel `Customer` holding half a customer — it deploys perfectly, and
the original stays authoritative and missing the fields.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src import ir
from src.adapters.hybris_extension import (build_extension, build_items_xml, java_type,
                                           pascal)

MAGENTO = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")


@pytest.fixture(scope="module")
def model():
    from src.adapters.php_reader import available
    if not available():
        pytest.skip("tree-sitter-php not installed")
    from src.adapters.adobe_source import ADAPTER
    return ADAPTER.read(MAGENTO)


@pytest.fixture(scope="module")
def xml(model):
    return build_items_xml(model.data_model, extension="acmeloyalty")


# ── the lookups ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ir_type,java", [
    ("String", "java.lang.String"), ("Integer", "java.lang.Integer"),
    ("BigDecimal", "java.math.BigDecimal"), ("DateTime", "java.util.Date"),
    ("Boolean", "java.lang.Boolean"), ("", "java.lang.String"),
])
def test_ir_types_map_to_java(ir_type, java):
    assert java_type(ir_type) == java


def test_table_names_become_item_type_names():
    assert pascal("acme_loyalty_account") == "AcmeLoyaltyAccount"


# ── a declared table becomes a new type ───────────────────────────────────────

def test_the_document_is_well_formed(xml):
    ET.fromstring(xml)


def test_a_declared_table_becomes_a_generated_item_type(xml):
    root = ET.fromstring(xml)
    acct = next(i for i in root.iter("itemtype") if i.get("code") == "AcmeLoyaltyAccount")
    assert acct.get("autocreate") == "true" and acct.get("generate") == "true"
    assert acct.get("extends") == "GenericItem"


def test_a_new_type_gets_a_deployment_table_and_a_custom_typecode(xml):
    root = ET.fromstring(xml)
    dep = next(i for i in root.iter("itemtype")
               if i.get("code") == "AcmeLoyaltyAccount").find("deployment")
    assert dep.get("table") == "acmeloyaltyaccount"
    assert int(dep.get("typecode")) >= 10001, "below 10000 is platform territory"


def test_typecodes_do_not_collide(xml):
    codes = [d.get("typecode") for d in ET.fromstring(xml).iter("deployment")]
    assert len(codes) == len(set(codes))


def test_column_constraints_survive(xml):
    root = ET.fromstring(xml)
    acct = next(i for i in root.iter("itemtype") if i.get("code") == "AcmeLoyaltyAccount")
    code = next(a for a in acct.iter("attribute") if a.get("qualifier") == "code")
    assert code.get("type") == "java.lang.String"
    mods = code.find("modifiers")
    assert mods.get("optional") == "false" and mods.get("unique") == "true"


def test_a_decimal_column_does_not_become_a_double(xml):
    """`lifetime_spend` is money. Double would be the same class of bug as A1."""
    root = ET.fromstring(xml)
    spend = next(a for a in root.iter("attribute")
                 if a.get("qualifier") == "lifetime_spend")
    assert spend.get("type") == "java.math.BigDecimal"


# ── an EAV entity extends, never shadows ──────────────────────────────────────

def test_an_eav_entity_contributes_to_the_platform_type(xml):
    """The failure this guards: a parallel Customer holding half a customer."""
    root = ET.fromstring(xml)
    cust = next(i for i in root.iter("itemtype") if i.get("code") == "Customer")
    assert cust.get("autocreate") == "false"
    assert cust.get("generate") == "false"
    assert cust.find("deployment") is None, "it does not own a table"


def test_the_eav_entity_is_named_as_sap_names_it(xml):
    """Magento calls it `customer`; SAP calls it `Customer`. The name has to be SAP's."""
    codes = {i.get("code") for i in ET.fromstring(xml).iter("itemtype")}
    assert "Customer" in codes and "customer" not in codes


def test_the_eav_attributes_are_the_ones_the_patch_declared(xml):
    root = ET.fromstring(xml)
    cust = next(i for i in root.iter("itemtype") if i.get("code") == "Customer")
    assert {a.get("qualifier") for a in cust.iter("attribute")} == {
        "acme_loyalty_tier", "acme_points_balance"}


def test_the_open_set_warning_reaches_the_file_a_developer_reads(xml):
    """The note survived ingest, the IR and emission. Dropped anywhere, it never existed."""
    assert "admin UI" in xml and "exported from the live system" in xml


# ── the extension skeleton ────────────────────────────────────────────────────

def test_the_skeleton_is_the_layout_the_platform_expects(tmp_path, model):
    created = build_extension(str(tmp_path), name="acmeloyalty",
                              package="com.acme.loyalty", data_model=model.data_model)
    root = tmp_path / "hybris" / "bin" / "custom" / "acmeloyalty"
    for rel in ("extensioninfo.xml", "build.xml",
                "resources/acmeloyalty-items.xml", "resources/acmeloyalty-spring.xml"):
        assert (root / rel).exists(), rel
    assert (root / "src" / "com" / "acme" / "loyalty").is_dir()
    assert (root / "testsrc" / "com" / "acme" / "loyalty").is_dir()
    assert len(created) == 4


def test_extensioninfo_declares_the_platform_dependencies(tmp_path, model):
    build_extension(str(tmp_path), name="acmeloyalty", package="com.acme.loyalty",
                    data_model=model.data_model)
    info = (tmp_path / "hybris/bin/custom/acmeloyalty/extensioninfo.xml").read_text()
    ET.fromstring(info)
    assert 'name="core"' in info and 'name="commerceservices"' in info
    assert 'classprefix="Acmeloyalty"' in info


# ── the guard that has to stay ────────────────────────────────────────────────

def test_emit_still_refuses_while_services_are_missing(tmp_path, model):
    """A run that wrote items.xml and no services would report files created and hand
    over an extension with a data model and no behaviour. That reads as success."""
    from src.adapters.adobe_source import NotImplementedYet
    from src.adapters.hybris_target import ADAPTER

    with pytest.raises(NotImplementedYet) as e:
        ADAPTER.emit(str(tmp_path), [], model.data_model, {})
    assert "services, DAOs" in str(e.value)
