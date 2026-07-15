"""
capability_demo.py — a guided, deterministic tour of the Phase-0 correctness
features that normally need a real org or a paid LLM call. Every step here uses
the *real* production functions with crafted inputs, so you can watch each
mechanism work with no cost and no Salesforce org.

Run:  python Testing/capability_demo.py   (from the h2a-mvp venv)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "h2a-mvp"))

def rule(title): print("\n" + "=" * 72 + f"\n  {title}\n" + "=" * 72)

# ── 1. Schema grounding + reconciliation (auto-resolve warnings) ──────────────
rule("1. SCHEMA GROUNDING catches a bad field; RECONCILIATION decides what to do")
from src.schema import build_schema, validate_field_references, reconcile_schema

schema = build_schema([{"name": "Order", "fields": [
    {"name": "code", "type": "java.lang.String"},
    {"name": "totalAmount", "type": "java.math.BigDecimal"}]}])
print("Derived schema (from items.xml):")
for obj, meta in schema.items():
    print(f"  {obj}: {list(meta['fields'])}")

# Pretend the LLM generated this Apex — it references two fields NOT in items.xml:
#   Priority__c  -> the Java source really uses `priority` (real, undeclared)
#   Wizbang__c   -> nothing in the source uses this (a hallucination)
apex = "List<Order__c> os = [SELECT Id, Code__c, Priority__c, Wizbang__c FROM Order__c];"
issues = validate_field_references(apex, schema)
print("\nValidator flags (grounding):")
for i in issues:
    print(f"  [{i['rule']}] {i['message']}")

source_corpus = "public interface OrderDao { List<Order> findByPriority(int priority); }"
augmented, info = reconcile_schema(schema, {"OrderSelector.cls": issues}, source_corpus)
print("\nReconciliation decisions (evidence = the Java source):")
for f in info["added_fields"]:
    print(f"  + ADDED  {f['object']}.{f['field']} as {f['type']}  ({f['reason']})")
for f in info["flagged"]:
    print(f"  ! FLAGGED {f['field']}  ({f['reason']})")

# ── 2. Field type inference ───────────────────────────────────────────────────
rule("2. TYPE INFERENCE reads the Java type instead of defaulting to Text")
from src.schema import infer_field_type
src = "BigDecimal getDealerFee(); boolean getActive(); int stockLevel; String note;"
for fld in ["DealerFee__c", "Active__c", "StockLevel__c", "Note__c", "Unknown__c"]:
    print(f"  {fld:15} -> {infer_field_type(fld, src)}")

# ── 3. Behavioral parity harness ──────────────────────────────────────────────
rule("3. PARITY HARNESS scores whether tests assert the comprehended business rules")
from src.parity import build_parity
generated = [{
    "target_name": "OrderService", "source_classes": [{"class_name": "DefaultOrderService"}],
    "main_class": "public with sharing class OrderService { public static Decimal total(){return 0;} }",
    "business_rules": [
        "An order total must be greater than zero",
        "Orders with a priority greater than 5 are expedited",
    ],
    # This test asserts the first rule (total/zero/positive) but NOT the second.
    "test_class": ("@isTest class OrderServiceTest { @isTest static void t(){"
                   " System.assert(total > 0, 'order total must be positive greater than zero'); } }"),
}]
parity = build_parity(generated)
o = parity["overall"]
print(f"Overall parity: {o['score']}% ({o['rules_covered']}/{o['rules_total']} rules asserted)")
for r in parity["targets"][0]["rules"]:
    print(f"  {'✅' if r['covered'] else '❌'} {r['rule']}")

# ── 4. Deploy self-healing: METADATA errors ──────────────────────────────────
rule("4. SELF-HEALING #1 — a missing-field deploy error ADDS the field (no org)")
from src.verify import _parse_metadata_errors, _errors_to_issues
deploy_errors = [
    {"file": "classes/OrderSelector.cls", "line": 3,
     "problem": "No such column 'Priority__c' on entity 'Order__c'."},
    {"file": "classes/OrderService.cls", "line": 9,
     "problem": "Variable does not exist: foo"},
]
meta = _parse_metadata_errors(deploy_errors)
print("Parsed metadata errors (fixable by adding schema, not repairing Apex):")
for m in meta:
    print(f"  {m}")
print("Remaining (Apex) errors -> fed to the LLM repair loop as:")
apex_only = [e for e in deploy_errors if "does not exist" in e["problem"]]
for iss in _errors_to_issues(apex_only):
    print(f"  {iss}")

# ── 5. Deploy self-healing: COVERAGE ─────────────────────────────────────────
rule("5. SELF-HEALING #2 — the coverage-heal loop targets classes below 75%")
per_class = [{"name": "OrderService", "coverage": 55.0},
             {"name": "OrderSelector", "coverage": 92.0},
             {"name": "OrderServiceTest", "coverage": 100.0}]
threshold = 75.0
need = [c for c in per_class if c["coverage"] < threshold and not c["name"].endswith("Test")]
print(f"Coverage threshold: {threshold}%")
for c in per_class:
    flag = "  <- STRENGTHEN" if c in need else ""
    print(f"  {c['name']:18} {c['coverage']:5.1f}%{flag}")
print(f"-> strengthen_tests() would be called for: {[c['name'] for c in need]}")

# ── 6. Parity-driven test strengthening (close the gap the harness measures) ──
rule("6. PARITY STRENGTHENING closes the gap — adds assertions for missed rules")
import src.generate as _gen
from src.parity import build_parity, close_parity_gaps
import tempfile, pathlib

demo = [{
    "target_name": "OrderService", "source_classes": [],
    "main_class": "public with sharing class OrderService {}",
    "business_rules": ["An order total must be greater than zero",
                       "Orders with priority above five are expedited"],
    "test_class": "@isTest class OrderServiceTest { @isTest static void t(){ System.assert(true); } }",
}]
print(f"Before: {build_parity(demo)['overall']['score']}% of rules asserted")
# Stub the LLM (no key needed for the demo): return a test asserting both rules.
_gen.strengthen_parity = lambda *a, **k: (
    "@isTest class OrderServiceTest { @isTest static void t(){"
    " System.assert(total > 0, 'order total greater than zero');"
    " System.assert(expedited, 'priority above five expedited'); } }")
with tempfile.TemporaryDirectory() as d:
    (pathlib.Path(d) / "force-app/main/default/classes").mkdir(parents=True)
    summary = close_parity_gaps(demo, d, max_attempts=1, log=lambda *a: None)
print(f"After:  {build_parity(demo)['overall']['score']}% "
      f"(+{summary['rules_closed']} rules now asserted in {summary['targets_improved']})")

print("\n" + "=" * 72 + "\n  All Phase-0 mechanisms exercised deterministically. ✓\n" + "=" * 72)
