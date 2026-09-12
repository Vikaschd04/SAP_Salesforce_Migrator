"""
report.py — Generate the feasibility report with dynamic inventory
from actual migration results.
"""

from pathlib import Path


# Map layer names to Salesforce design patterns

def _pipeline_words() -> dict:
    """How this run should describe itself. [1.39]

    The feasibility report opened "SAP Hybris to Salesforce Apex Migration" whichever
    migration produced it, and listed `.java` sources beside `.cls` targets for a run that
    reads PHP and writes Java. A report whose *title* names the wrong pipeline is not a
    cosmetic problem: it is the first thing a stakeholder reads.
    """
    try:
        from src import pipeline
        pipeline.ensure_registered()
        p = pipeline.active_or_shipped()
        src_lang = getattr(p.source, "code_language", "code")
        tgt_lang = getattr(p.target, "code_language", "code")
        return {
            "source": p.source.label.split(" (")[0],
            "target": p.target.label.split(" (")[0],
            "source_lang": src_lang,
            "target_lang": tgt_lang,
            "source_ext": {"Java": ".java", "PHP": ".php"}.get(src_lang, ""),
            "target_ext": {"Apex": ".cls", "Java": ".java"}.get(tgt_lang, ""),
            # Each target polices a different thing, and naming the wrong one tells a
            # reviewer to check something the platform does not have. [1.39]
            "limits": ("governor-limit safety" if tgt_lang == "Apex"
                       else "resolvable types and bounded queries"),
            #: What the *source* calls its query language, so advice about translating
            #: queries names the thing the reader will actually search for.
            "query_language": {"hybris": "Hybris FlexibleSearch",
                               "adobe-commerce": "Magento collections and select()"
                               }.get(getattr(p.source, "platform", ""),
                                     "the source's own query language"),
            "cli": "Salesforce CLI" if tgt_lang == "Apex" else "compiler",
        }
    except Exception:
        return {"source": "the source platform", "target": "the target platform",
                "source_lang": "code", "target_lang": "code",
                "source_ext": "", "target_ext": "",
                "limits": "platform limits", "cli": "the platform's tooling",
                "query_language": "the source's own query language"}


#: The shape each source layer takes on the target, in that target's own vocabulary. One
#: table per target: "Selector Pattern" and "Bulkified Service Class" are Salesforce
#: answers, and labelling a generated Hybris service with them describes a migration that
#: did not happen. [1.39]

def _review_checklist(words: dict) -> list:
    """What a reviewer should actually check, per target. [1.39]

    "Verify generated Apex handles collections without hitting governor limits" is sound
    advice about Salesforce and meaningless about a Hybris extension, which has neither
    governor limits nor SOQL. A checklist that lists checks the platform cannot fail is
    how a reviewer learns to skim the checklist.
    """
    if words.get("target_lang") == "Apex":
        return [
            "- [ ] **Bulk Safety**: Verify that generated Apex methods handle collections "
            "without hitting governor limits on DML/SOQL.",
            "- [ ] **Query Equivalency**: Manually test SOQL queries to ensure correct "
            f"mapping of joins or conditions from {words['query_language']}.",
        ]
    return [
        "- [ ] **Query bounds**: Every generated FlexibleSearch is parameterised and "
        "bounded. Confirm the bound is the one the source intended, not just present.",
        "- [ ] **Wiring**: Each emitted bean is declared in the extension's spring.xml and "
        "each cronjob's ImpEx names a bean that exists — an unresolved springId imports "
        "cleanly and fails the first time the job runs.",
        "- [ ] **Interceptor scope**: An interceptor fires for every save of its item "
        "type, wherever that save came from. Anything conditional in the original plugin "
        "has to become an explicit condition.",
        "- [ ] **Listener ordering**: Hybris publishes events asynchronously and unordered "
        "by default. Confirm nothing downstream depended on an observer having already "
        "run.",
    ]


_LAYER_PATTERNS = {
    "Model": "Custom Object (SObject)",
    "DAO": "Selector Pattern",
    "Service": "Bulkified Service Class",
    "Facade": "Merged into Service Layer",
    "Controller": "REST Resource (@RestResource)",
    "Utility": "Apex Helper Class",
    "Job": "Scheduled Apex (Schedulable)",
    "Component": "Lightning Web Component (LWC)",
}

_LAYER_PATTERNS_HYBRIS = {
    "Model": "Item type (items.xml)",
    "DAO": "DAO with FlexibleSearch",
    "Service": "Spring service (interface + Default impl)",
    "Facade": "Merged into the service layer",
    "Controller": "OCC controller",
    "Utility": "Spring bean",
    "Job": "AbstractJobPerformable + cronjob",
    "Api": "Spring service (interface + Default impl)",
    "Plugin": "Decorator or interceptor",
    "Observer": "Event listener",
    "Cron": "AbstractJobPerformable + cronjob",
}


def _pattern_for(layer: str, words: dict) -> str:
    """The design-pattern cell, in the running target's vocabulary."""
    if words.get("target_lang") == "Java":
        return _LAYER_PATTERNS_HYBRIS.get(layer, "Spring bean")
    return _LAYER_PATTERNS.get(layer, "Apex Helper Class")


def _confidence_label(score: int) -> str:
    if score >= 85:
        return "High"
    if score >= 60:
        return "Medium"
    return "Low"


def _compute_confidence(generated_results: list, validation_results: dict,
                        verify_result: dict | None) -> dict:
    """
    Per-artifact confidence, derived from evidence rather than asserted:
      - offline validation (governor + schema grounding) errors/warnings,
      - whether a real org deploy ran and compiled the class,
      - whether the class had to be auto-healed to get there.

    A real, clean org deploy is the strongest signal; with no org at all we cap
    confidence — unverified output is never presented as certain. Returns
    {target_name: {"score": int, "label": str, "basis": str}}.
    """
    ran = bool(verify_result and verify_result.get("available") and verify_result.get("ran"))
    deploy_ok = bool(ran and verify_result.get("success"))
    healed = set((verify_result or {}).get("healing", {}).get("healed_files", []))
    deploy_err_files = {Path(e.get("file", "")).name
                        for e in (verify_result or {}).get("errors", [])}

    out = {}
    for gen in generated_results:
        name = gen.get("target_name", "Unknown")
        files = (f"{name}.cls", f"{name}Test.cls")
        errors = warnings = 0
        for f in files:
            for i in validation_results.get(f, []):
                if i.get("severity") == "ERROR":
                    errors += 1
                else:
                    warnings += 1

        score = 100 - 22 * errors - 7 * warnings
        basis = []

        if ran:
            if deploy_err_files & set(files):
                score = min(score, 45)
                basis.append("failed org deploy")
            elif deploy_ok:
                if errors == 0:
                    score = max(score, 88)
                basis.append("deployed cleanly to org")
            if healed & set(files):
                basis.append("auto-healed from compiler errors")
        else:
            score = min(score, 75)
            basis.append("unverified — no org deploy" if verify_result else "offline validation only")

        if errors:
            basis.append(f"{errors} offline error(s)")
        if warnings:
            basis.append(f"{warnings} warning(s)")

        score = max(5, min(99, score))
        out[name] = {"score": score, "label": _confidence_label(score),
                     "basis": ", ".join(basis) or "offline validation clean"}
    return out


def generate_report(output_dir: str, validation_results: dict = None,
                    token_accounting: dict = None,
                    generated_results: list = None,
                    skipped_domains: list = None,
                    verify_result: dict = None,
                    reconciliation: dict = None,
                    parity: dict = None,
                    ledger: list = None) -> str:
    """
    Generate FEASIBILITY_REPORT.md in the output directory.

    Args:
        output_dir: Output directory path.
        validation_results: Dict of filename -> list of issue dicts.
        token_accounting: Dict containing LLM API request/token totals.
        generated_results: List of generated result dicts with source_classes,
                          target_name, layer, mapping_notes.
        skipped_domains: List of domain names that were skipped during translation.

    Returns:
        Path to the generated report file.
    """
    _w = _pipeline_words()
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    report_file = out_path / "FEASIBILITY_REPORT.md"

    if validation_results is None:
        validation_results = {}
    if token_accounting is None:
        token_accounting = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0}
    if generated_results is None:
        generated_results = []
    if skipped_domains is None:
        skipped_domains = []

    confidence = _compute_confidence(generated_results, validation_results, verify_result)

    # Build the report sections
    sections = [
        f"# Feasibility Study Report: {_w['source']} to {_w['target']} Migration",
        "",
        f"This report evaluates the feasibility of migrating {_w['source_lang']} source "
        f"code from {_w['source']} into functionally equivalent {_w['target']} "
        f"{_w['target_lang']}, based on deterministic and LLM-driven generation.",
        "",
    ]

    # ── Section 1: Migration Inventory ──
    sections.extend([
        "## 1. Migration Inventory",
        "",
        "The following components were analyzed and processed in this iteration:",
        "",
        f"| Source {_w['source']} Class | Inferred Layer | Target {_w['target_lang']} "
        "Artifact | Target Design Pattern | Confidence |",
        "|---|---|---|---|---|",
    ])

    if generated_results:
        for gen in generated_results:
            target_name = gen.get("target_name", "Unknown")
            layer = gen.get("layer", "Utility")
            pattern = _pattern_for(layer, _w)
            is_lwc = layer == "Component"
            # The *source's* extension. Hardcoded `.java`, this listed a Magento module's
            # PHP classes as `StoreConfigInterface.java` — a filename that appears nowhere
            # in the customer's repository. [1.39]
            ext = ".ts" if is_lwc else (_w["source_ext"] or "")
            source_classes = gen.get("source_classes", [])
            source_names = ", ".join(
                f"`{c['class_name']}{ext}`" for c in source_classes
            ) if source_classes else f"`{target_name}{ext}`"
            target_cell = (f"`lwc/{target_name}`" if is_lwc
                           else f"`{target_name}{_w['target_ext']}`")
            conf = confidence.get(target_name, {})
            conf_cell = f"{conf.get('label', 'Medium')} ({conf.get('score', '—')})" if conf else "—"
            sections.append(
                f"| {source_names} | {layer} | {target_cell} | {pattern} | {conf_cell} |"
            )
    else:
        sections.append("| _(No classes were translated in this run)_ | — | — | — | — |")

    sections.append("")

    # ── Section 1b: Completeness Ledger ──
    if ledger:
        counts = {}
        for r in ledger:
            counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
        summary = ", ".join(f"**{v}** {k}" for k, v in counts.items())
        sections.extend([
            "## 1b. Completeness Ledger",
            "",
            "Every ingested source class is accounted for below — the guarantee that no "
            "business logic was silently dropped. `flagged` items are converted in full "
            "**and** carry a native-product review suggestion; `skipped` items had no "
            "business logic to preserve (with a reason).",
            "",
            f"> {summary}.",
            "",
        ])
        if any(r["outcome"] == "unaccounted" for r in ledger):
            sections.extend([
                "> ⚠️ **Some inputs are unaccounted for — investigate before relying on this run.**",
                "",
            ])
        manual_rows = [r for r in ledger if r["outcome"] == "manual"]
        if manual_rows:
            # The reason comes from the ledger, not from an assumption about what
            # `manual` means. It used to say every one was a business process whose
            # orchestration was not carried across, and point at `BUSINESS_PROCESSES.md`
            # — a document an Adobe Commerce run does not produce, about a construct
            # Magento does not have. There is more than one way to be read and not
            # converted, and the row already records which. [1.39]
            reasons = []
            for r in manual_rows:
                note = (r.get("note") or "").strip()
                if note and note not in reasons:
                    reasons.append(note)
            sections.append(
                f"> ⚠️ **`manual` means we read it and did not convert it.** "
                f"{len(manual_rows)} item(s), for these reasons:")
            sections.append("")
            sections += [f"> - {r}" for r in reasons[:6]] or [
                "> - no reason was recorded, which is itself worth investigating"]
            sections.append("")
        if any(r["outcome"] == "overwritten" for r in ledger):
            sections.extend([
                "> 🚨 **`overwritten` means two artifacts wrote the same file and only one "
                "survived.** The class is listed as reaching an artifact because it did — "
                "the loss happened at the write, so treat its logic as missing until you "
                "have checked the generated file.",
                "",
            ])
        sections.extend([
            "| Source Class | Layer | Outcome | Target | Note |",
            "|---|---|---|---|---|",
        ])
        for r in ledger:
            sections.append(
                f"| `{r['source']}` | {r['layer']} | {r['outcome']} | {r['target']} | {r['note'] or '—'} |")
        sections.append("")

    # ── Section 2: Validation Results ──
    sections.extend([
        "## 2. Static Code Validation Results (Tier-1)",
        "",
        f"All generated {_w['target_lang']} classes and test suites were subjected to "
        f"offline checks for {_w['limits']} and structural patterns.",
        "",
        "| Target Artifact Name | Validation Status | Issues Identified |",
        "|---|---|---|",
    ])

    total_passed = 0
    total_failed = 0
    for filename, issues in sorted(validation_results.items()):
        status = "PASSED ✅"
        issue_desc = "None"
        if issues:
            errs = [i for i in issues if i["severity"] == "ERROR"]
            warnings = [i for i in issues if i["severity"] == "WARNING"]

            summary_parts = []
            if errs:
                status = "FAILED ❌"
                total_failed += 1
                summary_parts.append(f"{len(errs)} Errors")
            else:
                total_passed += 1
            if warnings:
                summary_parts.append(f"{len(warnings)} Warnings")

            issue_desc = ", ".join(summary_parts) + ": " + "; ".join(
                f"[{i['rule']}] {i['message']}" for i in issues
            )
        else:
            total_passed += 1

        sections.append(f"| `{filename}` | {status} | {issue_desc} |")

    total_files = total_passed + total_failed
    sections.extend([
        "",
        f"> **Summary**: {total_passed}/{total_files} files passed validation"
        + (f", {total_failed} failed" if total_failed else "")
        + ".",
        "",
    ])

    # ── Section 2b: Deploy Verification ──
    if verify_result is not None:
        sections.extend([f"## 2b. Deploy Verification ({_w['cli']})", ""])
        if not verify_result.get("available"):
            sections.append(f"_{_w['cli']} not available — deploy verification "
                            "skipped._")
        elif not verify_result.get("ran"):
            sections.append(f"_Not run: {verify_result.get('message', 'no org available')}_")
        else:
            status = "✅ COMPILED" if verify_result.get("success") else "❌ FAILED"
            sections.append(f"**Dry-run deploy status**: {status}")
            if verify_result.get("coverage") is not None:
                cov = verify_result["coverage"]
                flag = "" if cov >= 75 else "  ⚠️ _below Salesforce's 75% deploy threshold_"
                sections.append(f"**Apex code coverage**: {cov}%{flag}")

            healing = verify_result.get("healing", {}) or {}
            rounds = healing.get("rounds", [])
            healed = healing.get("healed_files", [])
            healed_meta = healing.get("healed_metadata", [])
            strengthened = healing.get("coverage_strengthened", [])
            if rounds:
                verb = "green after" if verify_result.get("success") else "still failing after"
                sections.append(f"**Self-healing**: {verb} {len(rounds)} heal round(s), driven by real "
                                "deploy feedback:")
                if healed:
                    sections.append(f"- Apex repaired from compiler errors: "
                                    + ", ".join(f"`{f}`" for f in healed))
                if healed_meta:
                    sections.append(f"- SObject metadata added (source-evidenced): "
                                    + ", ".join(f"`{m}`" for m in healed_meta))
                if strengthened:
                    sections.append(f"- Tests strengthened for coverage: "
                                    + ", ".join(f"`{f}`" for f in strengthened))
                if not (healed or healed_meta or strengthened):
                    sections.append("- (no automated change produced a fix)")

            errs = verify_result.get("errors", [])
            if errs:
                sections.append("")
                sections.append("| File | Line | Problem |")
                sections.append("|---|---|---|")
                for e in errs[:50]:
                    sections.append(f"| {e.get('file','')} | {e.get('line','')} | {e.get('problem','')} |")
        sections.append("")

    # ── Section 2c: Migration Confidence ──
    if confidence:
        sections.extend([
            "## 2c. Migration Confidence",
            "",
            "Per-artifact confidence, scored from evidence — offline governor/schema "
            "validation, real org-deploy result, and any auto-healing required. "
            "Unverified output (no org deploy) is capped; a clean org deploy is the "
            "strongest signal.",
            "",
            f"| Target {_w['target_lang']} Artifact | Confidence | Score | Basis |",
            "|---|---|---|---|",
        ])
        for name, c in sorted(confidence.items()):
            sections.append(f"| `{name}{_w['target_ext']}` | {c['label']} | "
                            f"{c['score']}/100 | {c['basis']} |")
        sections.append("")

    # ── Section 2d: Schema Reconciliation ──
    if reconciliation and (reconciliation.get("added_fields") or reconciliation.get("added_objects")
                           or reconciliation.get("flagged")):
        sections.extend([
            "## 2d. Schema Reconciliation",
            "",
            "Unknown-field/object references were auto-resolved using evidence from "
            "the Hybris source: names the source actually uses (but `items.xml` never "
            "declared) were **added to the schema and emitted as SObject metadata**; "
            "references with no source evidence are **flagged** as likely hallucinations "
            "for review.",
            "",
        ])
        added = reconciliation.get("added_objects", []) + [
            {"object": f["object"], "reason": f"field `{f['field']}` — {f['reason']}"}
            for f in reconciliation.get("added_fields", [])]
        if added:
            sections.append("**Auto-added (evidenced in source):**")
            sections.append("")
            for a in reconciliation.get("added_objects", []):
                sections.append(f"- Object `{a['object']}` — {a['reason']}")
            for f in reconciliation.get("added_fields", []):
                sections.append(f"- Field `{f['object']}.{f['field']}` ({f['type']}) — {f['reason']}")
            sections.append("")
        if reconciliation.get("flagged"):
            sections.append("**Flagged for review (no source evidence):**")
            sections.append("")
            for fl in reconciliation["flagged"]:
                where = f"`{fl['object']}.{fl['field']}`" if fl.get("object") and fl.get("field") \
                    else f"`{fl.get('field') or fl.get('object')}`"
                sections.append(f"- {where} [{fl['rule']}] — {fl['reason']}")
            sections.append("")

    # ── Section 2e: Behavioral Parity ──
    if parity and parity.get("overall"):
        o = parity["overall"]
        sections.extend([
            "## 2e. Behavioral Parity",
            "",
            "How well the generated `@isTest` classes assert the **business rules** "
            "comprehended from the Hybris source — a proxy for behavioral equivalence "
            "(full dual-execution against a live Hybris instance is a later phase). "
            "See `PARITY.md` for the per-rule checklist.",
            "",
        ])
        if o.get("score") is not None:
            sections.append(f"- **Rule-assertion parity**: {o['score']}% "
                            f"({o['rules_covered']}/{o['rules_total']} business rules asserted)")
        else:
            sections.append("- **Rule-assertion parity**: n/a (no business rules were comprehended)")
        sections.append(f"- **Targets with assertion-bearing tests**: "
                        f"{o.get('targets_with_tests', 0)}/{o.get('targets_total', 0)}")
        strengthened = parity.get("strengthened")
        if strengthened and strengthened.get("rules_closed"):
            sections.append(f"- **Parity strengthening**: added assertions for "
                            f"{strengthened['rules_closed']} previously-unchecked rule(s) across "
                            f"{len(strengthened['targets_improved'])} class(es)")
        sections.append("")

    # ── Section 3: Token Usage ──
    providers = token_accounting.get("providers", {})
    provider_str = ", ".join(f"{k} ({v})" for k, v in providers.items()) or "n/a"
    is_mock = set(providers.keys()) == {"mock"}
    sections.extend([
        "## 3. Resource Cost & Token Usage",
        "",
        "The following execution statistics detail the cost of running the automated pipeline:",
        "",
        f"- **Provider(s)**: {provider_str}"
        + ("  ⚠️ _mock provider — output is a deterministic stub, not a real translation_" if is_mock else ""),
        f"- **Total LLM API Requests**: {token_accounting.get('requests', 0)}",
        f"- **Prompt Tokens Consumed**: {token_accounting.get('prompt_tokens', 0)}",
        f"- **Completion Tokens Generated**: {token_accounting.get('completion_tokens', 0)}",
        f"- **Cache Read / Write Tokens**: {token_accounting.get('cache_read_tokens', 0)} / {token_accounting.get('cache_write_tokens', 0)}",
        f"- **Classes Translated**: {len(generated_results)}",
        "",
    ])

    # ── Section 4: Mapping Decisions ──
    sections.extend([
        "## 4. Mapping Decisions Summary",
        "",
    ])

    if generated_results:
        for i, gen in enumerate(generated_results, 1):
            target_name = gen.get("target_name", "Unknown")
            notes = gen.get("mapping_notes", "").strip()
            if notes:
                sections.append(f"{i}. **{target_name}**: {notes}")
            else:
                layer = gen.get("layer", "Utility")
                # `_pattern_for` has existed for both platforms since the second
                # pipeline landed, and this one line never called it — so an
                # Adobe→Hybris feasibility report said its DAO became an "Apex Selector
                # Pattern" and its controller an "Apex REST Resource (@RestResource)".
                # The table was made pipeline-aware and one of its readers was
                # missed. [1.63]
                sections.append(
                    f"{i}. **{target_name}**: Translated from {layer} layer to "
                    f"{_w.get('target_lang', 'Apex')} {_pattern_for(layer, _w)}."
                )
    else:
        sections.append("_(No mapping decisions recorded)_")

    sections.append("")

    # ── Section 5: Skipped Domains ──
    if skipped_domains:
        sections.extend([
            "## 5. Skipped Domains",
            "",
            "The following domains were not translated due to errors (e.g. API credit exhaustion):",
            "",
        ])
        for domain in skipped_domains:
            sections.append(f"- `{domain}`")
        sections.append("")

    # ── Section 6: Manual Checklist ──
    sections.extend([
        "## 6. Manual Equivalence Checklist",
        "",
        "Developers performing final human inspection should verify:",
        "",
        *_review_checklist(_w),
        "- [ ] **Serialization**: Verify REST endpoint JSON payloads match the expected conventions of legacy consumer systems.",
        "- [ ] **Transaction Boundary**: Implement unit-of-work patterns where DML operations span multiple records.",
        "- [ ] **Test Coverage**: Run org-based code coverage reports to verify actual logic coverage.",
        "",
        "## 7. Limitations & Risks",
        "",
    ])

    verified_live = bool(verify_result and verify_result.get("ran"))
    if verified_live:
        sections.append(
            f"- **Deployment Verification**: Output was checked by {_w['target']}'s own "
            "tooling; failures were fed back into a self-healing repair loop until it "
            "passed (or the repair budget was exhausted — see §2b).")
    else:
        sections.append(
            "- **Deployment Automation**: No org deploy ran this iteration; offline static "
            "analysis is a proxy, not a substitute for real execution. Enable `verify.deploy` "
            "(or pass `--verify`) with an authorised org to activate deploy verification + "
            "self-healing.")
    sections.extend([
        "- **Validation Scope**: Offline validation checks syntax structures but cannot confirm query performance, indexing, or field level security configuration.",
        f"- **Commerce Logic**: Complex commerce workflows (cart calculations, checkout, "
        f"promotions) may map better to a native {_w['target']} capability than to "
        f"custom {_w['target_lang']}.",
        "- **Test Coverage**: While tests are generated, verify actual logic coverage via org-based code coverage reports.",
    ])

    report_content = "\n".join(sections)
    report_file.write_text(report_content, encoding="utf-8")
    return str(report_file)
