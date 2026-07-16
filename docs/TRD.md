# Technical Requirements Document (TRD)

**Product:** SAP Hybris → Salesforce Apex Migrator
**Version:** 0.8.0
**Audience:** Engineers implementing, extending, or operating the system

This document lists *what the system must do and support* (requirements). For *how* it does it, see [TDD.md](TDD.md).

---

## 1. Functional requirements

| ID | Requirement | Status |
|---|---|---|
| FR-1 | Parse Java source files (Hybris DAO/Service/Facade/Controller/Job/Model classes) into a structured representation | ✅ Done |
| FR-2 | Parse `items.xml` (item types, attributes, enum types, relations, modifiers) into a Salesforce SObject schema | ✅ Done |
| FR-3 | Translate each source class into governor-limit-safe Apex following fflib Enterprise Patterns (Selector / Service / Controller / Schedulable) | ✅ Done |
| FR-4 | Generate a matching `@isTest` class for every main class, with real assertions (not just line coverage) | ✅ Done |
| FR-5 | Validate generated Apex against governor-limit rules (no SOQL/DML in loops, `with sharing`, no leaked Java syntax) | ✅ Done |
| FR-6 | Ground every SOQL/field reference against the real derived schema; flag anything that doesn't exist | ✅ Done |
| FR-7 | Auto-repair validation failures by feeding the errors back to the LLM (bounded retry) | ✅ Done |
| FR-8 | Reconcile schema gaps: if generated code references a field that's genuinely used in the Java source but undeclared in `items.xml`, add it (with an inferred type); if there's no evidence, flag it instead of guessing | ✅ Done |
| FR-9 | Emit deployable Salesforce metadata (Custom Objects, Custom Fields, picklists, lookups) derived from the schema | ✅ Done |
| FR-10 | Translate `.impex` data files into per-object CSVs + an idempotent upsert runbook, with External IDs derived from `[unique=true]` | ✅ Done |
| FR-11 | Detect Hybris scheduled jobs (`extends AbstractJobPerformable`) and translate them to `Schedulable` Apex; resolve their cron triggers (Spring XML or ImpEx) into a scheduling runbook | ✅ Done |
| FR-12 | Optionally dry-run deploy the output to a real Salesforce org and report real compiler errors + code coverage | ✅ Done |
| FR-13 | Self-heal deploy failures: missing-field errors patch the schema; compile errors are repaired via the LLM; low coverage triggers auto-generated additional test methods | ✅ Done |
| FR-14 | Produce a migration *plan* before generating code: for each source class, decide whether it should become custom Apex, be replaced by a native Salesforce feature, or be skipped — with a stated rationale | ✅ Done |
| FR-15 | Adversarially review every generated artifact for behavior preservation, security (FLS/sharing), and fflib conformance before accepting it | ✅ Done |
| FR-16 | Score "behavioral parity" — how many of the comprehended business rules are actually asserted by the generated tests — and optionally close the gap by strengthening tests | ✅ Done |
| FR-17 | Support three interchangeable LLM providers (Anthropic, OpenRouter, keyless mock) with identical prompts/pipeline — only the model changes | ✅ Done |
| FR-18 | Route different pipeline stages to different model tiers (cheap vs. frontier) to control cost | ✅ Done |
| FR-19 | Ground generation/review in a bundled Salesforce/Apex/fflib knowledge base via lightweight retrieval | ✅ Done (scaffold; production-scale corpus is future work) |
| FR-20 | Provide a VS Code extension that runs the full pipeline from a right-click on a folder | ✅ Done |
| FR-21 | Provide a CLI for the same operations, for CI/CD or terminal use | ✅ Done |
| FR-22 | Incrementally re-run: skip re-translating domains whose source hasn't changed since the last run | ✅ Done |
| FR-23 | Introspect a target org's existing metadata (to reuse objects instead of duplicating them) | ⏳ Planned (Phase 3 — needs live org credentials) |
| FR-24 | Translate Hybris business processes to Salesforce Flow/Approval Processes | ⏳ Planned (Phase 2) |
| FR-25 | Translate storefront REST APIs (OCC) to Apex REST / Experience Cloud | ⏳ Planned (Phase 2) |

## 2. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | **Determinism where it matters.** Parsing, schema derivation, validation, data/metadata emission are 100% deterministic (no LLM) so they are unit-testable and reproducible. LLM steps are isolated to comprehension, generation, review, and repair. |
| NFR-2 | **Graceful degradation.** Every external dependency (Salesforce CLI, a live org, an LLM provider) is optional at the code level — its absence produces a clear message, never a crash. |
| NFR-3 | **No silent data loss.** Auto-added schema fields and every AI decision are logged (`MIGRATION_PLAN.md`, `FEASIBILITY_REPORT.md`) — nothing is added or changed invisibly. |
| NFR-4 | **Cost visibility.** Every LLM call is counted (tokens, cache hits, provider) and surfaced in the feasibility report. |
| NFR-5 | **Reasonable latency.** A small (2–5 class) migration completes in single-digit minutes on the agentic path with a frontier model; the mock path completes in seconds. |
| NFR-6 | **Testability.** The full pipeline must be runnable end-to-end with zero external cost or network access (`mock` provider), for CI and local development. |
| NFR-7 | **Auditability.** Every agent decision (Planner's routing, Critic's findings, reconciliation additions) is recorded in a human-readable decision log. |
| NFR-8 | **Extensibility.** Adding a new source-code surface (e.g. business processes) should not require changing the core orchestration — it should plug in as a new deterministic parser + (optionally) a new generation "layer," following the pattern established by ImpEx and Cronjobs. |

## 3. Security & data-handling requirements

| ID | Requirement |
|---|---|
| SEC-1 | API keys are never written to source control; `.env` is gitignored and excluded from the packaged extension (`.vscodeignore`). |
| SEC-2 | The packaged VS Code extension is audited before every release to confirm no secret, cache, or virtualenv content is bundled. |
| SEC-3 | Source code sent to an LLM provider is only sent to the provider the user explicitly configured. A custom gateway (`ANTHROPIC_BASE_URL`) is supported but flagged with an explicit warning that a third-party gateway sees all transmitted content — the user must opt in per endpoint. |
| SEC-4 | The `mock` provider exists specifically so the pipeline can be exercised with **zero code leaving the machine**, for sensitive-codebase testing. |
| SEC-5 | Generated Apex enforces field-level security (`Security.stripInaccessible`) and object sharing (`with sharing`) by default, per the fflib patterns the system is instructed to follow. |
| SEC-6 | No destructive operations are performed automatically — deploys are dry-run (`--dry-run` / `--verify`) unless the user separately runs a real deploy themselves. |

## 4. Environment & dependency requirements

| Component | Requirement |
|---|---|
| **Python** | 3.10+ (engine and CLI) |
| **Python packages** | `anthropic`, `openai` (for OpenRouter), `javalang` (Java parsing), `pyyaml`, `pydantic`, `rich`, `pytest` — see `h2a-mvp/requirements.txt` |
| **Node / VS Code** | Node.js + `@vscode/vsce` to build the extension; VS Code 1.75+ to run it |
| **Salesforce CLI (`sf`)** | Optional — only required for `--verify` (real deploy verification) |
| **A Salesforce org** | Optional — a scratch org or sandbox for deploy verification; not required for generation |
| **LLM API key** | Required only for the `anthropic` or `openrouter` provider; not required for `mock` |

## 5. Supported inputs

| Input | Parsed by |
|---|---|
| `*.java` (Hybris DAO/Service/Facade/Controller/Job/Model classes) | `src/ingest.py` (via `javalang` AST) |
| `items.xml` / `*-items.xml` (item types, enum types, relations, attribute modifiers) | `src/ingest.py` |
| `*.impex` (data + cron trigger definitions) | `src/impex.py`, `src/cronjob.py` |
| `*.xml` Spring bean config (cron trigger wiring) | `src/cronjob.py` |

## 6. Supported outputs

A standard **Salesforce DX (SFDX) project**:

```
salesforce_<project>/
├── sfdx-project.json, config/project-scratch-def.json
├── force-app/main/default/
│   ├── classes/         (Apex .cls + -meta.xml + matching Test.cls)
│   └── objects/         (Custom Objects, Custom Fields, picklists, lookups)
├── data/                 (per-object CSVs, from ImpEx)
├── DATA_MIGRATION.md      (data upsert runbook)
├── CRON_JOBS.md + schedule.apex   (scheduled-job runbook)
├── MAPPING.md             (field/layer mapping reference)
├── MIGRATION_PLAN.md      (agentic run only: plan + review + decisions log)
├── PARITY.md              (behavioral parity checklist)
├── FEASIBILITY_REPORT.md  (validation, confidence, deploy status, cost)
└── .call_graph.json       (for the dashboard visualizer)
```

## 7. Interfaces

| Interface | Entry point |
|---|---|
| VS Code command | Right-click a folder → **H2A: Migrate to Apex** |
| CLI | `python -m src.main {repo-migrate, agent-migrate, impex, cronjob, metadata, report, ping}` |
| Configuration | `h2a-mvp/config.yaml` (provider, model, effort, verify, agentic, parity settings) + `.env` (API keys) + VS Code settings (`h2aMigrator.*`) |

## 8. Constraints & assumptions

- The system assumes Hybris source follows conventional naming (`XxxDao`, `DefaultXxxService`, `XxxController`, `XxxFacade`) or Spring annotations / superclass markers (`extends AbstractJobPerformable`) to infer layers. Unconventional naming falls back to a generic "Utility" classification.
- Cron-expression translation assumes both Hybris and Salesforce speak Quartz-compatible cron syntax (true in practice), so it validates rather than rewrites.
- Real-org deploy verification requires network access to Salesforce and a pre-authorized org; it is entirely optional and the rest of the pipeline works without it.
