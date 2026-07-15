"""
pipeline_driver.py — Orchestrator for repository-scale Hybris→Apex migration.

Translates a monolith domain-by-domain in topological order, grounding every
generation in the derived SObject schema, injecting only the *scoped* upstream
signatures a domain actually depends on, validating against schema + governor
rules, and (optionally) verifying the output compiles against a real org.
"""

from __future__ import annotations

import os
import traceback
from pathlib import Path

from src.repo_analyzer import get_translation_schedule, build_dependency_graph
from src.signature_registry import SignatureRegistry
from src.ingest import ingest
from src.comprehend import comprehend_class
from src.generate import (
    plan_targets, generate_apex, extract_method_signatures, write_outputs, _load_mappings,
)
from src.validate import validate_all, repair
from src.report import generate_report
from src.llm import reset_accounting, get_accounting, _load_config, _get_provider
from src.state_ledger import load_ledger, save_ledger, get_domain_source_hash, calculate_md5
from src.schema import build_schema


def _transitive_deps(adjacency: dict, domain: str) -> set:
    """All domains reachable from `domain` (its dependency closure)."""
    seen, stack = set(), list(adjacency.get(domain, []))
    while stack:
        d = stack.pop()
        if d in seen:
            continue
        seen.add(d)
        stack.extend(adjacency.get(d, []))
    return seen


def run_repo_migration(input_dir: str, output_dir: str, *, offline: bool = False,
                       verify: bool | None = None):
    reset_accounting()
    config = _load_config()

    print("=== Repository Modularity Analysis ===")
    schedule = get_translation_schedule(input_dir)
    adjacency_list, domains = build_dependency_graph(input_dir)
    print(f"  Detected Domains: {list(domains.keys())}")
    print(f"  Dependency Graph: {adjacency_list}")
    print(f"  Topological Execution Order: {schedule}")

    try:
        from src.repo_analyzer import extract_method_call_graph
        extract_method_call_graph(input_dir, output_dir)
        print("  ✓ Extracted modular call graph for the dashboard")
    except Exception as ge:
        print(f"  ⚠ Skipped call graph extraction: {ge}")

    registry = SignatureRegistry()
    global_generated = []
    global_validation_results = {}
    mappings = _load_mappings()

    env_inc = os.environ.get("H2A_INCREMENTAL")
    incremental = (env_inc.lower() in ("true", "1", "yes")) if env_inc is not None \
        else config.get("incremental", True)

    mappings_file = config.get("mappings_file", "mappings/hybris_to_apex.yaml")
    mappings_hash = calculate_md5(Path(__file__).resolve().parent.parent / mappings_file)
    config_hash = calculate_md5(Path(__file__).resolve().parent.parent / "config.yaml")

    current_ledger = load_ledger(output_dir) if incremental else {}
    new_ledger = {}

    ingest_result = ingest(input_dir)
    all_classes = ingest_result["classes"]
    item_types = ingest_result["item_types"]
    relations = ingest_result.get("relations", [])
    enum_types = ingest_result.get("enum_types", [])

    # Ground everything in the derived SObject schema.
    schema = build_schema(item_types, relations, enum_types)
    print(f"  Derived SObject schema: {len(schema)} objects "
          f"({sum(len(m['fields']) for m in schema.values())} custom fields)")

    max_repair = config.get("max_repair_attempts", 2)
    skipped_domains = []
    any_upstream_changed = False

    for domain in schedule:
        print(f"\n==========================================")
        print(f"  Translating Domain Module: {domain}")
        print(f"==========================================")

        domain_class_names = {c["class_name"] for c in domains[domain]}
        domain_classes = [c for c in all_classes if c["class_name"] in domain_class_names]
        if not domain_classes:
            print(f"  No Java classes matched domain: {domain}. Skipping.")
            continue

        domain_source_hash = get_domain_source_hash(domain_classes)
        can_reuse = (
            incremental and domain in current_ledger and not any_upstream_changed
            and current_ledger[domain].get("source_hash") == domain_source_hash
            and current_ledger[domain].get("mappings_hash") == mappings_hash
            and current_ledger[domain].get("config_hash") == config_hash
        )
        if can_reuse:
            print(f"  ⏭ Reusing cached migration for domain: {domain} (unchanged)")
            cached_info = current_ledger[domain]
            new_ledger[domain] = cached_info
            for target_name, sigs in cached_info.get("signatures", {}).items():
                registry.register(domain, target_name, sigs)
            for gen in cached_info.get("generated_files", []):
                global_generated.append(gen)
            continue

        any_upstream_changed = True
        domain_entry = {
            "source_hash": domain_source_hash, "mappings_hash": mappings_hash,
            "config_hash": config_hash, "generated_files": [], "signatures": {},
        }

        try:
            # Comprehend
            print("\n  --- Comprehend ---")
            comprehensions = {}
            for cls in domain_classes:
                if cls["layer"] == "Model":
                    print(f"    ⏭ {cls['class_name']} (Model/DTO — deterministic)")
                    continue
                print(f"    🔍 {cls['class_name']} ({cls['layer']})")
                comp = comprehend_class(cls, offline=offline)
                comprehensions[cls["class_name"]] = comp

            # Scope: only signatures from the domains this one depends on.
            dep_domains = _transitive_deps(adjacency_list, domain)
            scoped_sigs = registry.get_signatures_for_domains(dep_domains)

            # Generate
            print("  --- Generate ---")
            for target in plan_targets(domain_classes):
                source_names = ", ".join(c["class_name"] for c in target["source_classes"])
                print(f"    ⚙ {target['target_name']} (from {source_names})")

                gen_result = generate_apex(
                    target, comprehensions, scoped_sigs,
                    offline=offline, schema=schema, mappings=mappings,
                )
                gen_result["source_classes"] = target["source_classes"]
                gen_result["layer"] = target["layer"]
                # Merge comprehended business rules for the parity harness.
                target_rules = []
                for c in target["source_classes"]:
                    target_rules.extend(comprehensions.get(c["class_name"], {}).get("business_rules", []) or [])
                gen_result["business_rules"] = target_rules

                # Validate + repair (schema + governor rules)
                for code_field in ("main_class", "test_class"):
                    is_test = code_field == "test_class"
                    filename = f"{target['target_name']}{'Test' if is_test else ''}.cls"
                    code = gen_result[code_field]
                    issues = validate_all(code, filename, schema)
                    attempt = 1
                    while issues and attempt <= max_repair:
                        print(f"      ⚠ {filename}: {[i['rule'] for i in issues]} — repair {attempt}")
                        repaired = repair(code, issues, attempt=attempt, offline=offline,
                                          signatures=scoped_sigs, schema=schema)
                        new_issues = validate_all(repaired, filename, schema)
                        if len(new_issues) < len(issues) or not new_issues:
                            code, issues = repaired, new_issues
                        attempt += 1
                    gen_result[code_field] = code

                global_generated.append(gen_result)
                sigs = extract_method_signatures(gen_result["main_class"], target["target_name"])
                registry.register(domain, target["target_name"], sigs)
                domain_entry["generated_files"].append({
                    "target_name": target["target_name"],
                    "main_class": gen_result["main_class"],
                    "test_class": gen_result["test_class"],
                    "mapping_notes": gen_result.get("mapping_notes", ""),
                    "sobject_refs": gen_result.get("sobject_refs", []),
                    "source_classes": [{"class_name": c["class_name"]} for c in target["source_classes"]],
                    "layer": target["layer"],
                    "business_rules": target_rules,
                })
                domain_entry["signatures"][target["target_name"]] = sigs

            new_ledger[domain] = domain_entry

        except Exception as e:
            traceback.print_exc()
            msg = str(e)
            if "credit" in msg.lower() or "401" in msg or "rate_limit" in msg.lower():
                print(f"\n  ⚠ Provider error ({msg[:120]}). Stopping.")
                skipped_domains.append(domain)
                skipped_domains.extend(schedule[schedule.index(domain) + 1:])
                break
            print(f"\n  ⚠ Error translating '{domain}': {msg}. Skipping.")
            skipped_domains.append(domain)
            continue

    if incremental:
        save_ledger(output_dir, new_ledger)
    if skipped_domains:
        print(f"\n  ℹ Skipped domains ({len(skipped_domains)}): {skipped_domains[:10]}")

    print("\n═══ Writing Repository Outputs ═══")
    created = write_outputs(output_dir, global_generated, item_types, mappings)
    for f in created:
        print(f"  ✓ {f}")

    # ── Schema reconciliation ──
    # Auto-resolve unknown-field/object warnings using Hybris-source evidence:
    # fields the source really uses (but items.xml never declared) are ADDED to
    # the schema; unsupported references stay flagged for review.
    from src.schema import reconcile_schema
    from src.metadata_generator import write_schema_metadata
    from src.parity import build_parity, write_parity_md

    source_corpus = "\n".join(c.get("source", "") for c in all_classes)
    prelim_validation = {}
    for gen in global_generated:
        prelim_validation[f"{gen['target_name']}.cls"] = validate_all(gen["main_class"], f"{gen['target_name']}.cls", schema)
    schema, reconciliation = reconcile_schema(schema, prelim_validation, source_corpus)
    if reconciliation["added_fields"] or reconciliation["added_objects"]:
        print(f"  ✓ Schema reconciliation: +{len(reconciliation['added_objects'])} object(s), "
              f"+{len(reconciliation['added_fields'])} field(s) evidenced in source")
    if reconciliation["flagged"]:
        print(f"  ⚠ Schema reconciliation flagged {len(reconciliation['flagged'])} reference(s) "
              f"with no source evidence (left for review)")

    # ── Emit SObject metadata from the reconciled schema ──
    # Without this the Apex references custom objects/fields that don't exist in
    # the org and any real deploy fails immediately.
    meta_written = write_schema_metadata(output_dir, schema)
    print(f"  ✓ Wrote SObject metadata: {len(meta_written)} object/field file(s)")

    # ── ImpEx data migration (Phase 2) ──
    from src.impex import translate_impex_dir
    impex_summary = translate_impex_dir(input_dir, output_dir)
    if impex_summary["impex_files"]:
        print(f"  ✓ ImpEx: {impex_summary['record_total']} record(s) across "
              f"{len(impex_summary['objects'])} object(s) → data/ + DATA_MIGRATION.md")

    # ── Cronjob scheduling (Phase 2) ──
    from src.cronjob import translate_cronjobs_dir
    cron_summary = translate_cronjobs_dir(input_dir, output_dir)
    if cron_summary["triggers"]:
        print(f"  ✓ Cronjobs: {cron_summary['resolved_count']} trigger(s) resolved → "
              f"CRON_JOBS.md + schedule.apex")

    # ── Parity-driven test strengthening ──
    # Turn the parity harness from measurement into improvement: add assertions
    # for the business rules the tests don't yet check. Runs before deploy
    # verification so the strengthened tests are themselves verified. Skipped for
    # the mock provider (no real LLM to write the assertions).
    parity_strengthen = None
    pcfg = config.get("parity", {})
    if pcfg.get("strengthen", True) and not offline and _get_provider(config) != "mock":
        from src.parity import close_parity_gaps
        parity_strengthen = close_parity_gaps(
            global_generated, output_dir, offline=offline, schema=schema,
            max_attempts=pcfg.get("max_attempts", 1),
        )
        if parity_strengthen.get("rules_closed"):
            print(f"  ✓ Parity strengthening: asserted {parity_strengthen['rules_closed']} more "
                  f"business rule(s) across {len(parity_strengthen['targets_improved'])} class(es)")

    # Optional real compile verification against a Salesforce org, with a
    # self-healing loop: real compiler errors are fed back into the LLM repair
    # loop and the offending classes are rewritten + re-deployed until green.
    do_verify = verify if verify is not None else config.get("verify", {}).get("deploy", False)
    verify_result = None
    if do_verify:
        vcfg = config.get("verify", {})
        print("\n═══ Deploy Verification + Self-Healing (sf CLI) ═══")
        from src.verify import deploy_and_heal
        # Flat signature list across every generated class, to ground repairs in
        # the real (cross-class) API surface the compiler is checking against.
        all_sigs = []
        for gen in global_generated:
            all_sigs.extend(extract_method_signatures(gen.get("main_class", ""), gen["target_name"]))
        verify_result = deploy_and_heal(
            output_dir, global_generated,
            schema=schema, signatures=all_sigs, offline=offline,
            target_org=vcfg.get("target_org") or None,
            run_tests=vcfg.get("run_tests", False),
            auto_repair=vcfg.get("auto_repair", True),
            max_attempts=vcfg.get("max_deploy_attempts", max_repair),
            source_corpus=source_corpus,
            coverage_threshold=vcfg.get("coverage_threshold", 75.0),
        )
        print(f"  {verify_result['message']}")

    # Recompute offline validation *after* healing + reconciliation so the report
    # reflects the code on disk and the augmented schema (added fields no longer
    # flagged as unknown).
    for gen in global_generated:
        m_file = f"{gen['target_name']}.cls"
        t_file = f"{gen['target_name']}Test.cls"
        global_validation_results[m_file] = validate_all(gen["main_class"], m_file, schema)
        global_validation_results[t_file] = validate_all(gen["test_class"], t_file, schema)

    # ── Behavioral parity harness ──
    parity = build_parity(global_generated)
    if parity_strengthen:
        parity["strengthened"] = parity_strengthen
    parity_file = write_parity_md(output_dir, parity)
    if parity["overall"]["score"] is not None:
        print(f"  ✓ Behavioral parity: {parity['overall']['score']}% of business rules asserted "
              f"({parity_file})")

    acct = get_accounting()
    report_file = generate_report(
        output_dir, global_validation_results, acct,
        generated_results=global_generated, skipped_domains=skipped_domains,
        verify_result=verify_result, reconciliation=reconciliation, parity=parity,
    )
    print(f"  ✓ Feasibility report: {report_file}")

    print(f"\n═══ Token Accounting ═══")
    print(f"  provider(s)={acct.get('providers', {})}  requests={acct['requests']}  "
          f"prompt_tokens={acct['prompt_tokens']}  completion_tokens={acct['completion_tokens']}  "
          f"cache_read={acct.get('cache_read_tokens', 0)}  cache_write={acct.get('cache_write_tokens', 0)}")
