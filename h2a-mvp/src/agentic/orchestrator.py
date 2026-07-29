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


def _domain_for(cls: dict) -> str:
    """Feature domain for a class the Java dependency graph didn't cover (e.g. a
    frontend Component). `ProductListComponent` → `ProductList`."""
    name = cls.get("class_name", "")
    for suffix in ("Component", "Controller", "Service", "Module"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def _augment_domains_and_schedule(bb) -> None:
    """Ensure every ingested class has a domain + a build-schedule slot. repo_analyzer
    only sees Java, so frontend Components would otherwise never be planned/built."""
    covered = {c.get("class_name") for lst in bb.domains.values() for c in lst}
    for cls in bb.all_classes:
        if cls.get("class_name") in covered:
            continue
        dom = _domain_for(cls)
        bb.domains.setdefault(dom, []).append(cls)
        if dom not in bb.schedule:
            bb.schedule.append(dom)


def _transitive_deps(adjacency: dict, domain: str) -> set:
    seen, stack = set(), list(adjacency.get(domain, []))
    while stack:
        d = stack.pop()
        if d in seen:
            continue
        seen.add(d)
        stack.extend(adjacency.get(d, []))
    return seen


def _error_artifact(item, err: str):
    """A placeholder for a target whose automatic build failed — so one bad class is
    flagged for manual migration and accounted for in the ledger, never a reason to
    abort the whole run. Kept writer-safe (valid stub bundle for a failed Component)."""
    from src.agentic.blackboard import Artifact
    stub = (f"// AUTOMATIC MIGRATION FAILED for {item.target_name}.\n"
            f"// Reason: {err}\n"
            f"// This class could not be auto-translated and needs manual conversion.\n")
    is_component = item.layer == "Component"
    art = Artifact(
        target_name=item.target_name, layer=item.layer,
        apex_pattern=item.apex_pattern or "Utility",
        main_class="" if is_component else stub,
        source_classes=[{"class_name": c.get("class_name", ""), "layer": c.get("layer", ""),
                         "source": c.get("source", "")} for c in item.source_classes],
        status="error",
    )
    art.review_flags.append(f"Automatic conversion failed ({err}); needs manual migration.")
    if is_component:
        art.lwc_bundle = {
            "js": f"// TODO manual migration — automatic conversion failed: {err}",
            "html": "<template><!-- TODO manual migration --></template>",
            "css": "",
            "meta": ('<?xml version="1.0" encoding="UTF-8"?>\n'
                     '<LightningComponentBundle xmlns="http://soap.sforce.com/2006/04/metadata">'
                     '<apiVersion>59.0</apiVersion><isExposed>false</isExposed></LightningComponentBundle>'),
            "test": "",
        }
    return art


def _make_emitter(on_event):
    """Return an emit(type, **data) that forwards structured progress events to an
    optional listener (e.g. the web dashboard). Never raises — a UI hiccup must not
    break a migration. When on_event is None (CLI / extension), it's a no-op and the
    existing prints stand, so nothing changes for those callers."""
    def emit(etype, **data):
        if on_event is None:
            return
        try:
            on_event({"type": etype, **data})
        except Exception:
            pass
    return emit


_MAX_GATE_ROUNDS = 3


def _run_gate(gate, emit, name: str, payload: dict) -> dict:
    """Human-in-the-loop review gate. When `gate` is None (autopilot / CLI / extension)
    this is a no-op that approves. When supervised, it emits a gate_open event with the
    state to review, then BLOCKS in the caller's `gate` callback until the reviewer
    submits a decision — and returns it."""
    if gate is None:
        return {"action": "approve"}
    emit("gate_open", gate=name, **payload)
    try:
        decision = gate(name, payload) or {"action": "approve"}
    except Exception:
        decision = {"action": "approve"}
    emit("gate_closed", gate=name, action=decision.get("action", "approve"))
    return decision


def _apply_plan_decision(bb, decision) -> int:
    """Apply reviewer overrides to the plan: flip Convert↔Skip per target."""
    overrides = (decision or {}).get("overrides") or {}
    changed = 0
    for p in bb.plan:
        o = overrides.get(p.target_name)
        if not o:
            continue
        newdec = o.get("decision")
        if newdec == "Skip" and p.target_kind != "Skip":
            p.target_kind = "Skip"; p.rationale = "excluded by reviewer"; changed += 1
        elif newdec == "Convert" and p.target_kind == "Skip":
            p.target_kind = "Convert"; p.rationale = "included by reviewer"; changed += 1
    return changed


_CX_ORDER = {"Low": 1, "Medium": 2, "High": 3}


def _comprehension_for(bb, item) -> dict:
    """Roll up the Comprehender's understanding of an item's source classes, so the
    Plan-gate reviewer can see what a target does (and its risk) before approving."""
    purpose, rules, risks, cx = "", [], [], ""
    for c in item.source_classes:
        u = bb.comprehensions.get(c.get("class_name")) or {}
        if not purpose and isinstance(u.get("purpose"), str):
            purpose = u["purpose"]
        rules += list(u.get("business_rules") or [])
        risks += list(u.get("migration_risks") or [])
        if _CX_ORDER.get(u.get("complexity", ""), 0) > _CX_ORDER.get(cx, 0):
            cx = u.get("complexity", "")
    return {"purpose": purpose, "business_rules": rules[:6],
            "migration_risks": risks[:6], "complexity": cx}


def _plan_payload(bb) -> dict:
    return {"items": [{
        "target_name": p.target_name, "layer": p.layer, "domain": p.domain,
        "decision": ("Skip" if p.target_kind == "Skip" else "Convert"),
        "native_recommendation": p.native_recommendation, "rationale": p.rationale,
        "sources": [c.get("class_name") for c in p.source_classes],
        "comprehension": _comprehension_for(bb, p),
    } for p in bb.plan]}


def _build_payload(bb) -> dict:
    def code_of(a):
        return (a.lwc_bundle or {}).get("js", "") if a.is_lwc else a.main_class
    return {"artifacts": [{
        "target_name": a.target_name, "layer": a.layer, "is_lwc": a.is_lwc,
        "apex_pattern": a.apex_pattern, "status": a.status,
        "review_flags": list(a.review_flags),
        "findings": [{"severity": f.get("severity"), "category": f.get("category"),
                      "message": f.get("message"), "suggestion": f.get("suggestion", "")}
                     for f in a.critic_findings],
        "code": code_of(a)[:6000],
    } for a in bb.artifacts]}


def run_agentic_migration(input_dir: str, output_dir: str, *, offline: bool = False,
                          verify: bool | None = None, on_event=None, gate=None):
    reset_accounting()
    config = _load_config()
    bb = Blackboard(input_dir=input_dir, output_dir=output_dir, offline=offline)
    emit = _make_emitter(on_event)
    # Stream each recorded decision live so the dashboard's audit trail builds in real time.
    bb.on_decision = lambda d: emit("decision", agent=d["agent"], action=d["action"], detail=d["detail"])
    emit("run_started", input=input_dir, output=output_dir, offline=offline)

    print("=== Agentic Migration (Phase 1) ===")
    emit("stage", name="analyze", status="start")
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
    bb.frontend_skipped = ingest_result.get("frontend_skipped", [])
    bb.schema = build_schema(bb.item_types, bb.relations, bb.enum_types)
    bb.source_corpus = "\n".join(c.get("source", "") for c in bb.all_classes)

    # repo_analyzer only sees Java; make sure every ingested class (incl. frontend
    # Components) has a domain and a slot in the build schedule so it gets built.
    _augment_domains_and_schedule(bb)
    n_fe = sum(1 for c in bb.all_classes if c.get("layer") == "Component")
    print(f"  Schema: {len(bb.schema)} objects"
          + (f"  |  frontend components: {n_fe}" if n_fe else ""))
    emit("stage", name="analyze", status="done",
         detail=f"{len(bb.domains)} domains, {len(bb.schema)} objects, {n_fe} frontend components")
    emit("analyzed", domains=list(bb.domains.keys()), schedule=list(bb.schedule),
         objects=len(bb.schema), backend_classes=len(bb.all_classes) - n_fe, frontend_components=n_fe,
         files=[{"class_name": c.get("class_name"), "layer": c.get("layer"), "file": c.get("file", "")}
                for c in bb.all_classes])

    # ── Comprehend (routed to the cheap tier) ──
    print("  --- Comprehend ---")
    emit("stage", name="comprehend", status="start")
    for cls in bb.all_classes:
        if cls["layer"] == "Model":
            continue
        model = route_model(config, f"comprehend_{cls['class_name']}")
        u = comprehend_class(cls, offline=offline, model=model)
        bb.comprehensions[cls["class_name"]] = u
        # Surface what the agent actually understood so the reviewer can see the AI's
        # reading of each class — not just that it was processed.
        emit("comprehend", cls=cls["class_name"], layer=cls.get("layer"),
             purpose=(u.get("purpose") if isinstance(u.get("purpose"), str) else ""),
             business_rules=list(u.get("business_rules") or [])[:8],
             queries=list(u.get("queries") or [])[:8],
             side_effects=list(u.get("side_effects") or [])[:8],
             inputs=list(u.get("inputs") or [])[:8],
             outputs=list(u.get("outputs") or [])[:8],
             dependencies=list(u.get("dependencies") or [])[:12],
             migration_risks=list(u.get("migration_risks") or [])[:8],
             complexity=u.get("complexity") or "")
    emit("stage", name="comprehend", status="done", detail=f"{len(bb.comprehensions)} classes understood")

    # ── Plan ──
    print("  --- Planner ---")
    emit("stage", name="plan", status="start")
    PlannerAgent().run(bb)
    for p in bb.plan:
        if p.target_kind == "Skip":
            print(f"    · {p.target_name}: skipped — {p.rationale}")
        elif p.native_recommendation:
            print(f"    · {p.target_name}: converted + review flag → consider {p.native_recommendation}")
    emit("plan", items=[{
        "target_name": p.target_name, "layer": p.layer, "domain": p.domain,
        "decision": ("Skip" if p.target_kind == "Skip" else "Convert"),
        "native_recommendation": p.native_recommendation, "rationale": p.rationale,
        "sources": [c.get("class_name") for c in p.source_classes],
    } for p in bb.plan])
    emit("stage", name="plan", status="done",
         detail=f"{sum(1 for p in bb.plan if p.is_code)} to convert, "
                f"{sum(1 for p in bb.plan if p.target_kind == 'Skip')} skipped")

    # ── Review gate: the reviewer can adjust what gets migrated before we build ──
    if gate is not None:
        decision = _run_gate(gate, emit, "plan", _plan_payload(bb))
        n = _apply_plan_decision(bb, decision)
        if n:
            bb.record("Reviewer", "plan_gate", f"{n} plan override(s) applied")
            emit("plan", **_plan_payload(bb))

    # ── Build + Critic (scoped signatures, schedule order) ──
    print("  --- Build + Critic ---")
    emit("stage", name="build", status="start")
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
            # "building" carries the plan context so the reviewer sees WHAT is being
            # built and WHY (pattern, source classes, native-review flag) as it starts.
            emit("artifact", target_name=item.target_name, layer=item.layer, status="building",
                 apex_pattern=item.apex_pattern, domain=item.domain, rationale=item.rationale,
                 native_recommendation=item.native_recommendation,
                 sources=[c.get("class_name") for c in item.source_classes])
            build_error = None
            try:
                art = builder.build(item, bb, scoped, mappings, max_repair, retriever=retriever)
                bb.record("Builder", "generated", f"{art.target_name} ({art.apex_pattern})")

                if critic_enabled:
                    findings = critic.review(art, bb.schema, offline=offline, retriever=retriever)
                    if any(f.get("severity") == "ERROR" for f in findings):
                        n_err = sum(1 for f in findings if f.get("severity") == "ERROR")
                        changed = builder.apply_critic_repair(
                            art, findings, bb.schema, scoped, offline, max_repair)
                        if changed:
                            # Show the Critic→Builder repair loop working, not just the outcome.
                            emit("critic_repair", target_name=art.target_name, errors=n_err,
                                 categories=sorted({f.get("category") for f in findings
                                                    if f.get("severity") == "ERROR"}))
                            bb.record("Builder", "critic_repair",
                                      f"{art.target_name}: repaired {n_err} critic error(s)")
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
            except Exception as be:
                # Contain a single-target failure: flag it for manual migration and keep
                # going, so one problematic class never aborts the whole repo.
                build_error = f"{type(be).__name__}: {be}"
                print(f"    ⚠ build FAILED for {item.target_name}: {build_error} "
                      f"— flagged for manual review, continuing")
                art = _error_artifact(item, build_error)
                bb.record("Builder", "build_failed", f"{item.target_name}: {build_error}")
                bb.ask("Builder", f"{item.target_name}: automatic build failed — {build_error}")

            bb.artifacts.append(art)
            try:
                registry.register(domain, art.target_name, builder.signatures(art))
            except Exception:
                pass   # signature extraction on a stub must not abort the run
            # "done" carries the full agent product: what the Builder mapped, which
            # SObjects/rules it preserved, and every Critic finding (not just a count).
            emit("artifact", target_name=art.target_name, layer=art.layer,
                 apex_pattern=art.apex_pattern, status=art.status,
                 is_lwc=art.is_lwc, findings=len(art.critic_findings),
                 findings_detail=[{"severity": f.get("severity"), "category": f.get("category"),
                                   "message": f.get("message"), "suggestion": f.get("suggestion", "")}
                                  for f in art.critic_findings],
                 review_flags=list(art.review_flags),
                 mapping_notes=(art.mapping_notes or "")[:800],
                 sobject_refs=list(art.sobject_refs or []),
                 business_rules=list(art.business_rules or [])[:10],
                 sources=[c.get("class_name") for c in art.source_classes],
                 lwc_parts=(sorted((art.lwc_bundle or {}).keys()) if art.is_lwc else []),
                 has_controller=bool(art.apex_controller))

    emit("stage", name="build", status="done", detail=f"{len(bb.artifacts)} artifact(s) built")

    # ── Review gate: approve, or send artifacts back to the Builder with feedback ──
    if gate is not None:
        art_domain = {p.target_name: p.domain for p in bb.plan}
        rounds = 0
        while rounds < _MAX_GATE_ROUNDS:
            decision = _run_gate(gate, emit, "build", _build_payload(bb))
            if decision.get("action") != "rework":
                break
            feedback = decision.get("feedback") or {}
            for a in bb.artifacts:
                note = feedback.get(a.target_name)
                if not note:
                    continue
                dom = art_domain.get(a.target_name, "")
                scoped = registry.get_signatures_for_domains(_transitive_deps(bb.adjacency, dom))
                builder.rework(a, note, bb, scoped)
                if critic_enabled:
                    findings = critic.review(a, bb.schema, offline=offline, retriever=retriever)
                    a.status = ("accepted" if not any(f.get("severity") == "ERROR" for f in findings)
                                else "needs_review")
                bb.record("Reviewer", "rework", f"{a.target_name}: {note[:80]}")
                emit("artifact", target_name=a.target_name, layer=a.layer,
                     apex_pattern=a.apex_pattern, status=a.status, is_lwc=a.is_lwc,
                     findings=len(a.critic_findings), review_flags=list(a.review_flags), reworked=True)
            rounds += 1

    # ── Reconcile schema + write outputs + metadata ──
    print("  --- Reconcile + Write ---")
    emit("stage", name="reconcile", status="start")
    # Only Apex artifacts feed schema reconciliation (LWC has no SObject SOQL to check).
    prelim = {f"{a.target_name}.cls": validate_all(a.main_class, f"{a.target_name}.cls", bb.schema)
              for a in bb.artifacts if not a.is_lwc}
    bb.schema, bb.reconciliation = reconcile_schema(bb.schema, prelim, bb.source_corpus)
    if bb.reconciliation["added_fields"] or bb.reconciliation["added_objects"]:
        bb.record("Reconciler", "schema_augmented",
                  f"+{len(bb.reconciliation['added_objects'])} object(s), "
                  f"+{len(bb.reconciliation['added_fields'])} field(s)")

    write_outputs(output_dir, bb.generated_dicts(), bb.item_types, mappings)
    meta = write_schema_metadata(output_dir, bb.schema)
    print(f"    ✓ classes + {len(meta)} metadata file(s)")
    # Surface exactly which schema changes the AI made (and its evidence) so the
    # reviewer can see the reconciliation reasoning, not just a count.
    emit("reconcile", metadata_files=len(meta),
         added_objects=list(bb.reconciliation.get("added_objects", []))[:40],
         added_fields=list(bb.reconciliation.get("added_fields", []))[:40])
    emit("stage", name="reconcile", status="done",
         detail=f"{len(meta)} metadata file(s); "
                f"+{len(bb.reconciliation.get('added_fields', []))} evidenced field(s)")

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
        # Parity is about Apex test assertions; LWC bundles are excluded.
        generated = [g for g in bb.generated_dicts() if g.get("layer") != "Component"]
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
        emit("stage", name="verify", status="start")
        bb.verify_result = VerifierAgent().run(bb, config)
        print(f"    {bb.verify_result.get('message', '')}")
        emit("stage", name="verify", status="done", detail=(bb.verify_result or {}).get("message", ""))

    # ── Final validation + parity + reports ──
    from src.validate_lwc import validate_lwc
    for a in bb.artifacts:
        if a.is_lwc:
            # LWC artifacts get the LWC validator, not the Apex governor/schema checks.
            bb.validation_results[f"lwc/{a.target_name}"] = validate_lwc(a.lwc_bundle or {})
            continue
        m, t = f"{a.target_name}.cls", f"{a.target_name}Test.cls"
        bb.validation_results[m] = validate_all(a.main_class, m, bb.schema)
        bb.validation_results[t] = validate_all(a.test_class, t, bb.schema)

    bb.parity = build_parity([g for g in bb.generated_dicts() if g.get("layer") != "Component"])
    if parity_strengthen:
        bb.parity["strengthened"] = parity_strengthen
    write_parity_md(output_dir, bb.parity)
    _write_plan_doc(bb)

    acct = get_accounting()
    ledger = bb.completeness_ledger()
    report_file = generate_report(
        output_dir, bb.validation_results, acct,
        generated_results=bb.generated_dicts(), skipped_domains=[],
        verify_result=bb.verify_result, reconciliation=bb.reconciliation, parity=bb.parity,
        ledger=ledger)

    counts = {}
    for r in ledger:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    ledger_line = ", ".join(f"{v} {k}" for k, v in counts.items()) or "0"

    print("\n═══ Agentic Run Complete ═══")
    print(f"  Report: {report_file}")
    print(f"  Plan + decisions: {Path(output_dir) / 'MIGRATION_PLAN.md'}")
    print(f"  Completeness: {ledger_line}")
    if any(r["outcome"] == "unaccounted" for r in ledger):
        print("  ⚠ some inputs are UNACCOUNTED for — see the completeness ledger in MIGRATION_PLAN.md")
    print(f"  provider(s)={acct.get('providers', {})}  requests={acct['requests']}")
    if bb.open_questions:
        print(f"  Open questions for review: {len(bb.open_questions)} (see MIGRATION_PLAN.md)")

    emit("run_complete",
         ledger=ledger, ledger_summary=counts,
         open_questions=list(bb.open_questions),
         report="FEASIBILITY_REPORT.md", plan="MIGRATION_PLAN.md",
         providers=acct.get("providers", {}), requests=acct.get("requests", 0),
         # The full agent audit trail — every meaningful choice each agent made,
         # in order — so the reviewer can trace the whole run after the fact.
         decisions=[{"agent": d["agent"], "action": d["action"], "detail": d["detail"]}
                    for d in bb.decisions],
         artifacts=[{"target_name": a.target_name, "layer": a.layer, "status": a.status,
                     "is_lwc": a.is_lwc, "review_flags": list(a.review_flags)} for a in bb.artifacts])
    return bb


def _write_plan_doc(bb) -> str:
    lines = ["# Agentic Migration Plan", "",
             "Produced by the Phase-1 agent team. The Planner converts every target's "
             "logic to Apex — flagging any that might fit a native Salesforce product "
             "(e.g. CPQ) for review rather than skipping it; the Critic reviews each built "
             "artifact for behavior, security, and governor safety.", "",
             "## 1. Plan", "",
             "| Target | Pattern | Decision | Rationale |", "|---|---|---|---|"]
    for p in bb.plan:
        if p.target_kind == "Skip":
            decision = "Skipped"
        elif p.native_recommendation:
            decision = f"Converted · review: consider {p.native_recommendation}"
        else:
            decision = "Converted"
        lines.append(f"| `{p.target_name}` | {p.apex_pattern} | {decision} | {p.rationale or '—'} |")

    # ── Completeness ledger: proof that every ingested class is accounted for ──
    ledger = bb.completeness_ledger()
    counts = {}
    for r in ledger:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in counts.items()) or "nothing ingested"
    lines += ["", "## 2. Completeness ledger", "",
              "Every ingested source class is accounted for below — the proof that no "
              "logic was silently dropped. `flagged` = converted in full **and** carries a "
              "native-product review suggestion; `skipped` = no business logic to preserve "
              "(with a reason).", "",
              f"**Summary: {summary}.**", ""]
    if any(r["outcome"] == "unaccounted" for r in ledger):
        lines += ["> ⚠️ **Some inputs are unaccounted for — investigate before relying on this run.**", ""]
    lines += ["| Source class | Layer | Outcome | Target | Note |", "|---|---|---|---|---|"]
    for r in ledger:
        lines.append(f"| `{r['source']}` | {r['layer']} | {r['outcome']} | {r['target']} | {r['note'] or '—'} |")

    # ── Class understanding: the Comprehender's read of each class, persisted so the
    #    extension (which shows reports, not the live stream) has the same insight. ──
    if bb.comprehensions:
        lines += ["", "## 3. Class understanding (Comprehender)", "",
                  "What the AI understood about each class before building — including the "
                  "business rules it must preserve, concrete migration risks, and a complexity "
                  "rating. This is the same insight the web dashboard shows live.", ""]
        for name, u in bb.comprehensions.items():
            if not isinstance(u, dict):
                continue
            cx = u.get("complexity") or "—"
            purpose = u.get("purpose") if isinstance(u.get("purpose"), str) else ""
            lines.append(f"### `{name}`  ·  complexity: **{cx}**")
            if purpose:
                lines.append(purpose)
            for label, key in (("Business rules to preserve", "business_rules"),
                               ("⚠ Migration risks", "migration_risks")):
                items = [x for x in (u.get(key) or []) if x]
                if items:
                    lines.append(f"- _{label}:_")
                    lines += [f"  - {x}" for x in items]
            lines.append("")

    lines += ["", "## 4. Artifact review (Critic)", "",
              "Each generated artifact with the Critic's findings and a concrete suggested fix "
              "for each.", ""]
    for a in bb.artifacts:
        target = f"lwc/{a.target_name}" if a.is_lwc else f"{a.target_name}.cls"
        lines.append(f"### `{target}` — {a.status}")
        if not a.critic_findings:
            lines.append("- ✓ Critic clean — no findings")
        for f in a.critic_findings:
            sev = f.get("severity", "?"); cat = f.get("category", ""); msg = f.get("message", "")
            lines.append(f"- **{sev}** [{cat}] {msg}")
            if f.get("suggestion"):
                lines.append(f"  - 💡 _Fix:_ {f['suggestion']}")
        lines.append("")

    lines += ["## 5. Decisions log", "", bb.decisions_markdown(), "",
              "## 6. Open questions for human review", ""]
    lines += ([f"- {q}" for q in bb.open_questions] or ["_(none)_"])

    path = Path(bb.output_dir) / "MIGRATION_PLAN.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)
