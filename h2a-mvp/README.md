# h2a-mvp — Repository-Scale Hybris-to-Apex Migration Pipeline

An LLM-powered pipeline that translates complete SAP Hybris (Java/Spring) monolith
repositories into governor-limit-safe Salesforce Apex classes, `@isTest` suites,
SObject schema metadata, and a deployment-ready SFDX workspace.

**Engine version**: 0.10.0 | **License**: MIT

> Full documentation (PRD, TRD, architecture, app flows, plain-English guide,
> usage guide, demo script, roadmap) lives in [`../docs/`](../docs/README.md).

Two ways to run it: the deterministic **linear pipeline** (`repo-migrate`), and
the **agentic core** (`agent-migrate`) — a Planner + Builder + Critic + Verifier
team over a shared blackboard, with RAG grounding and model routing. Both share
the same underlying stages and produce the same output shape; see
[`../docs/TDD.md`](../docs/TDD.md) for the architecture.

---

## 1. Pipeline

1. **Crawl & schedule** — group classes into domains, detect cross-domain
   dependencies (whole-word, comment/string-stripped), topologically sort.
2. **Call graph** — emit `.call_graph.json` for the dashboard.
3. **Ingest** — parse Java via `javalang` AST; parse `items.xml` item types **and
   relations**.
4. **Schema** — derive the target SObject/field catalog from `items.xml`.
5. **Comprehend** — one structured-output call per class (role, queries, rules).
6. **Generate** — Claude translation with a **cached system prompt** (rules + type
   table + constraints + schema) and a per-class user prompt carrying only the
   **scoped** upstream signatures the class depends on. Returns structured JSON.
7. **Validate & repair** — governor-limit lints **+ schema field grounding** (flag
   SOQL/fields that don't exist); LLM repair loop grounded in the errors + schema.
8. **Reconcile + Metadata** — evidence-based schema gap-filling, then compile
   `items.xml` to custom objects, fields (incl. picklists from enum types), and
   lookups.
9. **Data + Jobs** — translate `.impex` to CSV + an upsert runbook; resolve
   Hybris cron triggers (Spring XML / ImpEx) to a Scheduled Apex runbook.
10. **Verify + Report** — optional real-org deploy + self-heal (metadata, Apex,
    and coverage healing); behavioral parity scoring; standard SFDX layout,
    `MAPPING.md`, and a feasibility report with provider/cache accounting.

The **agentic path** (`agent-migrate`) wraps steps 5–7 with a Planner (decides
Apex vs. a native Salesforce feature vs. skip) and a Critic (adversarial review
before accepting each artifact), and adds RAG grounding — see
[`../docs/TDD.md`](../docs/TDD.md) §3.

---

## 2. Key capabilities

- **Anthropic Claude** generation (`claude-opus-4-8` by default) with adaptive
  thinking + effort per stage.
- **Prompt caching**: the large stable prefix (rules, type table, constraints,
  schema) is cached, so every class in a repo reuses it at ~0.1x cost.
- **Structured outputs**: guaranteed-parseable JSON — no fragile `===MARKER===`
  scraping.
- **Schema grounding**: SOQL/field references are validated against the objects
  and fields actually derived from `items.xml`.
- **Scoped dependency context**: only signatures from a domain's transitive
  dependencies are injected (not every class generated so far).
- **Three interchangeable providers** (same prompts, schema, and validation —
  only the LLM changes): **`anthropic`** (Claude, best quality), **`openrouter`**
  (free/cheap models for dev/testing), **`mock`** (keyless deterministic stub for
  CI/dry-runs, clearly labelled in logs and the report).
- **Optional real verification + self-healing**: `--verify` dry-run deploys the
  output to a Salesforce org and reports compile errors + coverage; real
  errors are fed back into automatic metadata/Apex/coverage healing.
- **Agentic core** (`agent-migrate`): a Planner + Builder + Critic + Verifier team
  over a shared blackboard, with lexical RAG grounding and per-task model routing.
- **Data & scheduled-job migration**: `.impex` → CSV + upsert runbook; Hybris
  cronjobs → Scheduled Apex + a `System.schedule(...)` runbook.
- **Eval harness** (`eval/`): objective scorecard (validation pass-rate, schema
  violations, artifact coverage, optional compile + golden similarity).
- **Incremental delta tracking**: MD5 ledger skips unchanged domains.

---

## 3. Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Option A — real translation (needs a key):
cp .env.example .env       # add ANTHROPIC_API_KEY
python -m src.main repo-migrate --input <hybris_dir> --output <out_dir>

# Option B — keyless deterministic dry run (verifies the pipeline, stub Apex):
H2A_PROVIDER=mock python -m src.main repo-migrate --input <hybris_dir> --output <out_dir>

# Add a live compile check against an authorised org:
python -m src.main repo-migrate --input <hybris_dir> --output <out_dir> --verify
```

## 4. CLI

| Command | Purpose |
|---|---|
| `ping` | Test provider connectivity (prints provider + model). |
| `repo-migrate --input <dir> --output <dir> [--offline] [--verify]` | Full repo migration (linear pipeline). |
| `agent-migrate --input <dir> --output <dir> [--offline] [--verify]` | **Phase 1 agentic run**: Planner + Builder + Critic + Verifier over a shared blackboard; emits `MIGRATION_PLAN.md`. |
| `impex --input <dir> --output <dir>` | **Phase 2 data migration**: translate `.impex` → per-object CSVs + `DATA_MIGRATION.md` upsert runbook (also runs inside repo/agent migrate). |
| `cronjob --input <dir> --output <dir>` | **Phase 2 scheduled jobs**: resolve Hybris cron triggers (Spring XML / ImpEx) → `CRON_JOBS.md` + `schedule.apex` (also runs inside repo/agent migrate). |
| `metadata --input <dir> --output <dir>` | Compile `items.xml` to SObject metadata. |
| `report --output <dir>` | Regenerate the feasibility report from disk. |
| `python -m eval.run_eval --input <dir> [--provider mock] [--deploy]` | Quality scorecard. |

## 5. Configuration (`config.yaml`)

```yaml
provider: anthropic          # anthropic | openrouter | mock
model: claude-opus-4-8                       # used when provider=anthropic
openrouter:                                  # used when provider=openrouter
  base_url: https://openrouter.ai/api/v1
  model: qwen/qwen3-coder:free               # any model from openrouter.ai/models
effort:   {comprehend: low, generate: high}  # anthropic only
max_tokens: {comprehend: 800, generate: 4000}
max_repair_attempts: 2
verify: {deploy: false, run_tests: false, target_org: ""}
```

Keys: `ANTHROPIC_API_KEY` (anthropic) / `OPENROUTER_API_KEY` (openrouter), in the
environment or `.env`. Env overrides: `H2A_PROVIDER`, `H2A_CUSTOM_MODEL`,
`H2A_INCREMENTAL`.

```bash
# switch providers per run without editing config:
H2A_PROVIDER=openrouter H2A_CUSTOM_MODEL=qwen/qwen3-coder:free \
  python -m src.main repo-migrate --input <dir> --output <dir>
```

## 6. Output structure

```
salesforce_<project>/
├── sfdx-project.json
├── config/project-scratch-def.json
├── force-app/main/default/
│   ├── classes/<Name>.cls (+ -meta.xml, + <Name>Test.cls)
│   └── objects/<Object>__c/ (object + fields/*.field-meta.xml, incl. picklists)
├── data/<Object>__c.csv          (from .impex)
├── DATA_MIGRATION.md              (data upsert runbook)
├── CRON_JOBS.md + schedule.apex   (scheduled-job runbook)
├── MIGRATION_PLAN.md              (agentic runs: plan + review + decision log)
├── PARITY.md
├── .call_graph.json
├── MAPPING.md
└── FEASIBILITY_REPORT.md
```

## 7. Tests

```bash
python -m pytest tests/ -q     # 296 tests: ingest, schema grounding, mock provider,
                               # scoped signatures, agentic core, ImpEx, cronjobs,
                               # and full end-to-end mock migrations (linear + agentic)
```

## 8. Requires

- Python 3.10+ · `anthropic` SDK · `javalang` · `pyyaml` · `pydantic`
- (optional, for `--verify`) Salesforce CLI (`sf`) + an authorised org
