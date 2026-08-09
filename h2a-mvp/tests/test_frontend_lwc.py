"""
test_frontend_lwc.py — Spartacus (Angular) → LWC path: ingest, generate, validate.
"""

from pathlib import Path

from src.frontend_ingest import ingest_frontend
from src.generate import lwc_name, plan_targets
from src.generate_lwc import generate_lwc
from src.validate_lwc import validate_lwc

_STOREFRONT = Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris" / "js-storefront" / "acmestorefront"


# ── frontend ingest ──

def test_ingest_frontend_finds_components_and_skips_glue():
    fe = ingest_frontend(str(_STOREFRONT))
    names = {c["class_name"] for c in fe["components"]}
    assert {"PricingBreakdownComponent", "FulfilmentTrackerComponent"} <= names
    # framework glue / type-only files recorded (not converted), with a reason
    skipped = {s["class_name"]: s for s in fe["skipped"]}
    assert "AcmestorefrontModule" in skipped and skipped["AcmestorefrontModule"]["reason"]


def test_ingest_frontend_extracts_io_and_service_source():
    fe = ingest_frontend(str(_STOREFRONT))
    pdp = next(c for c in fe["components"] if c["class_name"] == "PricingBreakdownComponent")
    assert pdp["layer"] == "Component"
    assert "orderCode" in pdp["inputs"]             # @Input()
    assert "promoApplied" in pdp["outputs"]         # @Output()
    assert "PricingService" in pdp["injected"]
    assert pdp["services_source"]                   # injected service source inlined
    assert pdp["template"] and pdp["source"]


# ── target planning ──

def test_lwc_name_camelcases_and_drops_suffix():
    assert lwc_name("ProductListComponent") == "productList"
    assert lwc_name("CartComponent") == "cart"


def test_plan_targets_maps_component_to_lwc():
    classes = [{"class_name": "ProductListComponent", "layer": "Component",
                "source": "", "template": "", "styles": ""}]
    targets = plan_targets(classes)
    assert len(targets) == 1
    assert targets[0]["target_name"] == "productList"
    assert targets[0]["layer"] == "Component"


# ── LWC generation (mock) ──

def test_generate_lwc_mock_produces_valid_bundle(monkeypatch):
    monkeypatch.setenv("H2A_PROVIDER", "mock")
    component = {"class_name": "ProductDetailComponent", "inputs": ["productCode"],
                 "outputs": ["added"], "source": "", "template": "", "styles": ""}
    out = generate_lwc({"target_name": "productDetail", "component": component}, {}, {})
    b = out["lwc_bundle"]
    assert "extends LightningElement" in b["js"]
    assert "export default class ProductDetail" in b["js"]
    assert "@api productCode" in b["js"]            # @Input → @api
    assert "<template" in b["html"]
    assert "<apiVersion>" in b["meta"] and "<isExposed>" in b["meta"]


# ── LWC validation ──

def test_validate_lwc_flags_template_expression():
    bad = {"js": "export default class X extends LightningElement {}",
           "html": "<template>{ product.price | currency }</template>",
           "meta": "<apiVersion>60.0</apiVersion><isExposed>true</isExposed>"}
    issues = validate_lwc(bad)
    assert any(i["rule"] == "lwc_template_expression" and i["severity"] == "ERROR" for i in issues)


def test_validate_lwc_accepts_property_binding():
    good = {"js": "export default class X extends LightningElement {}",
            "html": "<template><p>{formattedPrice}</p>"
                    "<template for:each={items} for:item=\"i\"><li key={i.code}>{i.name}</li>"
                    "</template></template>",
            "meta": "<apiVersion>60.0</apiVersion><isExposed>true</isExposed>"}
    issues = validate_lwc(good)
    assert not any(i["severity"] == "ERROR" for i in issues)
