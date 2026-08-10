"""
main.py — CLI entry point for h2a-mvp.

Commands:
  ping          Test LLM provider connectivity (Anthropic / mock).
  ingest        Parse Hybris Java/Spring sources and items.xml.
  run           Execute the full migration pipeline (ingest -> comprehend -> generate).
  repo-migrate  Repository-scale multi-domain migration (topological, schema-grounded).
  metadata      Compile items.xml to SObject metadata.
  report        Generate the feasibility report with validation results.
"""

import argparse
import sys
import io

# Force stdout/stderr to be UTF-8 encoded to avoid crashes on Windows cp1252 consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


def cmd_ping(args):
    """Test connectivity to the configured LLM provider (Anthropic / mock)."""
    from src.llm import ping

    result = ping()
    print(f"\n✓ Provider: {result['provider']}  Model: {result['model']}")
    print(f"  Model reply: {result['reply']}")
    print(f"  requests={result['requests']}  "
          f"prompt_tokens={result['prompt_tokens']}  "
          f"completion_tokens={result['completion_tokens']}  "
          f"cached={result['cached']}")


def cmd_ingest(args):
    """Parse Hybris Java sources and items.xml."""
    from src.ingest import ingest

    result = ingest(args.input)

    # Build a display-friendly summary (exclude full source for readability)
    display = {
        "classes": [],
        "item_types": result["item_types"],
        "dependency_order": result["dependency_order"],
        "api_requests": result["api_requests"],
    }
    for cls in result["classes"]:
        display["classes"].append({
            "class_name": cls["class_name"],
            "layer": cls["layer"],
            "file": cls["file"],
            "annotations": cls["annotations"],
            "fields": cls["fields"],
            "methods": cls["methods"],
            "referenced_types": cls["referenced_types"],
        })

    import json
    print(json.dumps(display, indent=2))


def cmd_run(args):
    """Execute the full migration pipeline."""
    import json
    from src.ingest import ingest
    from src.comprehend import comprehend_class
    from src.generate import (
        plan_targets, generate_apex, extract_method_signatures,
        write_outputs, _load_mappings,
    )
    from src.llm import reset_accounting, get_accounting

    reset_accounting()
    offline = getattr(args, "offline", False)

    from src.schema import build_schema

    # Stage 1: Ingest
    print("═══ Stage 1: Ingest ═══")
    ingest_result = ingest(args.input)
    classes = ingest_result["classes"]
    item_types = ingest_result["item_types"]
    schema = build_schema(item_types, ingest_result.get("relations", []))
    print(f"  Parsed {len(classes)} classes, {len(item_types)} item types, "
          f"{len(schema)} SObjects")
    print(f"  Dependency order: {ingest_result['dependency_order']}")

    # Stage 2: Comprehend (skip Model/DTO — trivial data class)
    print("\n═══ Stage 2: Comprehend ═══")
    comprehensions = {}
    for cls in classes:
        if cls["layer"] == "Model":
            print(f"  ⏭ {cls['class_name']} (Model/DTO — skipped, deterministic)")
            continue
        print(f"  🔍 Comprehending {cls['class_name']} ({cls['layer']})...")
        comp = comprehend_class(cls, offline=offline)
        comprehensions[cls["class_name"]] = comp
        print(f"     Purpose: {comp.get('purpose', 'N/A')}")

    # Stage 3: Generate
    print("\n═══ Stage 3: Map + Generate ═══")
    targets = plan_targets(classes)
    mappings = _load_mappings()
    generated = []
    generated_sigs = {}

    for target in targets:
        source_names = ", ".join(c["class_name"] for c in target["source_classes"])
        print(f"  ⚙ Generating {target['target_name']} (from {source_names})...")

        gen_result = generate_apex(
            target, comprehensions, generated_sigs, offline=offline,
            schema=schema, mappings=mappings,
        )

        # Preserve source info for MAPPING.md
        gen_result["source_classes"] = target["source_classes"]
        gen_result["layer"] = target["layer"]

        # Run validation & repair loop (schema + governor rules)
        from src.validate import validate_all, repair

        for class_key, code_field in [("main_class", "main_class"), ("test_class", "test_class")]:
            filename = f"{target['target_name']}.cls" if class_key == "main_class" else f"{target['target_name']}Test.cls"
            code = gen_result[code_field]

            issues = validate_all(code, filename, schema)
            attempt = 1
            max_repair = 2

            while issues and attempt <= max_repair:
                print(f"    ⚠ Validation issues in {filename}: {[i['rule'] for i in issues]}")
                print(f"    🛠 Attempting repair {attempt}/{max_repair}...")
                repaired_code = repair(code, issues, attempt=attempt, offline=offline, schema=schema)
                new_issues = validate_all(repaired_code, filename, schema)
                
                if len(new_issues) < len(issues) or not new_issues:
                    print(f"      ✓ Repair improved issues count from {len(issues)} to {len(new_issues)}.")
                    code = repaired_code
                    issues = new_issues
                else:
                    print(f"      ✗ Repair did not reduce issues count.")
                attempt += 1
                
            if issues:
                print(f"    🚨 [Escalation] Remaining issues in {filename} after repair: {issues}")
            gen_result[code_field] = code

        generated.append(gen_result)

        # Extract method sigs for downstream dependency injection
        sigs = extract_method_signatures(gen_result["main_class"], target["target_name"])
        generated_sigs[target["target_name"]] = sigs
        print(f"     Generated {target['target_name']}.cls + {target['target_name']}Test.cls")

    # Write outputs
    print("\n═══ Writing Output ═══")
    created = write_outputs(args.output, generated, item_types, mappings)
    for f in created:
        print(f"  ✓ {f}")

    # Run validation again on output files for final reporting
    from src.report import generate_report
    validation_results = {}
    for gen in generated:
        m_file = f"{gen['target_name']}.cls"
        t_file = f"{gen['target_name']}Test.cls"
        validation_results[m_file] = validate_all(gen["main_class"], m_file, schema)
        validation_results[t_file] = validate_all(gen["test_class"], t_file, schema)

    acct = get_accounting()
    report_file = generate_report(
        args.output, validation_results, acct,
        generated_results=generated,
    )
    print(f"  ✓ Generated feasibility report: {report_file}")

    # Token accounting
    print(f"\n═══ Token Accounting ═══")
    print(f"  requests={acct['requests']}  "
          f"prompt_tokens={acct['prompt_tokens']}  "
          f"completion_tokens={acct['completion_tokens']}")


def cmd_report(args):
    """Generate the feasibility report."""
    from pathlib import Path
    from src.validate import validate_tier1
    from src.report import generate_report

    out_dir = Path(args.output)
    if not out_dir.exists():
        print(f"Error: Output directory '{args.output}' does not exist. Run 'run' command first.")
        sys.exit(1)

    # Scan for generated cls files
    validation_results = {}
    for f in sorted(out_dir.glob("*.cls")):
        filename = f.name
        code = f.read_text(encoding="utf-8")
        validation_results[filename] = validate_tier1(code, filename)

    # Empty token accounting (since report is run offline from disk files)
    report_file = generate_report(str(out_dir), validation_results)
    print(f"\n✓ Feasibility report generated successfully at: {report_file}")


def cmd_metadata(args):
    """Compile items.xml configurations into Salesforce metadata XML formats."""
    from src.metadata_generator import generate_salesforce_metadata
    from pathlib import Path
    import os
    
    input_path = Path(args.input)
    xml_files = []
    
    if input_path.is_file():
        if input_path.name.endswith("-items.xml") or input_path.name == "items.xml":
            xml_files.append(input_path)
    else:
        for root, _, files in os.walk(str(input_path)):
            for file in files:
                if file.endswith("-items.xml") or file == "items.xml":
                    xml_files.append(Path(root) / file)
                    
    if not xml_files:
        print(f"Warning: No items XML files (*-items.xml or items.xml) found inside {input_path}")
        sys.exit(0)
        
    for xml_file in xml_files:
        print(f"Compiling metadata from: {xml_file}")
        generate_salesforce_metadata(str(xml_file), args.output)


def cmd_repo_migrate(args):
    """Run sequential repository-scale multi-domain migrations."""
    from src.pipeline_driver import run_repo_migration
    offline = getattr(args, "offline", False)
    verify = True if getattr(args, "verify", False) else None
    run_repo_migration(args.input, args.output, offline=offline, verify=verify)


def cmd_agent_migrate(args):
    """Run the Phase-1 agentic migration (Planner + Builder + Critic + Verifier)."""
    from src.agentic import run_agentic_migration
    offline = getattr(args, "offline", False)
    verify = True if getattr(args, "verify", False) else None
    run_agentic_migration(args.input, args.output, offline=offline, verify=verify)


def cmd_impex(args):
    """Translate Hybris .impex data files into Salesforce CSVs + an upsert runbook."""
    from src.impex import translate_impex_dir
    summary = translate_impex_dir(args.input, args.output)
    if not summary["impex_files"]:
        print(f"No .impex files found under {args.input}.")
        return
    print(f"Parsed {len(summary['impex_files'])} .impex file(s) → "
          f"{len(summary['objects'])} object(s), {summary['record_total']} record(s).")
    for o in summary["objects"]:
        print(f"  • {o['object']}: {o['records']} record(s), external id = {o['external_id'] or '(none)'}")
    for f in summary["files_written"]:
        print(f"  ✓ {f}")


def cmd_cronjob(args):
    """Translate Hybris cron triggers (Spring XML / ImpEx) into a Scheduled Apex runbook."""
    from src.cronjob import translate_cronjobs_dir
    summary = translate_cronjobs_dir(args.input, args.output)
    if not summary["triggers"]:
        print(f"No cron triggers found under {args.input}.")
        return
    print(f"Found {len(summary['triggers'])} trigger(s): "
          f"{summary['resolved_count']} resolved, {summary['unresolved_count']} unresolved.")
    for t in summary["triggers"]:
        status = "✓" if t["resolved"] else "⚠"
        print(f"  {status} {t['job_class']}: '{t['cron_expression']}' "
              f"({'active' if t['active'] else 'inactive'})")
    for f in summary["files_written"]:
        print(f"  ✓ {f}")


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse CLI parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="h2a-mvp",
        description="Hybris-to-Apex Migration Feasibility MVP",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ping
    subparsers.add_parser("ping", help="Test LLM provider connectivity (Anthropic / mock)")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Parse Hybris Java sources and items.xml")
    p_ingest.add_argument("--input", required=True, help="Path to Hybris source directory")

    # run
    p_run = subparsers.add_parser("run", help="Execute full migration pipeline")
    p_run.add_argument("--input", required=True, help="Path to Hybris source directory")
    p_run.add_argument("--output", required=True, help="Path to output directory")
    p_run.add_argument("--offline", action="store_true", help="Replay cached responses only")

    # report
    p_report = subparsers.add_parser("report", help="Generate feasibility report")
    p_report.add_argument("--output", default="demo_output", help="Path to output directory")

    # metadata
    p_meta = subparsers.add_parser("metadata", help="Compile database structures to Salesforce SObject XML formats")
    p_meta.add_argument("--input", required=True, help="Path to items.xml or directory containing it")
    p_meta.add_argument("--output", required=True, help="Path to output directory")

    # repo-migrate
    p_repo = subparsers.add_parser("repo-migrate", help="Translate entire multi-domain codebase topologically")
    p_repo.add_argument("--input", required=True, help="Path to codebase root directory")
    p_repo.add_argument("--output", required=True, help="Path to output directory")
    p_repo.add_argument("--offline", action="store_true", help="Replay cached responses only")
    p_repo.add_argument("--verify", action="store_true",
                        help="Dry-run deploy the output against a Salesforce org (needs `sf` CLI)")

    # agent-migrate (Phase 1: agentic core)
    p_agent = subparsers.add_parser(
        "agent-migrate",
        help="Agentic migration: Planner + Builder + Critic + Verifier over a shared blackboard")
    p_agent.add_argument("--input", required=True, help="Path to codebase root directory")
    p_agent.add_argument("--output", required=True, help="Path to output directory")
    p_agent.add_argument("--offline", action="store_true", help="Replay cached responses only")
    p_agent.add_argument("--verify", action="store_true",
                         help="Dry-run deploy + self-heal against a Salesforce org (needs `sf` CLI)")

    # impex (Phase 2: data migration)
    p_impex = subparsers.add_parser(
        "impex", help="Translate Hybris .impex data files into Salesforce CSVs + upsert runbook")
    p_impex.add_argument("--input", required=True, help="Directory containing .impex files")
    p_impex.add_argument("--output", required=True, help="Path to output directory")

    # cronjob (Phase 2: scheduled jobs)
    p_cron = subparsers.add_parser(
        "cronjob", help="Translate Hybris cron triggers (Spring XML / ImpEx) into a Scheduled Apex runbook")
    p_cron.add_argument("--input", required=True, help="Directory containing Spring XML / .impex trigger definitions")
    p_cron.add_argument("--output", required=True, help="Path to output directory")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "ping": cmd_ping,
        "ingest": cmd_ingest,
        "run": cmd_run,
        "report": cmd_report,
        "metadata": cmd_metadata,
        "repo-migrate": cmd_repo_migrate,
        "agent-migrate": cmd_agent_migrate,
        "impex": cmd_impex,
        "cronjob": cmd_cronjob,
    }

    from src.llm import ProviderAuthError

    handler = dispatch.get(args.command)
    if handler:
        try:
            handler(args)
        except ProviderAuthError as e:
            # A stack trace here would bury the one line that tells the operator what to
            # do about it, and this failure is configuration, not a crash.
            print(f"\n✗ {e}\n\n  Nothing was generated and nothing was charged.",
                  file=sys.stderr)
            sys.exit(2)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
