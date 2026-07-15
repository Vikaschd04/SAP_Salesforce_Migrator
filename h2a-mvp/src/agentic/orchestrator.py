"""
orchestrator.py — the agentic migration manager.

Coordinates the agent team over the shared Blackboard, reusing the Phase-0 stage
functions for the actual work:

    ingest/schema  →  Comprehend (routed cheap)  →  Planner  →
    [ Builder → Critic → bounded repair ] per target  →  Reconcile + Metadata  →
    Parity strengthening  →  Verifier (deploy + self-heal)  →  Report + Plan doc

Opt-in and side-by-side with the linear `run_repo_migration`; both share the same
downstream writers, so output is identical in shape. With `mock`/offline the
Planner and Critic degrade to deterministic behavior and the whole run is keyless.
"""

from __future__ import annotations

from pathlib import Path

from src.repo_analyzer import (get_translation_schedule, build_dependency_graph,
                               extract_method_call_graph)
from src.ingest import ingest
from src.comprehend import comprehend_class
from src.schema import build_schema, reconcile_schema
from src.validate import validate_all
from src.generate import _load_mappings, write_outputs
from src.metadata_generator import write_schema_metadata
from src.parity import build_parity, write_parity_md, close_parity_gaps
from src.report import generate_report
from src.signature_registry import SignatureRegistry
from src.llm import reset_accounting, get_accounting, _load_config, _get_provider

from src.agentic.blackboard import Blackboard
from src.agentic.router import route_model
from src.agentic.retriever import build_retriever
from src.agentic.planner import PlannerAgent
from src.agentic.critic import CriticAgent
from src.agentic.builders import BuilderAgent, VerifierAgent


def _transitive_deps(adjacency: dict, domain: str) -> set:
    seen, stack = set(), list(adjacency.get(domain, []))
    while stack:
        d = stack.pop()
        if d in seen:
            continue
        seen.add(d)
        stack.extend(adjacency.get(d, []))
    return seen


def run_agentic_migration(input_dir: str, output_dir: str, *, offline: bool = False,
                          verify: bool | None = None):
    reset_accounting()
    config = _load_config()
    bb = Blackboard(input_dir=input_dir, output_dir=output_dir, offline=offline)

    print("=== Agentic Migration (Phase 1) ===")
    bb.schedule = get_translation_schedule(input_dir)
    bb.adjacency, bb.domains = build_dependency_graph(input_dir)
    print(f"  Domains: {list(bb.domains.keys())}  |  order: {bb.schedule}")
    try:
        extract_method_call_graph(input_dir, output_dir)
    except Exception as ge:
        print(f"  ⚠ call graph skipped: {ge}")

    ingest_result = ingest(input_dir)
    bb.all_classes = ingest_result["classes"]
    bb.item_types = ingest_result["item_types"]
    bb.relations = ingest_result.get("relations", [])
    bb.enum_types = ingest_result.get("enum_types", [])
    bb.schema = build_schema(bb.item_types, bb.relations, bb.enum_types)
    bb.source_corpus = "\n".join(c.get("source", "") for c in bb.all_classes)
    print(f"  Schema: {len(bb.schema)} objects")

    # ── Comprehend (routed to the cheap tier) ──
    print("  --- Comprehend ---")
    for cls in bb.all_classes:
        if cls["layer"] == "Model":
            continue
        model = route_model(config, f"comprehend_{cls['class_name']}")
        bb.comprehensions[cls["class_name"]] = comprehend_class(cls, offline=offline, model=model)

    # ── Plan ──
    print("  --- Planner ---")
    PlannerAgent().run(bb)
    for p in bb.plan:
        if p.target_kind != "Apex":
            print(f"    · {p.target_name}: {p.target_kind}"
                  + (f" → {p.native_recommendation}" if p.native_recommendation else ""))

    # ── Build + Critic (scoped signatures, schedule order) ──
    print("  --- Build + Critic ---")
    registry = SignatureRegistry()
    mappings = _load_mappings()
    max_repair = config.get("max_repair_attempts", 2)
    critic_enabled = (config.get("agentic") or {}).get("critic", True)
    builder, critic = BuilderAgent(), CriticAgent()

    # RAG: ground generation + review in the bundled Salesforce/fflib docs.
    retriever = build_retriever(config)
    if retriever is not None:
        bb.record("Retriever", "loaded",
                  f"{retriever.n_chunks} chunks from bundled Salesforce docs (lexical RAG)")
        print(f"    · RAG grounding on ({retriever.n_chunks} doc chunks)")

    for domain in bb.schedule:
        dep_domains = _transitive_deps(bb.adjacency, domain)
        for item in [p for p in bb.code_plan() if p.domain == domain]:
            scoped = registry.get_signatures_for_domains(dep_domains)
            art = builder.build(item, bb, scoped, mappings, max_repair, retriever=retriever)
            bb.record("Builder", "generated", f"{art.target_name} ({art.apex_pattern})")

            if critic_enabled:
                findings = critic.review(art, bb.schema, offline=offline, retriever=retriever)
                if any(f.get("severity") == "ERROR" for f in findings):
                    changed = builder.apply_critic_repair(
                        art, findings, bb.schema, scoped, offline, max_repair)
                    if changed:
                        findings = critic.review(art, bb.schema, offline=offline, retriever=retriever)
                remaining = [f for f in findings if f.get("severity") == "ERROR"]
                art.status = "accepted" if not remaining else "needs_review"
                bb.record("Critic", "reviewed",
                          f"{art.target_name}: {len(findings)} finding(s) → {art.status}")
                for f in remaining:
                    bb.ask("Critic", f"{art.target_name}: [{f.get('category')}] {f.get('message')}")
                if remaining:
                    print(f"    ⚠ {art.target_name}: {len(remaining)} unresolved critic finding(s) → needs_review")
            else:
                art.status = "accepted"

            bb.artifacts.append(art)
            registry.register(domain, art.target_name, builder.signatures(art))

    # ── Reconcile schema + write outputs + metadata ──
    print("  --- Reconcile + Write ---")
    prelim = {f"{a.target_name}.cls": validate_all(a.main_class, f"{a.target_name}.cls", bb.schema)
              for a in bb.artifacts}
    bb.schema, bb.reconciliation = reconcile_schema(bb.schema, prelim, bb.source_corpus)
    if bb.reconciliation["added_fields"] or bb.reconciliation["added_objects"]:
        bb.record("Reconciler", "schema_augmented",
                  f"+{len(bb.reconciliation['added_objects'])} object(s), "
                  f"+{len(bb.reconciliation['added_fields'])} field(s)")

    write_outputs(output_dir, bb.generated_dicts(), bb.item_types, mappings)
    meta = write_schema_metadata(output_dir, bb.schema)
    print(f"    ✓ classes + {len(meta)} metadata file(s)")

    # ── ImpEx data migration (Phase 2) ──
    from src.impex import translate_impex_dir
    impex = translate_impex_dir(input_dir, output_dir)   # runs after metadata so ext-id fields are patched
    if impex["impex_files"]:
        bb.record("DataMigrator", "impex",
                  f"{len(impex['objects'])} object(s), {impex['record_total']} record(s) → CSV + runbook")
        print(f"    ✓ ImpEx: {impex['record_total']} record(s) across "
              f"{len(impex['objects'])} object(s) → data/ + DATA_MIGRATION.md")

    # ── Cronjob scheduling (Phase 2) ──
    from src.cronjob import translate_cronjobs_dir
    cron = translate_cronjobs_dir(input_dir, output_dir)
    if cron["triggers"]:
        bb.record("JobScheduler", "cronjobs",
                  f"{cron['resolved_count']} trigger(s) resolved, {cron['unresolved_count']} unresolved")
        print(f"    ✓ Cronjobs: {cron['resolved_count']} trigger(s) resolved → "
              f"CRON_JOBS.md + schedule.apex")

    # ── Parity strengthening (real provider only) ──
    parity_strengthen = None
    if (config.get("parity") or {}).get("strengthen", True) and not offline and _get_provider(config) != "mock":
        generated = bb.generated_dicts()
        parity_strengthen = close_parity_gaps(
            generated, output_dir, offline=offline, schema=bb.schema,
            max_attempts=(config.get("parity") or {}).get("max_attempts", 1))
        by = {g["target_name"]: g for g in generated}
        for a in bb.artifacts:
            if a.target_name in by:
                a.test_class = by[a.target_name]["test_class"]
        if parity_strengthen.get("rules_closed"):
            bb.record("Parity", "strengthened", f"{parity_strengthen['rules_closed']} rule(s) newly asserted")

    # ── Verify + self-heal ──
    do_verify = verify if verify is not None else (config.get("verify") or {}).get("deploy", False)
    if do_verify:
        print("  --- Verifier (deploy + self-heal) ---")
        bb.verify_result = VerifierAgent().run(bb, config)
        print(f"    {bb.verify_result.get('message', '')}")

    # ── Final validation + parity + reports ──
    for a in bb.artifacts:
        m, t = f"{a.target_name}.cls", f"{a.target_name}Test.cls"
        bb.validation_results[m] = validate_all(a.main_class, m, bb.schema)
        bb.validation_results[t] = validate_all(a.test_class, t, bb.schema)

    bb.parity = build_parity(bb.generated_dicts())
    if parity_strengthen:
        bb.parity["strengthened"] = parity_strengthen
    write_parity_md(output_dir, bb.parity)
    _write_plan_doc(bb)

    acct = get_accounting()
    report_file = generate_report(
        output_dir, bb.validation_results, acct,
        generated_results=bb.generated_dicts(), skipped_domains=[],
        verify_result=bb.verify_result, reconciliation=bb.reconciliation, parity=bb.parity)

    print("\n═══ Agentic Run Complete ═══")
    print(f"  Report: {report_file}")
    print(f"  Plan + decisions: {Path(output_dir) / 'MIGRATION_PLAN.md'}")
    print(f"  provider(s)={acct.get('providers', {})}  requests={acct['requests']}")
    if bb.open_questions:
        print(f"  Open questions for review: {len(bb.open_questions)} (see MIGRATION_PLAN.md)")
    return bb


def _write_plan_doc(bb) -> str:
    lines = ["# Agentic Migration Plan", "",
             "Produced by the Phase-1 agent team. The Planner decides each target's "
             "home (Apex / native Salesforce / skip); the Critic reviews each built "
             "artifact for behavior, security, and governor safety.", "",
             "## 1. Plan", "",
             "| Target | Pattern | Decision | Rationale |", "|---|---|---|---|"]
    for p in bb.plan:
        decision = p.target_kind
        if p.native_recommendation:
            decision += f" → {p.native_recommendation}"
        lines.append(f"| `{p.target_name}` | {p.apex_pattern} | {decision} | {p.rationale or '—'} |")

    lines += ["", "## 2. Artifact review (Critic)", "",
              "| Artifact | Status | Findings |", "|---|---|---|"]
    for a in bb.artifacts:
        n = len(a.critic_findings)
        lines.append(f"| `{a.target_name}.cls` | {a.status} | {n if n else 'none'} |")

    lines += ["", "## 3. Decisions log", "", bb.decisions_markdown(), "",
              "## 4. Open questions for human review", ""]
    lines += ([f"- {q}" for q in bb.open_questions] or ["_(none)_"])

    path = Path(bb.output_dir) / "MIGRATION_PLAN.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)
