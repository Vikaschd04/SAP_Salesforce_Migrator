"""
test_planner_convert_everything.py — the "always convert, flag natives" policy.

Proves that logic which maps to a native Salesforce product (e.g. pricing → CPQ) is
STILL converted to Apex and only *flagged* for review — never skipped — and that every
ingested class is accounted for in the completeness ledger.
"""

from src.agentic.blackboard import Blackboard, PlanItem, Artifact
from src.generate import prepend_review_flag


# ── PlanItem.is_code: a native recommendation must not suppress conversion ──

def test_convert_is_code_even_with_native_recommendation():
    p = PlanItem(target_name="PromotionService", layer="Service", domain="Promotion",
                 target_kind="Convert", native_recommendation="Salesforce CPQ")
    assert p.is_code is True  # flagged for CPQ, but still built


def test_skip_is_not_code():
    p = PlanItem(target_name="ProductDTO", layer="Utility", domain="Product",
                 target_kind="Skip", rationale="pure DTO, no logic")
    assert p.is_code is False


# ── The review-flag banner ──

def test_prepend_review_flag_marks_but_keeps_logic():
    code = "public with sharing class PromotionService {}"
    out = prepend_review_flag(code, "Salesforce CPQ", "pricing logic")
    assert "MANUAL REVIEW" in out
    assert "Salesforce CPQ" in out
    assert code in out                      # original logic preserved in full


def test_prepend_review_flag_noop_without_native():
    code = "public with sharing class OrderService {}"
    assert prepend_review_flag(code, "") == code


# ── Completeness ledger: nothing silently dropped ──

def _bb_with(all_classes, artifacts, plan=None):
    bb = Blackboard(input_dir="x", output_dir="y")
    bb.all_classes = all_classes
    bb.artifacts = artifacts
    bb.plan = plan or []
    return bb


def test_ledger_flags_converted_native_and_accounts_for_all():
    all_classes = [
        {"class_name": "OrderDao", "layer": "DAO"},
        {"class_name": "DefaultPromotionService", "layer": "Service"},
        {"class_name": "CustomerModel", "layer": "Model"},
    ]
    artifacts = [
        Artifact(target_name="OrderSelector", layer="DAO",
                 source_classes=[{"class_name": "OrderDao"}]),
        Artifact(target_name="PromotionService", layer="Service",
                 source_classes=[{"class_name": "DefaultPromotionService"}],
                 review_flags=["Consider Salesforce CPQ (converted in full)."]),
    ]
    rows = _bb_with(all_classes, artifacts).completeness_ledger()
    by = {r["source"]: r for r in rows}

    assert by["OrderDao"]["outcome"] == "converted"
    assert by["DefaultPromotionService"]["outcome"] == "flagged"   # built + flagged, not skipped
    assert "CPQ" in by["DefaultPromotionService"]["note"]
    assert by["CustomerModel"]["outcome"] == "converted"           # Model → SObject metadata
    assert all(r["outcome"] != "unaccounted" for r in rows)        # nothing dropped


def test_ledger_records_skip_with_reason_and_flags_unaccounted():
    all_classes = [
        {"class_name": "DeadGlue", "layer": "Utility"},
        {"class_name": "Orphan", "layer": "Service"},
    ]
    plan = [PlanItem(target_name="DeadGlue", layer="Utility", domain="x",
                     target_kind="Skip", rationale="framework boilerplate",
                     source_classes=[{"class_name": "DeadGlue"}])]
    rows = _bb_with(all_classes, [], plan).completeness_ledger()
    by = {r["source"]: r for r in rows}

    assert by["DeadGlue"]["outcome"] == "skipped"
    assert "boilerplate" in by["DeadGlue"]["note"]
    # A class neither built nor explicitly skipped must surface as unaccounted.
    assert by["Orphan"]["outcome"] == "unaccounted"


# ── Planner decision mapping (real-provider path, no key needed) ──

def test_planner_maps_convert_and_skip_from_llm_decisions(monkeypatch):
    import src.agentic.planner as planner_mod

    # Simulate the structured LLM result: pricing → Convert + CPQ flag; a DTO → Skip.
    fake = {"parsed": {"decisions": [
        {"target_name": "PromotionService", "target_kind": "Convert",
         "rationale": "pricing", "native_recommendation": "Salesforce CPQ"},
        {"target_name": "ProductDTO", "target_kind": "Skip", "rationale": "pure DTO"},
    ]}}
    monkeypatch.setattr(planner_mod, "call_structured", lambda *a, **k: fake)

    base = [
        PlanItem(target_name="PromotionService", layer="Service", domain="Promotion",
                 source_classes=[{"class_name": "DefaultPromotionService"}]),
        PlanItem(target_name="ProductDTO", layer="Utility", domain="Product",
                 source_classes=[{"class_name": "ProductDTO"}]),
    ]
    bb = Blackboard(input_dir="x", output_dir="y")
    planner_mod.PlannerAgent()._annotate_with_llm(bb, base)

    promo = next(p for p in base if p.target_name == "PromotionService")
    dto = next(p for p in base if p.target_name == "ProductDTO")
    assert promo.target_kind == "Convert" and promo.is_code       # pricing still built
    assert promo.native_recommendation == "Salesforce CPQ"        # …and flagged
    assert dto.target_kind == "Skip" and not dto.is_code          # genuine DTO skipped


# ── interface + Default* impl: the universal Hybris idiom ─────────────────────

def _names(targets):
    return {c["class_name"] for t in targets for c in t["source_classes"]}


def test_both_halves_of_a_facade_pair_are_planned():
    """Every Hybris facade is an interface plus a Default* implementation. Picking one
    with next(...) dropped the other silently — it reached no target, and surfaced much
    later as an `unaccounted` row on a perfectly ordinary codebase."""
    from src.generate import plan_targets
    classes = [
        {"class_name": "PricingService", "layer": "Service"},
        {"class_name": "DefaultPricingService", "layer": "Service"},
        {"class_name": "PricingFacade", "layer": "Facade"},
        {"class_name": "DefaultPricingFacade", "layer": "Facade"},
    ]
    assert _names(plan_targets(classes)) == {c["class_name"] for c in classes}


def test_two_classes_that_resolve_to_one_apex_class_become_one_target():
    """The interface and its implementation both derive the same target name. Emitting
    two targets meant generating the class twice and letting the second write win —
    silently discarding the first artifact and the tokens spent on it."""
    from src.generate import plan_targets
    targets = plan_targets([
        {"class_name": "PricingService", "layer": "Service"},
        {"class_name": "DefaultPricingService", "layer": "Service"},
    ])
    assert len(targets) == 1, "the same Apex class was planned twice"
    assert _names(targets) == {"PricingService", "DefaultPricingService"}


def test_facades_with_no_service_still_reach_a_target():
    """A facade over a DAO, or over another extension's service, has nothing to fold
    into — it must not vanish for want of a host."""
    from src.generate import plan_targets
    targets = plan_targets([
        {"class_name": "PricingFacade", "layer": "Facade"},
        {"class_name": "DefaultPricingFacade", "layer": "Facade"},
    ])
    assert _names(targets) == {"PricingFacade", "DefaultPricingFacade"}


def test_dao_pairs_merge_too():
    from src.generate import plan_targets
    targets = plan_targets([
        {"class_name": "OrderDao", "layer": "DAO"},
        {"class_name": "DefaultOrderDao", "layer": "DAO"},
    ])
    assert len(targets) == 1 and targets[0]["target_name"] == "OrderSelector"
    assert _names(targets) == {"OrderDao", "DefaultOrderDao"}


def test_the_realistic_corpus_leaves_nothing_unaccounted():
    """The end-to-end guarantee: every ingested class reaches a target."""
    from src.ingest import ingest
    from src.repo_analyzer import build_dependency_graph
    from src.generate import plan_targets

    D = "../Testing/acme-commerce-hybris"
    _, domains = build_dependency_graph(D)
    all_classes = ingest(D)["classes"]
    covered = set()
    for names in ({c["class_name"] for c in lst} for lst in domains.values()):
        covered |= _names(plan_targets([c for c in all_classes if c["class_name"] in names]))

    backend = {c["class_name"] for c in all_classes if c.get("layer") not in ("Component", "Model")}
    assert backend - covered == set(), f"unplanned: {sorted(backend - covered)}"
