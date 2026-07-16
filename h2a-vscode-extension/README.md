# SAP Hybris → Salesforce Apex Migrator — VS Code Extension

[![Version](https://img.shields.io/badge/version-0.8.0-blue.svg)](https://marketplace.visualstudio.com/items?itemName=iamvikaas.h2a-vscode-extension)
[![Publisher](https://img.shields.io/badge/publisher-iamvikaas-green.svg)](https://marketplace.visualstudio.com/publishers/iamvikaas)

Migrate a complete SAP Hybris (Java/Spring) codebase into deployment-ready
Salesforce Apex classes, `@isTest` suites, SObject metadata, data, and scheduled
jobs — from a single right-click. Powered by an AI agent team (Planner, Builder,
Critic, Verifier) with **Anthropic Claude**.

> **Full documentation** — product requirements, architecture, app flows, a
> plain-English guide, a stakeholder demo script, and the roadmap — lives in
> [`../docs/`](../docs/README.md).

---

## Install the packaged extension (.vsix)

The repository holds the extension **source**; the installable `.vsix` is a build
artifact and is not committed (build output never is). GitHub builds it for you:

- **Latest build** — open the repo's **Actions → "Build VSIX"** run and download the
  `h2a-vscode-extension-vsix` artifact.
- **Tagged release** — push a version tag and the `.vsix` is attached to the matching
  [GitHub Release](https://github.com/Vikaschd04/SAP_Salesforce_Migrator/releases):
  ```bash
  git tag v0.8.0 && git push origin v0.8.0
  ```

Then install it:

```bash
code --install-extension h2a-vscode-extension-0.8.0.vsix
# …or in VS Code: Extensions view → “…” menu → Install from VSIX…
```

**Build it locally instead** (produces the same `.vsix`):

```bash
cd h2a-vscode-extension
npm install
npx @vscode/vsce package      # → h2a-vscode-extension-0.8.0.vsix
```

To publish to the Marketplace, run your own `npx @vscode/vsce publish`.

---

## What it does

Point it at a folder of Hybris Java + `items.xml` and it produces a standard
Salesforce DX project: fflib-style Selectors/Services/Controllers/Scheduled Apex,
matching test classes, custom objects/fields (incl. picklists), migrated data,
and scheduled-job runbooks — grounded in your actual data model, adversarially
reviewed, and checked against Salesforce governor limits.

## Features

- **One-click migration** — right-click any Hybris folder → **H2A: Migrate to Apex**.
- **Agentic engine (default)** — a Planner decides each target's home (custom
  Apex, a native Salesforce feature like CPQ, or skip); a Critic adversarially
  reviews every artifact for behavior/security/governor safety before accepting
  it; a Verifier deploys and self-heals against a real org. Switch to the
  simpler **linear** engine anytime via the **Engine** setting.
- **Self-contained** — the entire Python engine is bundled; on first run it
  auto-creates a virtual environment and installs dependencies. No manual setup.
- **Choose your provider** (same pipeline, prompts, and validation — only the LLM
  changes): **Anthropic Claude** (best quality), **OpenRouter** (free/cheap models
  for development & testing), or **Mock** (keyless dry run). Prompt caching +
  structured output on the Claude path for reliable parsing.
- **Schema grounding + reconciliation** — builds your SObject/field catalog from
  `items.xml`; SOQL is validated against it; fields genuinely used in your source
  but undeclared in `items.xml` are added automatically (evidence-based), not guessed.
- **fflib Enterprise Patterns** — Selectors own SOQL (`Security.stripInaccessible`,
  bulk-safe), Services are stateless and bulkified, Controllers are thin
  `@RestResource` classes, scheduled jobs implement `Schedulable`.
- **Data & scheduled-job migration** — `.impex` → CSVs + an idempotent upsert
  runbook; Hybris cron triggers → a `System.schedule(...)` runbook.
- **Validate, auto-repair, and self-heal** — governor-limit lints + schema checks
  offline; real deploy errors, missing fields, and low coverage are healed
  automatically against a live org (optional, needs the `sf` CLI + an org).
- **Keyless dry-run** — set Provider to `mock` to exercise the full pipeline
  without an API key (produces clearly-labelled stub Apex).
- **Incremental** — MD5 delta tracking skips unchanged domains on re-runs.
- **Interactive dashboard** — metrics, a topological stepper, an interactive
  call-graph canvas (Hybris ↔ Salesforce views), and colorized logs.

## Usage

1. Pick a **Provider** and set its key in **Settings → H2A Migrator**:
   - `anthropic` → **Anthropic Api Key** (`sk-ant-...`) — best quality.
   - `openrouter` → **Openrouter Api Key** (`sk-or-...`) — free/cheap models for
     dev/testing (set **Custom Model** to a slug from openrouter.ai/models).
   - `mock` → no key — keyless dry run to test the pipeline.
2. Right-click a Hybris folder in the Explorer → **H2A: Migrate to Apex**.
3. First run only: wait while the Python environment is provisioned.
4. Review the **H2A Converter Dashboard**, then find the output in a new
   `salesforce_<FolderName>/` folder next to your source.

## Settings

| Setting | Default | Description |
|---|---|---|
| `h2aMigrator.engine` | `agentic` | `agentic` (Planner + Builder + Critic + Verifier + RAG) · `linear` (simpler, fewer LLM calls). |
| `h2aMigrator.provider` | `anthropic` | `anthropic` (Claude) · `openrouter` (free/cheap) · `mock` (keyless). |
| `h2aMigrator.anthropicApiKey` | `""` | Anthropic key (`sk-ant-...`), used when provider = anthropic. |
| `h2aMigrator.openrouterApiKey` | `""` | OpenRouter key (`sk-or-...`), used when provider = openrouter. |
| `h2aMigrator.customModel` | `""` | Override the model for the active provider. |
| `h2aMigrator.incrementalMode` | `true` | Skip unchanged domains on re-runs. |
| `h2aMigrator.verifyDeploy` | `false` | Verify by deploying to Salesforce: after generating, run a **validate-only** (check-only) deploy against your default org and self-heal real compiler/coverage errors. Requires the Salesforce CLI (`sf`) and a default org (`sf org login web` → `sf config set target-org <alias>`). Nothing is written to the org. |
| `h2aMigrator.pythonPath` | `""` | Custom Python executable (else a bundled `.venv` is used). |
| `h2aMigrator.pipelinePath` | `""` | Custom path to the h2a-mvp pipeline directory. |

> **Security:** your key is passed to the local Python process as an environment
> variable for the run; it is not written to disk or transmitted anywhere except
> Anthropic's API.

## Output

```
salesforce_<project>/
├── sfdx-project.json
├── config/project-scratch-def.json
├── force-app/main/default/
│   ├── classes/<Name>.cls (+ -meta.xml, + <Name>Test.cls)
│   └── objects/<Object>__c/ (object + fields/*.field-meta.xml, incl. picklists)
├── data/<Object>__c.csv           ← from .impex
├── DATA_MIGRATION.md               ← data upsert runbook
├── CRON_JOBS.md + schedule.apex    ← scheduled-job runbook
├── MIGRATION_PLAN.md               ← agentic engine: plan, Critic review, decision log
├── PARITY.md                       ← behavioral parity checklist
├── .call_graph.json
├── MAPPING.md
└── FEASIBILITY_REPORT.md   ← provider, validation results, confidence, deploy verification
```

Deploy with `sf project deploy start --source-dir force-app`.

## Requirements

- Python 3.10+ on PATH (the extension provisions its own venv and installs the
  `anthropic` SDK + `javalang` automatically).
- An Anthropic API key (real runs) — https://console.anthropic.com/
- *(optional)* Salesforce CLI (`sf`) + an authorised org for live deploy verification.

## Version history

| Version | Key changes |
|---|---|
| **0.8.0** | **Deploy verification from the extension: a new `verifyDeploy` setting runs a validate-only (check-only) deploy of the generated project against your default Salesforce org and self-heals real compiler/coverage errors before you review — the org is never modified. Requires the Salesforce CLI (`sf`) with a default org set. Adds a bundled, demo-ready Hybris "Order Management" sample (in the repo's `Testing/` folder) covering DAO/service/controller/job, `items.xml`, ImpEx and a cron trigger.** |
| 0.7.0 | **Cronjobs → Scheduled Apex (Phase 2): Hybris jobs (`extends AbstractJobPerformable`) are detected as a new "Job" layer and translated to `Schedulable` Apex through the same agentic pipeline; their Spring XML / ImpEx cron triggers are resolved and translated (Hybris and Salesforce both use Quartz cron, so it's a validated pass-through) into a `CRON_JOBS.md` runbook + ready-to-run `schedule.apex`. Default model confirmed at the latest/most capable — `claude-opus-4-8`.** |
| 0.6.3 | Codegen hardening (from a real end-to-end Claude run): fixed a double-prefix bug that produced `System.System.assertEquals`, and stopped truncated/JSON responses from ever being written to a `.cls`; raised the generation token budget so large fflib test classes aren't cut off.** |
| 0.6.2 | The right-click migration now runs the full **agentic** engine by default (Planner + Builder + Critic + Verifier + RAG grounding + ImpEx data + picklist metadata). New **Engine** setting (`agentic` / `linear`) to switch.** |
| 0.6.1 | Deeper `items.xml` metadata: Hybris enum types become Salesforce **picklist** fields (with the value set + default), and attribute modifiers map to real field constraints — `optional="false"` → **required**, `unique="true"` → **unique**, plus default values. Richer, deploy-ready SObject metadata.** |
| 0.6.0 | Phase 2 begins — data migration: Hybris `.impex` files are parsed and translated into per-object Salesforce CSVs plus a `DATA_MIGRATION.md` runbook with ready-to-run `sf data upsert` commands. `[unique=true]` attributes become **External IDs** (marked in the object metadata) so loads are idempotent upserts; simple references map to `Rel__r.Key__c` lookup columns. Runs inside `repo-migrate`/`agent-migrate`, or standalone via `impex`.** |
| 0.5.1 | RAG grounding (scaffold): the agentic Builder and Critic now retrieve relevant facts from a bundled Salesforce/Apex/fflib knowledge base and inject them into the prompt, so generation/review cite real governor limits and patterns instead of relying on memory. Dependency-free lexical (TF-IDF) retrieval; the interface is ready to swap in a full semantic corpus.** |
| 0.5.0 | Phase 1 — agentic core (opt-in `agent-migrate`): a Planner that decides each target's home (custom Apex vs native Salesforce like CPQ/Flow vs skip), a Critic that adversarially reviews each artifact for behavior/security/governor safety before accepting, a shared Blackboard with a full decisions log + `MIGRATION_PLAN.md`, and per-task model routing (cheap model for comprehension/planning, frontier for generation). The linear `repo-migrate` path is unchanged.** |
| 0.4.3 | Phase 0 hardening: self-healing now also fixes metadata (a "missing custom field/object" deploy error adds the source-evidenced field instead of rewriting Apex) and enforces coverage (strengthens tests until ≥75%); auto-added fields get their type inferred from the Java source instead of defaulting to Text.** |
| 0.4.2 | Phase 0 — verifiable correctness: self-healing deploy loop (real `sf` compiler errors fed back into the LLM repair loop until the metadata compiles); evidence-based schema reconciliation (auto-adds source-evidenced fields, flags likely hallucinations); emits deployable SObject metadata (objects + fields), not just Apex; per-artifact confidence scores; behavioral-parity harness + `PARITY.md`.** |
| 0.4.1 | Marketplace republish — packaging refresh, no functional changes since 0.4.0. |
| 0.4.0 | Selectable providers — Anthropic Claude (default), OpenRouter (free/cheap models), and keyless Mock; prompt caching + structured outputs on the Claude path; SObject-schema grounding; scoped dependency context; optional `sf` deploy verification; removed the old silent multi-model auto-fallback & hardcoded output fixtures. |
| 0.3.0 | Call-graph extraction, fflib patterns, interactive canvas visualizer |
| 0.2.0 | SFDX restructuring, dashboard |
| 0.1.x | Initial multi-domain topological translation + metadata compiler |

## Documentation

Full documentation — PRD, TRD, architecture (TDD), app flows, plain-English guide,
usage guide, stakeholder demo script, and roadmap — lives in [`../docs/`](../docs/README.md).
See also the pipeline [README](./h2a-mvp/README.md).
