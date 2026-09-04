"""The seam both pipelines meet at, and the places it was not actually closed. [1.33]

The v2 refactor put a source adapter and a target adapter on either side of the run, and
routed reading and emission through them. Everything *between* stayed as it was: written
for Hybris on the way in and Salesforce on the way out. That was a sound way to ship v2
without regressing v1, and it made the second pipeline unrunnable in five separate places
— none of them in an adapter:

- preflight looked for Java and Angular, and told a Magento project "there is nothing to
  migrate";
- `build_schema` derived Salesforce SObjects for every run, including ones emitting
  `items.xml`;
- `write_schema_metadata` wrote `force-app/objects/` regardless of target;
- the org check queried a Salesforce org during an Adobe→Hybris run;
- `emit` was never handed the source model it needs, so the run died at the last step.

Two more were information loss rather than crashes, and those are the ones worth having
tests for: the target's own word for what a unit becomes was dropped between the planner
and the emitter, and the ledger reported artifacts as `converted` that the emitter had
deliberately not written.
"""

import pytest

from src import pipeline
from src.agentic.blackboard import Blackboard, PlanItem

CORPUS_MAGENTO = "../Testing/acme-commerce-magento"
CORPUS_HYBRIS = "../Testing/acme-commerce-hybris"


@pytest.fixture(autouse=True)
def _registered():
    pipeline.ensure_registered()


def _p(pid):
    return pipeline.get(pid)


# ── every adapter answers the whole protocol ──────────────────────────────────

@pytest.mark.parametrize("pid", ["hybris->salesforce", "adobe->hybris"])
@pytest.mark.parametrize("method", ["preflight", "detect", "read"])
def test_every_source_answers_the_protocol(pid, method):
    assert callable(getattr(_p(pid).source, method, None))


@pytest.mark.parametrize("pid", ["hybris->salesforce", "adobe->hybris"])
@pytest.mark.parametrize("method", ["plan", "emit", "validate", "verify",
                                    "schema", "reconcile", "emit_schema"])
def test_every_target_answers_the_protocol(pid, method):
    assert callable(getattr(_p(pid).target, method, None))


@pytest.mark.parametrize("pid,expected", [("hybris->salesforce", True),
                                          ("adobe->hybris", False)])
def test_only_a_target_with_an_environment_claims_one(pid, expected):
    """The org step ran for every target, so an Adobe→Hybris run queried a Salesforce org
    and reported how well the plan fitted it."""
    assert _p(pid).target.has_org is expected


# ── preflight is asked in the source's own vocabulary ─────────────────────────

def test_a_magento_project_is_not_measured_for_java():
    pre = _p("adobe->hybris").source.preflight(CORPUS_MAGENTO)
    assert pre["verdict"] != "reject"
    assert "PHP" in pre["summary"]


def test_a_hybris_project_still_gets_the_shipped_verdict():
    """The Hybris source delegates to the same `preflight.inspect`, so routing it through
    the adapter cannot change a verdict."""
    from src.preflight import inspect

    direct = inspect(CORPUS_HYBRIS)
    viaadapter = _p("hybris->salesforce").source.preflight(CORPUS_HYBRIS)
    assert direct == viaadapter


def test_each_source_refuses_the_other_platform():
    assert _p("adobe->hybris").source.preflight(CORPUS_HYBRIS)["verdict"] == "reject"


def test_preflight_refuses_a_path_that_is_not_a_codebase():
    got = _p("adobe->hybris").source.preflight("/nonexistent/path")
    assert got["verdict"] == "reject" and got["blockers"]


def test_preflight_does_not_inherit_the_not_implemented_blocker():
    """`detect` folds "not implemented yet" into its own blockers. That is a fact about
    this adapter's maturity, not the customer's codebase, and refusing an unrunnable
    pipeline is `require_runnable`'s job."""
    pre = _p("adobe->hybris").source.preflight(CORPUS_MAGENTO)
    assert not any("not implemented" in b.lower() for b in pre["blockers"])


@pytest.mark.parametrize("key", ["verdict", "blockers", "warnings", "signals",
                                 "secrets", "summary"])
def test_both_preflights_return_what_the_orchestrator_reads(key):
    for pid, corpus in (("adobe->hybris", CORPUS_MAGENTO),
                        ("hybris->salesforce", CORPUS_HYBRIS)):
        assert key in _p(pid).source.preflight(corpus)


# ── the schema belongs to the target ──────────────────────────────────────────

def test_the_salesforce_schema_is_exactly_the_shipped_one():
    """Routing through the adapter must not change a single field."""
    from src.ingest import _parse_enum_types, _parse_items_xml, _parse_relations
    from src.schema import build_schema
    from pathlib import Path

    items = str(next(Path(CORPUS_HYBRIS).rglob("*-items.xml")))
    args = (_parse_items_xml(items), _parse_relations(items), _parse_enum_types(items))
    assert _p("hybris->salesforce").target.schema(*args) == build_schema(*args)


def test_the_hybris_schema_is_items_xml_types_not_sobjects():
    """`build_schema` was called unconditionally, so an Adobe→Hybris run derived
    `__c` objects that nothing would ever emit."""
    got = _p("adobe->hybris").source.read(CORPUS_MAGENTO)
    schema = _p("adobe->hybris").target.schema(
        got.data_model.types, got.data_model.relations, got.data_model.enums)
    assert schema, "the Magento db_schema.xml declares tables"
    assert not any(name.endswith("__c") for name in schema)


def test_the_hybris_schema_carries_java_types():
    got = _p("adobe->hybris").source.read(CORPUS_MAGENTO)
    schema = _p("adobe->hybris").target.schema(
        got.data_model.types, got.data_model.relations, got.data_model.enums)
    types = {t for meta in schema.values() for t in meta["fields"].values()}
    assert types and not (types & {"Text", "Picklist", "Currency", "Checkbox"})


def test_the_hybris_schema_reads_like_every_other_schema():
    """Objects with fields is the one shape both platforms share, so the same prompt
    grounding and the same reports work without knowing which produced it."""
    from src.schema import schema_prompt_block

    got = _p("adobe->hybris").source.read(CORPUS_MAGENTO)
    schema = _p("adobe->hybris").target.schema(
        got.data_model.types, got.data_model.relations, got.data_model.enums)
    assert schema_prompt_block(schema).startswith("- ")


def test_a_target_with_no_compiler_says_it_did_not_reconcile():
    """Different from reconciling and finding nothing wrong — reconciliation needs a
    compiler's view of which references fail."""
    schema, notes = _p("adobe->hybris").target.reconcile({"A": {}}, {}, "")
    assert schema == {"A": {}}
    assert notes["ran"] is False and notes["added_fields"] == []


def test_a_hybris_extension_writes_no_separate_schema_metadata():
    """`items.xml` is part of the extension `emit` already wrote; a second copy would
    compete with it."""
    assert _p("adobe->hybris").target.emit_schema("/tmp/whatever", {"A": {}}) == []


# ── the plan contract ─────────────────────────────────────────────────────────

def test_both_targets_accept_the_wire_format():
    """The protocol says units are dicts. The Hybris target read them as objects, which
    made the pipeline unrunnable at the Planner."""
    units = [{"class_name": "PricingService", "name": "PricingService",
              "layer": "Model", "source": "<?php class PricingService {}", "file": "a.php"}]
    for pid in ("hybris->salesforce", "adobe->hybris"):
        assert isinstance(_p(pid).target.plan(units, {}), list)


def test_the_targets_own_word_survives_the_planner():
    """`hybris_plan` decides SERVICE / JOB / DECORATOR / LISTENER and explains why. The
    planner rebuilt a PlanItem from that row and kept neither, so the entire reason the
    adapter exists was discarded before emission."""
    item = PlanItem(target_name="X", layer="Cron", domain="d", kind="job",
                    rationale="a crontab job becomes an AbstractJobPerformable")
    assert item.kind == "job" and "AbstractJobPerformable" in item.rationale


def test_a_target_with_no_such_notion_leaves_the_kind_empty():
    assert PlanItem(target_name="X", layer="Service", domain="d").kind == ""


# ── the ledger believes the emitter ───────────────────────────────────────────

def _bb_with(artifact_name, layer="Service"):
    bb = Blackboard(input_dir=".", output_dir=".")
    bb.all_classes = [{"class_name": "Src", "layer": layer, "source": "x"}]
    from src.agentic.blackboard import Artifact
    art = Artifact(target_name=artifact_name, layer=layer, apex_pattern="Service")
    art.source_classes = [{"class_name": "Src", "layer": layer}]
    bb.artifacts = [art]
    return bb


def test_an_artifact_the_emitter_did_not_write_is_not_converted():
    """The Builder cannot see this loss — it happens after the Builder is done. Reporting
    it as `converted` is exactly the success-shaped failure the ledger exists to prevent:
    the report claimed eight conversions over an extension holding three of them."""
    bb = _bb_with("AwardPointsObserverListener")
    bb.not_emitted = {"Src": "no emitter for `event-listener` yet"}
    row = next(r for r in bb.completeness_ledger() if r["source"] == "Src")
    assert row["outcome"] == "manual"
    assert "event-listener" in row["note"]


def test_an_artifact_the_emitter_did_write_is_converted():
    bb = _bb_with("PricingService")
    row = next(r for r in bb.completeness_ledger() if r["source"] == "Src")
    assert row["outcome"] == "converted"


def test_the_ledger_names_java_files_in_a_java_run():
    """It named them `.cls` — Salesforce's extension — in a report a customer reads to
    find the file."""
    bb = _bb_with("PricingService")
    bb.pipeline_id = "adobe->hybris"
    assert bb.output_path(bb.artifacts[0]) == "PricingService.java"


def test_the_ledger_still_names_apex_files_in_an_apex_run():
    bb = _bb_with("PricingService")
    bb.pipeline_id = "hybris->salesforce"
    assert bb.output_path(bb.artifacts[0]) == "PricingService.cls"


def test_an_unknown_pipeline_keeps_todays_answer():
    """`.cls` is what every existing run produces and what the golden baseline records."""
    bb = _bb_with("PricingService")
    assert bb.output_path(bb.artifacts[0]) == "PricingService.cls"


def test_a_component_is_still_addressed_as_a_bundle():
    bb = _bb_with("pricingBreakdown", layer="Component")
    bb.pipeline_id = "hybris->salesforce"
    assert bb.output_path(bb.artifacts[0]) == "lwc/pricingBreakdown"


# ── the wire format really is dicts ───────────────────────────────────────────

def test_skipped_units_reach_the_ledger_as_dicts():
    """`to_ingest` exists to produce the wire format. A source that left objects in
    `skipped` reached the completeness ledger — which is platform-neutral and reads
    dicts — as an AttributeError."""
    model = _p("adobe->hybris").source.read(CORPUS_MAGENTO)
    assert all(isinstance(s, dict) for s in model.to_ingest()["frontend_skipped"])


# ── the build order comes from whoever can read the source [1.38] ─────────────

def test_a_source_the_java_analyser_cannot_read_still_gets_an_order():
    """`build_dependency_graph` reads Java, so for Magento it returns nothing and every
    unit landed in one wave — each target built with none of its dependencies' signatures
    in scope, which is the only reason the schedule exists. The Adobe reader already
    computes a topological order and it was being discarded."""
    from src.agentic.orchestrator import _augment_domains_and_schedule
    from src.agentic.blackboard import Blackboard

    model = _p("adobe->hybris").source.read(CORPUS_MAGENTO)
    bb = Blackboard(input_dir=".", output_dir=".")
    bb.source_model = model
    bb.all_classes = model.to_ingest()["classes"]
    bb.domains, bb.schedule, bb.adjacency = {}, [], {}
    _augment_domains_and_schedule(bb)

    assert bb.adjacency, "no domain edges were derived from the source's own references"
    order = {name: i for i, name in enumerate(model.dependency_order)}
    ranks = [min(order.get(c["class_name"], 10**6) for c in bb.domains[d])
             for d in bb.schedule]
    assert ranks == sorted(ranks), "the schedule does not follow the source's topology"


def test_the_shipped_path_is_left_exactly_as_it_was():
    """The analyser fills `adjacency` for Java, and reordering there changed the build
    sequence under v2 — breaking the v1/v2 equivalence the whole seam rests on. This is a
    fallback for a source the analyser cannot read, not a second opinion about one it
    can."""
    from src.agentic.orchestrator import _augment_domains_and_schedule
    from src.agentic.blackboard import Blackboard

    bb = Blackboard(input_dir=".", output_dir=".")
    bb.all_classes = []
    bb.domains = {"Z": [{"class_name": "Z"}], "A": [{"class_name": "A"}]}
    bb.schedule = ["Z", "A"]
    bb.adjacency = {"Z": ["A"]}
    bb.source_model = type("M", (), {"dependency_order": ["A", "Z"], "units": []})()

    _augment_domains_and_schedule(bb)
    assert bb.schedule == ["Z", "A"], "an analyser-derived schedule must not be re-sorted"
    assert bb.adjacency == {"Z": ["A"]}


# ── one derivation of a name [1.38] ───────────────────────────────────────────

def test_the_service_name_and_the_file_name_cannot_disagree():
    """`hybris_plan` stripped `Interface` before asking for a name and the emitters asked
    with the raw unit name, so `LoyaltyAccountInterface` was written into
    `LoyaltyAccountService.java` as `interface LoyaltyAccountInterfaceService` — a file
    whose name and class do not match, which Java rejects outright."""
    from src.adapters.hybris_plan import SERVICE, _name_for
    from src.adapters.hybris_service import service_name

    unit = type("U", (), {"name": "LoyaltyAccountInterface"})()
    assert service_name(unit.name) == "LoyaltyAccountService"
    assert _name_for(unit, SERVICE) == service_name(unit.name)


def test_a_name_that_already_ends_in_service_is_not_doubled():
    from src.adapters.hybris_service import service_name

    assert service_name("PricingService") == "PricingService"
    assert service_name("PricingServiceInterface") == "PricingService"
