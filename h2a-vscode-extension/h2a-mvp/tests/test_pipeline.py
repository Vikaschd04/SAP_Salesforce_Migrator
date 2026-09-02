"""
test_pipeline.py — Complete test suite for h2a-mvp pipeline (Phase 5).
Includes offline mocked tests for Ingestion, LLM client, Comprehend, Generate, and Validator.
"""

import json
from pathlib import Path
import pytest

from src.ingest import ingest
from src.llm import _cache_key
from src.validate import validate_tier1
from src.generate import plan_targets, clean_java_artifacts, extract_method_signatures


# ── Ingest Tests ─────────────────────────────────────────────────────────────

def test_ingestion(tmp_path):
    """Verify that ingest parses classes, layers, public methods, and items.xml."""
    dao_code = """
    package com.example;
    public interface ProductDao {
        ProductModel findByCode(String code);
    }
    """
    (tmp_path / "ProductDao.java").write_text(dao_code, encoding="utf-8")

    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<items>
    <itemtypes>
        <itemtype code="Product">
            <attributes>
                <attribute qualifier="code" type="java.lang.String"/>
                <attribute qualifier="stockLevel" type="java.lang.Integer"/>
            </attributes>
        </itemtype>
    </itemtypes>
</items>
"""
    (tmp_path / "items.xml").write_text(xml_content, encoding="utf-8")

    result = ingest(str(tmp_path))
    
    assert "classes" in result
    assert "item_types" in result
    assert "dependency_order" in result
    
    assert len(result["classes"]) == 1
    dao = result["classes"][0]
    assert dao["class_name"] == "ProductDao"
    assert dao["layer"] == "DAO"
    assert any(m["name"] == "findByCode" for m in dao["methods"])
    
    assert len(result["item_types"]) == 1
    product = result["item_types"][0]
    assert product["name"] == "Product"
    assert any(f["name"] == "stockLevel" for f in product["fields"])



# ── LLM Client Tests ──────────────────────────────────────────────────────────

def test_cache_key():
    """Verify SHA-256 cache key calculation."""
    k1 = _cache_key("test_stage", "test_model", "test_prompt")
    k2 = _cache_key("test_stage", "test_model", "test_prompt")
    k3 = _cache_key("other_stage", "test_model", "test_prompt")
    
    assert len(k1) == 64
    assert k1 == k2
    assert k1 != k3


# ── Validator Tests ───────────────────────────────────────────────────────────

def test_validate_balanced_braces():
    """Verify brace balancing checks."""
    bad_code = "public class A { public void test() { }"
    issues = validate_tier1(bad_code, "A.cls")
    assert any(i["rule"] == "balanced_braces" for i in issues)


def test_validate_soql_in_loop():
    """Verify checker flags SOQL queries inside loops."""
    bad_code = """
    public class ProductService {
        public void badMethod(List<String> codes) {
            for (String code : codes) {
                Product__c p = [SELECT Id FROM Product__c WHERE Code__c = :code LIMIT 1];
            }
        }
    }
    """
    issues = validate_tier1(bad_code, "ProductService.cls")
    assert any(i["rule"] == "soql_in_loop" for i in issues)


def test_validate_dml_in_loop():
    """Verify checker flags DML statements inside loops."""
    bad_code = """
    public class ProductService {
        public void badMethod(List<Product__c> products) {
            for (Product__c p : products) {
                update p;
            }
        }
    }
    """
    issues = validate_tier1(bad_code, "ProductService.cls")
    assert any(i["rule"] == "dml_in_loop" for i in issues)


def test_validate_missing_assert():
    """Verify test classes must have @isTest and System.assert."""
    bad_test = """
    @isTest
    public class ProductServiceTest {
        static void testSomething() {
            // Missing assert!
        }
    }
    """
    issues = validate_tier1(bad_test, "ProductServiceTest.cls")
    assert any(i["rule"] == "missing_assert" for i in issues)


def test_validate_java_syntax_leak():
    """Verify checker flags Java packages, imports, and Spring annotations."""
    java_leaked_code = """
    package com.example.product;
    import java.util.List;
    @Autowired
    public class MyService {
        // ...
    }
    """
    issues = validate_tier1(java_leaked_code, "MyService.cls")
    assert any(i["rule"] == "java_syntax_leak" for i in issues)


# ── Mapping & Generation Tests ────────────────────────────────────────────────

def test_target_planning():
    """Verify planning merges Facade and Service layers and filters appropriately."""
    mock_classes = [
        {"class_name": "ProductData", "layer": "Model"},
        {"class_name": "ProductDao", "layer": "DAO"},
        {"class_name": "DefaultProductService", "layer": "Service"},
        {"class_name": "ProductFacade", "layer": "Facade"},
        {"class_name": "ProductController", "layer": "Controller"},
    ]
    targets = plan_targets(mock_classes)
    
    # 3 target artifacts should be generated
    assert len(targets) == 3
    
    # ProductService target should combine DefaultProductService and ProductFacade
    service_target = next(t for t in targets if t["target_name"] == "ProductService")
    source_names = [c["class_name"] for c in service_target["source_classes"]]
    assert "DefaultProductService" in source_names
    assert "ProductFacade" in source_names


def test_clean_java_artifacts():
    """Verify regex-based Java cleanup converts JUnit asserts and removes Java packages."""
    dirty_code = """
    package com.example.product;
    import java.util.List;
    @Autowired
    public class TestClass {
        public void test() {
            assertEquals("foo", "foo");
            assertTrue(1 > 0);
        }
    }
    """
    clean = clean_java_artifacts(dirty_code)
    
    assert "package " not in clean
    assert "import " not in clean
    assert "@Autowired" not in clean
    assert "System.assertEquals(" in clean
    assert "System.assert(" in clean


def test_clean_java_artifacts_no_double_system_prefix():
    """Already-qualified asserts must not be re-prefixed into System.System.assertEquals."""
    from src.generate import clean_java_artifacts
    code = ("@isTest class T { static void t(){ System.assertEquals(1, 1);"
            " Assert.areEqual(2, 2); assertEquals(3, 3); } }")
    out = clean_java_artifacts(code)
    assert "System.System" not in out
    assert "System.assertEquals(1, 1)" in out       # left intact
    assert "System.assertEquals(3, 3)" in out        # bare form converted once
    # Idempotent: running twice never compounds prefixes.
    assert "System.System" not in clean_java_artifacts(out)


def test_clean_java_artifacts_handles_non_string():
    """A misbehaving provider/proxy returning a dict (not str) must not crash."""
    from src.generate import clean_java_artifacts
    assert clean_java_artifacts({"unexpected": "dict"}) == ""
    assert clean_java_artifacts(None) == ""
    assert clean_java_artifacts("public class X {}") == "public class X {}"


def test_extract_field_rejects_truncated_json():
    """A truncated JSON wrapper must never be returned as Apex (would corrupt a .cls)."""
    from src.generate import _extract_field
    good = '{"test_class": "@isTest class X {}"}'
    assert _extract_field(good, "test_class") == "@isTest class X {}"
    truncated = '{"test_class": "@isTest class X { static void t(){ System.assert'
    assert _extract_field(truncated, "test_class") == ""     # un-salvageable → empty
    assert _extract_field("public class Y {}", "main_class") == "public class Y {}"


def test_extract_method_signatures():
    """Verify that public methods are extracted correctly for dependency injection."""
    apex_code = """
    public with sharing class ProductSelector {
        public static List<Product__c> selectByCode(List<String> codes) {
            return new List<Product__c>();
        }
    }
    """
    sigs = extract_method_signatures(apex_code, "ProductSelector")
    assert len(sigs) == 1
    assert sigs[0] == "ProductSelector.selectByCode(List<String> codes) : List<Product__c>"


def test_metadata_generator(tmp_path):
    """Verify compilation of items.xml configurations into Salesforce DX layouts."""
    from src.metadata_generator import generate_salesforce_metadata
    
    # Create simple items.xml
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<items>
    <itemtypes>
        <itemtype code="TestObj">
            <attributes>
                <attribute qualifier="name" type="java.lang.String"/>
                <attribute qualifier="active" type="java.lang.Boolean"/>
            </attributes>
        </itemtype>
    </itemtypes>
</items>
"""
    items_xml = tmp_path / "items.xml"
    items_xml.write_text(xml_content, encoding="utf-8")
    
    out_dir = tmp_path / "out"
    generate_salesforce_metadata(str(items_xml), str(out_dir))
    
    # Verify outputs
    obj_meta = out_dir / "force-app" / "main" / "default" / "objects" / "TestObj__c" / "TestObj__c.object-meta.xml"
    field_meta = out_dir / "force-app" / "main" / "default" / "objects" / "TestObj__c" / "fields" / "active__c.field-meta.xml"
    
    assert obj_meta.exists()
    assert field_meta.exists()
    assert "<type>Checkbox</type>" in field_meta.read_text(encoding="utf-8")


def test_domain_classifier(tmp_path):
    """Verify that domain_classifier groups Java classes by base prefix modularity."""
    from src.domain_classifier import classify_domains
    
    # Create temp files
    (tmp_path / "DefaultCartService.java").write_text("class DefaultCartService {}", encoding="utf-8")
    (tmp_path / "CartController.java").write_text("class CartController {}", encoding="utf-8")
    (tmp_path / "ProductDao.java").write_text("class ProductDao {}", encoding="utf-8")
    
    domains = classify_domains(str(tmp_path))
    
    assert "Cart" in domains
    assert "Product" in domains
    assert len(domains["Cart"]) == 2
    assert len(domains["Product"]) == 1


def test_repo_analyzer_scheduling(tmp_path):
    """Verify that repo_analyzer successfully tracks domain dependencies and outputs sorted schedule."""
    from src.repo_analyzer import get_translation_schedule
    
    product_file = tmp_path / "ProductDao.java"
    product_file.write_text("class ProductDao {}", encoding="utf-8")
    
    order_file = tmp_path / "DefaultOrderService.java"
    order_file.write_text("class DefaultOrderService { private ProductDao dao; }", encoding="utf-8")
    
    schedule = get_translation_schedule(str(tmp_path))
    
    assert schedule == ["Product", "Order"]


def test_signature_registry():
    """Verify registry maps and propagates signatures cleanly."""
    from src.signature_registry import SignatureRegistry

    reg = SignatureRegistry()
    reg.register("Product", "ProductSelector", ["ProductSelector.selectByCode(String code) : Product__c"])

    flat = reg.get_all_signatures()
    assert "ProductSelector" in flat
    assert flat["ProductSelector"][0] == "ProductSelector.selectByCode(String code) : Product__c"

    # Scoped retrieval only returns signatures for requested domains.
    reg.register("Order", "OrderSelector", ["OrderSelector.selectById(Set<Id> ids) : List<Order__c>"])
    scoped = reg.get_signatures_for_domains({"Product"})
    assert any("ProductSelector" in s for s in scoped)
    assert not any("OrderSelector" in s for s in scoped)


# ── Schema Grounding Tests ────────────────────────────────────────────────────

def test_build_schema():
    from src.schema import build_schema
    item_types = [{"name": "Order", "fields": [
        {"name": "orderId", "type": "java.lang.String"},
        {"name": "totalAmount", "type": "java.math.BigDecimal"},
    ]}]
    schema = build_schema(item_types)
    assert "Order__c" in schema
    assert schema["Order__c"]["fields"]["OrderId__c"] == "Text"
    assert schema["Order__c"]["fields"]["TotalAmount__c"] == "Currency"


def test_schema_field_validation_flags_unknown():
    from src.schema import build_schema, validate_field_references
    schema = build_schema([{"name": "Order", "fields": [
        {"name": "orderId", "type": "java.lang.String"}]}])
    good = "List<Order__c> o = [SELECT Id, OrderId__c FROM Order__c];"
    bad = "List<Order__c> o = [SELECT Id, Bogus__c FROM Order__c];"
    assert validate_field_references(good, schema) == []
    issues = validate_field_references(bad, schema)
    assert any(i["rule"] == "unknown_field" for i in issues)


def test_schema_flags_unknown_object():
    from src.schema import build_schema, validate_field_references
    schema = build_schema([{"name": "Order", "fields": []}])
    issues = validate_field_references("Ghost__c g = new Ghost__c();", schema)
    assert any(i["rule"] == "unknown_sobject" for i in issues)


# ── Mock provider + structured output ─────────────────────────────────────────

def test_mock_generate_structured(monkeypatch, tmp_path):
    monkeypatch.setenv("H2A_PROVIDER", "mock")
    monkeypatch.setenv("H2A_INCREMENTAL", "false")
    from src.generate import generate_apex
    target = {"target_name": "ProductSelector", "layer": "DAO",
              "source_classes": [{"class_name": "ProductDao", "layer": "DAO",
                                  "source": "public interface ProductDao {}"}]}
    result = generate_apex(target, {}, [], schema={})
    assert result["provider"] == "mock"
    assert "class ProductSelector" in result["main_class"]
    assert "@isTest" in result["test_class"]
    # Mock output must itself pass tier-1 validation.
    assert validate_tier1(result["main_class"], "ProductSelector.cls") == []
    assert validate_tier1(result["test_class"], "ProductSelectorTest.cls") == []


def test_schema_directive_lists_keys():
    from src.llm import _schema_directive
    from src.generate import GENERATION_SCHEMA
    d = _schema_directive(GENERATION_SCHEMA)
    assert "main_class" in d and "test_class" in d and "JSON" in d
    assert _schema_directive({}) == ""  # no schema → no directive


def test_openrouter_provider_adapter(monkeypatch, tmp_path):
    """OpenRouter path builds a chat request and parses the response (stubbed client)."""
    monkeypatch.setenv("H2A_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("H2A_CUSTOM_MODEL", "some/free-model:free")

    captured = {}

    class _Msg:
        content = '{"purpose": "adapter test", "inputs": [], "outputs": [], ' \
                  '"side_effects": [], "queries": [], "business_rules": []}'

    class _Choice:
        message = _Msg()

    class _Usage:
        prompt_tokens = 100
        completion_tokens = 20

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return _Resp()

    import src.llm as llm
    llm._or_client = None
    llm.reset_accounting()
    monkeypatch.setattr(llm, "_openrouter_client", lambda key, base_url: _FakeClient())
    monkeypatch.setattr(llm, "_cache_dir", lambda config: tmp_path / "cache")  # isolate cache

    from src.comprehend import comprehend_class
    result = comprehend_class(
        {"class_name": "FooDao", "layer": "DAO", "methods": [],
         "referenced_types": [], "source": "public interface FooDao {}"})

    # Request was built correctly and the JSON response parsed.
    assert captured["model"] == "some/free-model:free"
    assert captured["messages"][-1]["role"] == "user"
    assert result["purpose"] == "adapter test"
    # Accounting recorded the openrouter request + tokens.
    from src.llm import get_accounting
    acct = get_accounting()
    assert acct["providers"].get("openrouter", 0) >= 1


# ── Schema reconciliation (auto-resolve warnings) ─────────────────────────────

def test_reconcile_adds_evidenced_field():
    """A field used in the Hybris source but missing from items.xml is auto-added."""
    from src.schema import build_schema, reconcile_schema
    schema = build_schema([{"name": "Order", "fields": [
        {"name": "code", "type": "java.lang.String"}]}])
    validation = {"OrderSelector.cls": [{
        "rule": "unknown_field", "severity": "WARNING",
        "object": "Order__c", "field": "DealerCode__c",
        "message": "SOQL selects 'DealerCode__c' from Order__c ..."}]}
    source = "public interface OrderDao { Order findByDealerCode(String dealerCode); }"

    augmented, info = reconcile_schema(schema, validation, source)
    assert "DealerCode__c" in augmented["Order__c"]["fields"]
    assert any(f["field"] == "DealerCode__c" for f in info["added_fields"])
    assert info["flagged"] == []


def test_reconcile_flags_hallucinated_field():
    """A field with no source evidence is flagged, not added."""
    from src.schema import build_schema, reconcile_schema
    schema = build_schema([{"name": "Order", "fields": []}])
    validation = {"OrderSelector.cls": [{
        "rule": "unknown_field", "severity": "WARNING",
        "object": "Order__c", "field": "Wizbang__c", "message": "..."}]}
    source = "public interface OrderDao { Order findByCode(String code); }"

    augmented, info = reconcile_schema(schema, validation, source)
    assert "Wizbang__c" not in augmented["Order__c"]["fields"]
    assert any(f["field"] == "Wizbang__c" for f in info["flagged"])
    assert info["added_fields"] == []


def test_write_schema_metadata(tmp_path):
    """Reconciled schema (incl. auto-added fields) is emitted as SObject metadata."""
    from src.metadata_generator import write_schema_metadata
    schema = {"Order__c": {"code": "Order", "fields": {
        "Code__c": "Text", "TotalAmount__c": "Currency", "DealerCode__c": "Text"}}}
    written = write_schema_metadata(str(tmp_path), schema)

    obj = tmp_path / "force-app/main/default/objects/Order__c/Order__c.object-meta.xml"
    dealer = tmp_path / "force-app/main/default/objects/Order__c/fields/DealerCode__c.field-meta.xml"
    assert obj.exists() and dealer.exists()
    assert "<type>Text</type>" in dealer.read_text(encoding="utf-8")
    assert any("Order__c.object-meta.xml" in w for w in written)


# ── Behavioral parity harness ─────────────────────────────────────────────────

def test_parity_scores_rule_assertions():
    """Parity marks a rule covered only when the test asserts its distinctive terms."""
    from src.parity import build_parity
    generated = [{
        "target_name": "OrderService", "layer": "Service",
        "source_classes": [{"class_name": "OrderService"}],
        "main_class": "public with sharing class OrderService { public static void x(){} }",
        "business_rules": [
            "Order total must equal the sum of line item amounts",
            "Cancelled orders cannot be refunded",
        ],
        "test_class": (
            "@isTest class OrderServiceTest {"
            " static testMethod void t(){ System.assertEquals(total, sum, 'order total sum line item'); } }"),
    }]
    parity = build_parity(generated)
    t = parity["targets"][0]
    rules = {r["rule"]: r["covered"] for r in t["rules"]}
    assert rules["Order total must equal the sum of line item amounts"] is True
    assert rules["Cancelled orders cannot be refunded"] is False
    assert parity["overall"]["rules_total"] == 2
    assert parity["overall"]["rules_covered"] == 1


def test_close_parity_gaps(monkeypatch, tmp_path):
    """close_parity_gaps feeds uncovered rules to the LLM and re-scores to green."""
    import src.generate as generate
    from src.parity import close_parity_gaps, build_parity

    (tmp_path / "force-app/main/default/classes").mkdir(parents=True)
    generated = [{
        "target_name": "OrderService", "source_classes": [],
        "main_class": "public with sharing class OrderService {}",
        "business_rules": ["An order total must be greater than zero",
                           "Orders with priority above five are expedited"],
        "test_class": "@isTest class OrderServiceTest { @isTest static void t(){ System.assert(true); } }",
    }]
    # Stub the LLM: return a test that now asserts BOTH rules' distinctive words.
    strengthened = ("@isTest class OrderServiceTest { @isTest static void t(){"
                    " System.assert(total > 0, 'order total greater zero');"
                    " System.assert(expedited, 'priority above five expedited'); } }")
    monkeypatch.setattr(generate, "strengthen_parity", lambda *a, **k: strengthened)

    before = build_parity(generated)["overall"]
    summary = close_parity_gaps(generated, str(tmp_path), max_attempts=1, log=lambda *a: None)
    after = build_parity(generated)["overall"]

    assert before["rules_covered"] == 0
    assert after["rules_covered"] == 2          # both rules now asserted
    assert summary["rules_closed"] == 2
    assert "OrderService" in summary["targets_improved"]
    assert (tmp_path / "force-app/main/default/classes/OrderServiceTest.cls").exists()


def test_parity_uncovered_without_assertions(tmp_path):
    """No assertions in the test → no rule counts as covered, and PARITY.md writes."""
    from src.parity import build_parity, write_parity_md
    generated = [{
        "target_name": "OrderService", "source_classes": [],
        "main_class": "public class OrderService {}",
        "business_rules": ["Order total must equal sum of line items"],
        "test_class": "@isTest class OrderServiceTest { static void t(){ } }",  # no assert
    }]
    parity = build_parity(generated)
    assert parity["overall"]["rules_covered"] == 0
    assert parity["overall"]["targets_with_tests"] == 0
    path = write_parity_md(str(tmp_path), parity)
    assert (tmp_path / "PARITY.md").exists()
    assert "strengthen test" in Path(path).read_text(encoding="utf-8")


# ── Self-healing deploy loop ──────────────────────────────────────────────────

def test_errors_to_issues():
    """Deploy component failures convert into the issue shape repair() expects."""
    from src.verify import _errors_to_issues
    issues = _errors_to_issues([
        {"file": "force-app/.../FooService.cls", "line": 12, "problem": "Variable does not exist: bar"},
        {"file": "force-app/.../FooService.cls", "line": None, "problem": "Method does not exist"},
    ])
    assert len(issues) == 2
    assert issues[0]["severity"] == "ERROR"
    assert issues[0]["rule"] == "deploy_error"
    assert "Line 12" in issues[0]["message"] and "bar" in issues[0]["message"]
    assert issues[1]["message"] == "Method does not exist"  # no line prefix


def test_deploy_and_heal_repairs_and_redeploys(monkeypatch, tmp_path):
    """A failing deploy feeds real errors to repair, rewrites the class, re-deploys green."""
    import src.verify as verify
    import src.validate as validate

    classes_dir = tmp_path / "force-app" / "main" / "default" / "classes"
    classes_dir.mkdir(parents=True)
    broken = "public class FooService { void m(){ bar; } }"
    fixed = "public with sharing class FooService { void m(){ } }"
    (classes_dir / "FooService.cls").write_text(broken, encoding="utf-8")

    generated = [{"target_name": "FooService", "main_class": broken, "test_class": "@isTest class X{}"}]

    calls = {"n": 0}

    def fake_deploy_check(output_dir, target_org=None, run_tests=False):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"available": True, "ran": True, "success": False, "coverage": None,
                    "errors": [{"file": "force-app/main/default/classes/FooService.cls",
                                "line": 1, "problem": "Variable does not exist: bar"}],
                    "message": "1 component failure(s)."}
        return {"available": True, "ran": True, "success": True, "coverage": 92.0,
                "errors": [], "message": "Compiled cleanly."}

    def fake_repair(code, issues, **kwargs):
        assert any("bar" in i["message"] for i in issues)  # grounded in the real error
        return fixed

    monkeypatch.setattr(verify, "deploy_check", fake_deploy_check)
    monkeypatch.setattr(validate, "repair", fake_repair)

    result = verify.deploy_and_heal(str(tmp_path), generated, max_attempts=2, log=lambda *a: None)

    assert result["success"] is True
    assert result["healing"]["healed_files"] == ["FooService.cls"]
    assert (classes_dir / "FooService.cls").read_text(encoding="utf-8") == fixed
    assert generated[0]["main_class"] == fixed        # in-memory updated for the report
    assert calls["n"] == 2                             # deploy → repair → re-deploy


def test_deploy_and_heal_no_org_is_noop(monkeypatch, tmp_path):
    """With no authorised org, heal returns the verdict untouched and never repairs."""
    import src.verify as verify
    import src.validate as validate

    repaired = {"called": False}
    monkeypatch.setattr(validate, "repair", lambda *a, **k: repaired.__setitem__("called", True))
    monkeypatch.setattr(verify, "deploy_check", lambda *a, **k: {
        "available": True, "ran": False, "success": False, "errors": [],
        "coverage": None, "message": "No authorised Salesforce org."})

    generated = [{"target_name": "FooService", "main_class": "x", "test_class": "y"}]
    result = verify.deploy_and_heal(str(tmp_path), generated, log=lambda *a: None)

    assert result["ran"] is False
    assert result["healing"]["rounds"] == []
    assert repaired["called"] is False


def test_confidence_scoring():
    """Confidence is capped without an org and elevated by a clean org deploy."""
    from src.report import _compute_confidence
    generated = [{"target_name": "FooService"}]
    clean_validation = {"FooService.cls": [], "FooServiceTest.cls": []}

    # No verification at all → capped at 75 (never presented as certain).
    unverified = _compute_confidence(generated, clean_validation, None)["FooService"]
    assert unverified["score"] <= 75

    # Clean org deploy → High.
    ok = _compute_confidence(generated, clean_validation,
                             {"available": True, "ran": True, "success": True, "errors": []})["FooService"]
    assert ok["label"] == "High" and ok["score"] >= 85

    # Failed org deploy on this file → Low.
    bad = _compute_confidence(generated, clean_validation, {
        "available": True, "ran": True, "success": False,
        "errors": [{"file": "force-app/main/default/classes/FooService.cls",
                    "line": 1, "problem": "boom"}]})["FooService"]
    assert bad["label"] == "Low" and bad["score"] <= 45


# ── Type inference, metadata healing, coverage healing ────────────────────────

def test_infer_field_type():
    """Auto-added field types are inferred from the Java source, not defaulted."""
    from src.schema import infer_field_type
    src = ("public interface OrderDao {"
           " BigDecimal getDealerFee(); boolean getActive(); Integer stockLevel; }")
    assert infer_field_type("DealerFee__c", src) == "Currency"
    assert infer_field_type("Active__c", src) == "Checkbox"
    assert infer_field_type("StockLevel__c", src) == "Number"
    assert infer_field_type("Nowhere__c", src) == "Text"   # no evidence → safe default


def test_parse_metadata_errors():
    """Missing-field/object deploy errors are recognised for metadata healing."""
    from src.verify import _parse_metadata_errors
    errs = [
        {"problem": "No such column 'DealerCode__c' on entity 'Order__c'."},
        {"problem": "sObject type 'Ghost__c' is not supported."},
        {"problem": "Variable does not exist: bar"},   # not a metadata error
    ]
    targets = _parse_metadata_errors(errs)
    assert {"object": "Order__c", "field": "DealerCode__c", "kind": "field"} in targets
    assert {"object": "Ghost__c", "field": None, "kind": "object"} in targets
    assert len(targets) == 2


def test_metadata_self_healing(monkeypatch, tmp_path):
    """A 'no such column' deploy error adds the evidenced field to schema+metadata."""
    import src.verify as verify
    import src.validate as validate

    (tmp_path / "force-app/main/default/classes").mkdir(parents=True)
    schema = {"Order__c": {"code": "Order", "fields": {}}}
    source = "public interface OrderDao { BigDecimal getDealerCode(); }"
    generated = [{"target_name": "OrderService",
                  "main_class": "public class OrderService { void m(){ Order__c o; o.DealerCode__c=1; } }",
                  "test_class": "@isTest class OrderServiceTest{}"}]

    calls = {"n": 0}
    def fake_deploy_check(output_dir, target_org=None, run_tests=False):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"available": True, "ran": True, "success": False, "coverage": None,
                    "per_class_coverage": [], "message": "1 failure",
                    "errors": [{"file": "force-app/main/default/classes/OrderService.cls",
                                "line": 1, "problem": "No such column 'DealerCode__c' on entity 'Order__c'."}]}
        return {"available": True, "ran": True, "success": True, "coverage": None,
                "per_class_coverage": [], "errors": [], "message": "clean"}

    repair_called = {"v": False}
    monkeypatch.setattr(verify, "deploy_check", fake_deploy_check)
    monkeypatch.setattr(validate, "repair", lambda *a, **k: repair_called.__setitem__("v", True) or "x")

    result = verify.deploy_and_heal(str(tmp_path), generated, schema=schema,
                                    source_corpus=source, max_attempts=2, log=lambda *a: None)

    assert result["success"] is True
    assert schema["Order__c"]["fields"].get("DealerCode__c") == "Currency"   # inferred, not Text
    assert "Order__c.DealerCode__c" in result["healing"]["healed_metadata"]
    assert repair_called["v"] is False   # metadata fix, not an Apex repair
    field_meta = tmp_path / "force-app/main/default/objects/Order__c/fields/DealerCode__c.field-meta.xml"
    assert field_meta.exists()


def test_coverage_self_healing(monkeypatch, tmp_path):
    """Compiles but under 75% → tests are strengthened and re-deployed to green."""
    import src.verify as verify
    import src.generate as generate

    classes_dir = tmp_path / "force-app/main/default/classes"
    classes_dir.mkdir(parents=True)
    (classes_dir / "OrderServiceTest.cls").write_text("@isTest class OrderServiceTest{}", encoding="utf-8")
    generated = [{"target_name": "OrderService",
                  "main_class": "public class OrderService { public static void m(){} }",
                  "test_class": "@isTest class OrderServiceTest{}"}]

    calls = {"n": 0}
    def fake_deploy_check(output_dir, target_org=None, run_tests=False):
        calls["n"] += 1
        cov = 50.0 if calls["n"] == 1 else 92.0
        return {"available": True, "ran": True, "success": True, "coverage": cov,
                "per_class_coverage": [{"name": "OrderService", "coverage": cov}],
                "errors": [], "message": "ok"}

    monkeypatch.setattr(verify, "deploy_check", fake_deploy_check)
    monkeypatch.setattr(generate, "strengthen_tests",
                        lambda *a, **k: "@isTest class OrderServiceTest{ @isTest static void t(){ System.assert(true); } }")

    result = verify.deploy_and_heal(str(tmp_path), generated, run_tests=True,
                                    coverage_threshold=75.0, max_attempts=3, log=lambda *a: None)

    assert result["success"] is True
    assert result["coverage"] == 92.0
    assert "OrderServiceTest.cls" in result["healing"]["coverage_strengthened"]
    assert "System.assert" in generated[0]["test_class"]   # in-memory updated


# ── Agentic core (Phase 1) ────────────────────────────────────────────────────

def test_blackboard_and_plan():
    from src.agentic.blackboard import Blackboard, PlanItem, Artifact
    bb = Blackboard(input_dir="i", output_dir="o")
    bb.plan = [PlanItem("A", "DAO", "D", target_kind="Convert", apex_pattern="Selector"),
               PlanItem("B", "Service", "D", target_kind="Convert", native_recommendation="CPQ"),
               PlanItem("C", "Utility", "D", target_kind="Skip", rationale="pure DTO")]
    # Everything Convert is built (incl. the CPQ-flagged one); only Skip is excluded.
    assert [p.target_name for p in bb.code_plan()] == ["A", "B"]
    bb.record("Planner", "planned", "x")
    assert bb.decisions[0]["agent"] == "Planner"
    bb.artifacts.append(Artifact("A", "DAO", main_class="m", test_class="t"))
    g = bb.generated_dicts()[0]
    assert g["target_name"] == "A" and g["main_class"] == "m"


def test_router_tiers():
    from src.agentic.router import route_model
    cfg = {"agentic": {"routing": {"enabled": True,
           "models": {"cheap": "c", "frontier": "f"},
           "tiers": {"comprehend": "cheap", "generate": "frontier"}}}}
    assert route_model(cfg, "comprehend_Foo") == "c"
    assert route_model(cfg, "generate_Foo") == "f"
    assert route_model(cfg, "plan_repo") == "c"                 # default tier: plan=cheap
    assert route_model({"agentic": {"routing": {"enabled": False}}}, "comprehend_x") is None
    assert route_model({}, "generate_x") is None                # no routing config → default


def test_planner_deterministic_fallback(monkeypatch):
    """Under mock, the Planner marks every structural target as Convert (all built)."""
    monkeypatch.setenv("H2A_PROVIDER", "mock")
    from src.agentic.blackboard import Blackboard
    from src.agentic.planner import PlannerAgent
    bb = Blackboard(input_dir="i", output_dir="o")
    bb.schedule = ["Order"]
    bb.domains = {"Order": [{"class_name": "DefaultOrderService", "layer": "Service"}]}
    bb.all_classes = [{"class_name": "DefaultOrderService", "layer": "Service",
                       "source": "class DefaultOrderService {}", "methods": []}]
    PlannerAgent().run(bb)
    assert bb.plan and all(p.target_kind == "Convert" for p in bb.plan)
    assert any(d["agent"] == "Planner" for d in bb.decisions)


def test_planner_llm_converts_and_flags_native(monkeypatch):
    """With a real provider (stubbed), pricing logic is CONVERTED to Apex and flagged
    for a native product (CPQ) — never skipped."""
    import src.agentic.planner as planner
    monkeypatch.setattr(planner, "_get_provider", lambda cfg: "anthropic")
    monkeypatch.setattr(planner, "call_structured", lambda *a, **k: {"parsed": {"decisions": [
        {"target_name": "OrderService", "target_kind": "Convert",
         "rationale": "pricing logic", "native_recommendation": "Salesforce CPQ"}]}})

    from src.agentic.blackboard import Blackboard
    bb = Blackboard(input_dir="i", output_dir="o")
    bb.schedule = ["Order"]
    bb.domains = {"Order": [{"class_name": "DefaultOrderService", "layer": "Service"}]}
    bb.all_classes = [{"class_name": "DefaultOrderService", "layer": "Service",
                       "source": "class DefaultOrderService {}", "methods": []}]
    planner.PlannerAgent().run(bb)

    item = next(p for p in bb.plan if p.target_name == "OrderService")
    assert item.target_kind == "Convert"
    assert item.native_recommendation == "Salesforce CPQ"
    assert [p.target_name for p in bb.code_plan()] == ["OrderService"]   # converted, not skipped
    assert any("CPQ" in q for q in bb.open_questions)


def test_critic_flags_governor_violation(monkeypatch):
    """The Critic's objective floor flags a real governor problem even under mock."""
    monkeypatch.setenv("H2A_PROVIDER", "mock")
    from src.agentic.blackboard import Artifact
    from src.agentic.critic import CriticAgent
    bad = Artifact("OrderService", "Service", main_class=(
        "public with sharing class OrderService {\n"
        "    public static void m(List<String> cs){\n"
        "        for (String c : cs){\n"
        "            Order__c o = [SELECT Id FROM Order__c WHERE Code__c = :c];\n"
        "        }\n"
        "    }\n"
        "}"),
        test_class="@isTest class OrderServiceTest { @isTest static void t(){ System.assert(true); } }")
    findings = CriticAgent().review(bad, {}, offline=False)
    assert any(f["category"] == "soql_in_loop" and f["severity"] == "ERROR" for f in findings)


def test_agentic_end_to_end_mock(monkeypatch, tmp_path):
    """Full agentic migration via mock: plan doc, classes, report; all valid."""
    monkeypatch.setenv("H2A_PROVIDER", "mock")
    monkeypatch.setenv("H2A_INCREMENTAL", "false")

    src_dir = tmp_path / "hy"
    src_dir.mkdir()
    (src_dir / "AccountDao.java").write_text(
        "package d;\npublic interface AccountDao { AccountModel findByCode(String code); }", encoding="utf-8")
    (src_dir / "DefaultAccountService.java").write_text(
        "package s;\npublic class DefaultAccountService { private AccountDao accountDao;\n"
        "  public AccountModel get(String c){ return accountDao.findByCode(c); } }", encoding="utf-8")
    (src_dir / "items.xml").write_text(
        '<?xml version="1.0"?><items><itemtypes><itemtype code="Account">'
        '<attributes><attribute qualifier="code" type="java.lang.String"/>'
        '</attributes></itemtype></itemtypes></items>', encoding="utf-8")

    out_dir = tmp_path / "out"
    from src.agentic import run_agentic_migration
    bb = run_agentic_migration(str(src_dir), str(out_dir))

    classes = out_dir / "force-app" / "main" / "default" / "classes"
    assert (classes / "AccountSelector.cls").exists()
    assert (classes / "AccountService.cls").exists()
    assert (out_dir / "MIGRATION_PLAN.md").exists()
    assert (out_dir / "FEASIBILITY_REPORT.md").exists()
    assert all(a.status == "accepted" for a in bb.artifacts)     # critic accepted the stubs

    from src.validate import validate_all
    for f in classes.glob("*.cls"):
        errs = [i for i in validate_all(f.read_text(encoding="utf-8"), f.name, bb.schema)
                if i["severity"] == "ERROR"]
        assert errs == [], f"{f.name}: {errs}"


# ── Deeper items.xml metadata: enums→picklists, required/unique (Phase 2) ─────

def test_ingest_enum_and_modifiers(tmp_path):
    from src.ingest import ingest
    (tmp_path / "MyDao.java").write_text("public interface MyDao {}", encoding="utf-8")
    (tmp_path / "items.xml").write_text(
        '<?xml version="1.0"?><items>'
        '<enumtypes><enumtype code="OrderStatus">'
        '<value code="NEW"/><value code="SHIPPED"/></enumtype></enumtypes>'
        '<itemtypes><itemtype code="Order"><attributes>'
        '<attribute qualifier="code" type="java.lang.String"><modifiers unique="true" optional="false"/></attribute>'
        '<attribute qualifier="status" type="OrderStatus"><defaultvalue>NEW</defaultvalue></attribute>'
        '</attributes></itemtype></itemtypes></items>', encoding="utf-8")
    res = ingest(str(tmp_path))
    assert res["enum_types"] == [{"name": "OrderStatus", "values": ["NEW", "SHIPPED"]}]
    order = res["item_types"][0]
    code_f = next(f for f in order["fields"] if f["name"] == "code")
    assert code_f["modifiers"].get("unique") == "true"
    status_f = next(f for f in order["fields"] if f["name"] == "status")
    assert status_f["default"] == "NEW"


def test_build_schema_picklist_and_constraints():
    from src.schema import build_schema
    item_types = [{"name": "Order", "fields": [
        {"name": "code", "type": "java.lang.String",
         "modifiers": {"unique": "true", "optional": "false"}},
        {"name": "status", "type": "OrderStatus", "default": "NEW", "modifiers": {}}]}]
    enums = [{"name": "OrderStatus", "values": ["NEW", "SHIPPED"]}]
    o = build_schema(item_types, enum_types=enums)["Order__c"]
    assert o["fields"]["Status__c"] == "Picklist"
    assert o["picklists"]["Status__c"] == ["NEW", "SHIPPED"]
    assert "Code__c" in o["required"] and "Code__c" in o["unique"]
    assert o["defaults"]["Status__c"] == "NEW"


def test_metadata_emits_picklist_and_constraints(tmp_path):
    from src.metadata_generator import write_schema_metadata
    schema = {"Order__c": {"code": "Order",
              "fields": {"Status__c": "Picklist", "Code__c": "Text"},
              "picklists": {"Status__c": ["NEW", "SHIPPED"]},
              "required": {"Code__c"}, "unique": {"Code__c"}, "defaults": {"Status__c": "NEW"}}}
    write_schema_metadata(str(tmp_path), schema)
    base = tmp_path / "force-app/main/default/objects/Order__c/fields"
    status = (base / "Status__c.field-meta.xml").read_text(encoding="utf-8")
    assert "<type>Picklist</type>" in status
    assert "<fullName>NEW</fullName><default>true</default>" in status
    assert "<fullName>SHIPPED</fullName><default>false</default>" in status
    code = (base / "Code__c.field-meta.xml").read_text(encoding="utf-8")
    assert "<required>true</required>" in code and "<unique>true</unique>" in code


# ── Cronjob → Scheduled Apex (Phase 2) ────────────────────────────────────────

_SAMPLE_SPRING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans">
    <bean id="orderCleanupJobPerformable" class="com.store.order.OrderCleanupJob" parent="abstractJobPerformable">
        <property name="orderDao" ref="orderDao"/>
    </bean>
    <bean id="orderCleanupCronJob" parent="cronJob">
        <property name="job" ref="orderCleanupJobPerformable"/>
    </bean>
    <bean id="orderCleanupTrigger" class="de.hybris.platform.cronjob.model.TriggerModel">
        <property name="cronJob" ref="orderCleanupCronJob"/>
        <property name="cronExpression" value="0 0 2 * * ?"/>
        <property name="active" value="true"/>
    </bean>
</beans>
"""


def test_ingest_detects_job_layer(tmp_path):
    """A class extending AbstractJobPerformable is classified as layer 'Job'."""
    from src.ingest import ingest
    (tmp_path / "OrderCleanupJob.java").write_text(
        "package com.store.order;\n"
        "public class OrderCleanupJob extends AbstractJobPerformable<CronJobModel> {\n"
        "  public PerformResult perform(CronJobModel cronJob) { return null; }\n"
        "}\n", encoding="utf-8")
    res = ingest(str(tmp_path))
    job = next(c for c in res["classes"] if c["class_name"] == "OrderCleanupJob")
    assert job["layer"] == "Job"


def test_plan_targets_job_becomes_scheduler():
    from src.generate import plan_targets
    classes = [{"class_name": "OrderCleanupJob", "layer": "Job"}]
    targets = plan_targets(classes)
    assert len(targets) == 1
    assert targets[0]["target_name"] == "OrderCleanupScheduler"


def test_translate_cron_passthrough_and_warnings():
    from src.cronjob import translate_cron
    expr, warnings = translate_cron("0 0 2 * * ?")
    assert expr == "0 0 2 * * ?" and warnings == []
    # Both day-of-month and day-of-week concrete -> Salesforce/Quartz violation.
    _, warnings = translate_cron("0 0 2 15 * MON")
    assert warnings and "day-of-month" in warnings[0].lower()
    # Wrong field count.
    _, warnings = translate_cron("0 0 2")
    assert warnings


def test_parse_spring_triggers_resolves_chain():
    from src.cronjob import parse_spring_triggers
    triggers = parse_spring_triggers(_SAMPLE_SPRING_XML, source="store-jobs-spring.xml")
    assert len(triggers) == 1
    t = triggers[0]
    assert t.job_class == "OrderCleanupJob"
    assert t.cron_expression == "0 0 2 * * ?"
    assert t.resolved is True and t.active is True


def test_parse_impex_triggers():
    from src.cronjob import parse_impex_triggers
    text = (
        "INSERT_UPDATE Trigger;cronJob(code)[unique=true];cronExpression;active\n"
        ";NightlyCleanupJob;0 0 3 * * ?;true\n"
    )
    triggers = parse_impex_triggers(text, source="jobs.impex")
    assert len(triggers) == 1
    assert triggers[0].job_class == "NightlyCleanupJob"
    assert triggers[0].cron_expression == "0 0 3 * * ?"


def test_write_cron_runbook(tmp_path):
    from src.cronjob import parse_spring_triggers, write_cron_runbook
    triggers = parse_spring_triggers(_SAMPLE_SPRING_XML, source="x.xml")
    written = write_cron_runbook(str(tmp_path), triggers)
    runbook = (tmp_path / "CRON_JOBS.md").read_text(encoding="utf-8")
    assert "OrderCleanupScheduler" in runbook and "0 0 2 * * ?" in runbook
    apex = (tmp_path / "schedule.apex").read_text(encoding="utf-8")
    assert "System.schedule('OrderCleanupScheduler'" in apex
    assert any("CRON_JOBS.md" in w for w in written)


def test_translate_cronjobs_dir_finds_spring_and_impex(tmp_path):
    from src.cronjob import translate_cronjobs_dir
    src = tmp_path / "src"
    src.mkdir()
    (src / "jobs-spring.xml").write_text(_SAMPLE_SPRING_XML, encoding="utf-8")
    out = tmp_path / "out"
    summary = translate_cronjobs_dir(str(src), str(out))
    assert summary["resolved_count"] == 1
    assert (out / "CRON_JOBS.md").exists()


# ── ImpEx → Salesforce data migration (Phase 2) ───────────────────────────────

_SAMPLE_IMPEX = """# seed data
$catalog=demoCatalog

INSERT_UPDATE Customer;uid[unique=true];name
;alice@example.com;Alice
;bob@example.com;Bob

INSERT_UPDATE Order;code[unique=true];totalAmount;customer(uid);categories(catalog(id),code)
;ORD-1;149.99;alice@example.com;xyz
"""


def test_parse_impex():
    from src.impex import parse_impex
    blocks = parse_impex(_SAMPLE_IMPEX)
    assert [b.type_code for b in blocks] == ["Customer", "Order"]
    cust = blocks[0]
    assert cust.mode == "INSERT_UPDATE"
    assert cust.columns[0].attr == "uid" and cust.columns[0].is_unique
    assert len(cust.rows) == 2 and cust.rows[0]["uid"] == "alice@example.com"
    order = blocks[1]
    ref = next(c for c in order.columns if c.attr == "customer")
    assert ref.is_reference and ref.ref_key == "uid" and not ref.composite
    comp = next(c for c in order.columns if c.attr == "categories")
    assert comp.is_reference and comp.composite     # nested → not auto-mappable


def test_impex_data_plan():
    from src.impex import parse_impex, build_data_plan
    plan = {o.type_code: o for o in build_data_plan(parse_impex(_SAMPLE_IMPEX))}
    cust = plan["Customer"]
    assert cust.object_api == "Customer__c" and cust.external_id == "Uid__c"
    assert cust.headers == ["Uid__c", "Name__c"]
    order = plan["Order"]
    assert order.external_id == "Code__c"
    assert "Customer__r.Uid__c" in order.headers       # single-key ref → relationship column
    assert order.manual_relationships                    # composite ref flagged for manual mapping


def test_impex_csv_and_runbook(tmp_path):
    from src.impex import parse_impex, build_data_plan, write_data_migration
    plan = build_data_plan(parse_impex(_SAMPLE_IMPEX))
    write_data_migration(str(tmp_path), plan)
    csv_text = (tmp_path / "data" / "Customer__c.csv").read_text(encoding="utf-8")
    assert "Uid__c,Name__c" in csv_text and "alice@example.com,Alice" in csv_text
    runbook = (tmp_path / "DATA_MIGRATION.md").read_text(encoding="utf-8")
    assert "sf data upsert bulk --sobject Customer__c" in runbook
    assert "--external-id Uid__c" in runbook


def test_impex_marks_external_id_metadata(tmp_path):
    from src.impex import parse_impex, build_data_plan, mark_external_id_fields
    fdir = tmp_path / "force-app/main/default/objects/Customer__c/fields"
    fdir.mkdir(parents=True)
    (fdir / "Uid__c.field-meta.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<CustomField xmlns="x">\n'
        '    <fullName>Uid__c</fullName>\n    <type>Text</type>\n</CustomField>\n', encoding="utf-8")
    plan = build_data_plan(parse_impex(_SAMPLE_IMPEX))
    patched = mark_external_id_fields(str(tmp_path), plan)
    xml = (fdir / "Uid__c.field-meta.xml").read_text(encoding="utf-8")
    assert "<externalId>true</externalId>" in xml and "<unique>true</unique>" in xml
    assert any("Uid__c" in p for p in patched)


def test_translate_impex_dir(tmp_path):
    from src.impex import translate_impex_dir
    src = tmp_path / "src"
    src.mkdir()
    (src / "data.impex").write_text(_SAMPLE_IMPEX, encoding="utf-8")
    out = tmp_path / "out"
    summary = translate_impex_dir(str(src), str(out))
    assert summary["record_total"] == 3
    assert {o["object"] for o in summary["objects"]} == {"Customer__c", "Order__c"}
    assert (out / "data" / "Order__c.csv").exists()


# ── RAG scaffold (retrieval grounding) ────────────────────────────────────────

def test_retriever_relevance():
    """The lexical retriever returns the topically-correct bundled doc chunk."""
    from src.agentic.retriever import Retriever
    r = Retriever()
    assert r.available and r.n_chunks > 0
    cases = {
        "selector that owns SOQL for one object": "fflib_patterns.md",
        "how much code coverage to deploy to production": "apex_testing.md",
        "strip inaccessible fields field level security": "soql_security.md",
        "SOQL query inside a for loop governor limit": "governor_limits.md",
    }
    for query, expected_doc in cases.items():
        hits = r.retrieve(query, 1)
        assert hits and hits[0].doc == expected_doc, f"{query!r} → {hits[0].doc if hits else None}"


def test_retriever_grounding_block():
    from src.agentic.retriever import Retriever
    block = Retriever().grounding_block("bulkify avoid SOQL in loop", 2)
    assert "Salesforce reference" in block and "loop" in block.lower()


def test_build_retriever_factory():
    from src.agentic.retriever import build_retriever
    assert build_retriever({"agentic": {"rag": {"enabled": False}}}) is None
    assert build_retriever({}) is None
    r = build_retriever({"agentic": {"rag": {"enabled": True, "top_k": 2}}})
    assert r is not None and r.top_k == 2


def test_grounding_reaches_generation_prompt(monkeypatch):
    """A grounding block passed to generate_apex is injected into the LLM prompt."""
    import src.generate as g
    captured = {}

    def fake_call_llm(stage, prompt, max_tokens, **k):
        captured["prompt"] = prompt
        return {"parsed": {"main_class": "public class X{}", "test_class": "@isTest class XTest{}",
                           "mapping_notes": "", "sobject_refs": []}, "content": "", "provider": "mock"}

    monkeypatch.setattr(g, "call_llm", fake_call_llm)
    target = {"target_name": "X", "layer": "DAO",
              "source_classes": [{"class_name": "XDao", "layer": "DAO", "source": "interface XDao{}"}]}
    g.generate_apex(target, {}, [], schema={},
                    grounding="== Salesforce reference ==\nAlways use bind variables in SOQL")
    assert "Always use bind variables in SOQL" in captured["prompt"]


def test_end_to_end_mock_migration(monkeypatch, tmp_path):
    """Full deterministic pipeline via the mock provider produces valid SFDX output."""
    monkeypatch.setenv("H2A_PROVIDER", "mock")
    monkeypatch.setenv("H2A_INCREMENTAL", "false")

    src_dir = tmp_path / "hybris"
    src_dir.mkdir()
    (src_dir / "ProductDao.java").write_text(
        "package com.example.dao;\npublic interface ProductDao {\n"
        "  ProductModel findByCode(String code);\n}", encoding="utf-8")
    (src_dir / "DefaultProductService.java").write_text(
        "package com.example.service;\npublic class DefaultProductService {\n"
        "  private ProductDao productDao;\n"
        "  public ProductModel getProduct(String code) { return productDao.findByCode(code); }\n}",
        encoding="utf-8")
    (src_dir / "ProductController.java").write_text(
        "package com.example.web;\npublic class ProductController {\n"
        "  private DefaultProductService service;\n}", encoding="utf-8")
    (src_dir / "items.xml").write_text(
        '<?xml version="1.0"?><items><itemtypes><itemtype code="Product">'
        '<attributes><attribute qualifier="code" type="java.lang.String"/>'
        '<attribute qualifier="price" type="java.math.BigDecimal"/>'
        '</attributes></itemtype></itemtypes></items>', encoding="utf-8")

    out_dir = tmp_path / "out"
    from src.pipeline_driver import run_repo_migration
    run_repo_migration(str(src_dir), str(out_dir))

    classes_dir = out_dir / "force-app" / "main" / "default" / "classes"
    assert (classes_dir / "ProductSelector.cls").exists()
    assert (classes_dir / "ProductService.cls").exists()
    assert (classes_dir / "ProductController.cls").exists()
    assert (out_dir / "sfdx-project.json").exists()
    assert (out_dir / "FEASIBILITY_REPORT.md").exists()

    # Every generated class passes tier-1 validation.
    from src.validate import validate_all
    from src.schema import build_schema
    from src.ingest import ingest
    schema = build_schema(ingest(str(src_dir))["item_types"])
    for f in classes_dir.glob("*.cls"):
        errors = [i for i in validate_all(f.read_text(encoding="utf-8"), f.name, schema)
                  if i["severity"] == "ERROR"]
        assert errors == [], f"{f.name} has validation errors: {errors}"


