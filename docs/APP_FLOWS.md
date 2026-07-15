# Application Flows

**Product:** SAP Hybris → Salesforce Apex Migrator
**Version:** 0.7.0
**Audience:** Anyone who wants to see exactly what happens, step by step

This document walks through every flow a user or the system goes through — from clicking a button to getting deployable Salesforce code. For the *why* behind these flows, see [TDD.md](TDD.md).

---

## 1. The primary flow — VS Code extension

This is the flow a user actually experiences.

```
 User                          Extension                        Python Engine
  │                                │                                  │
  │ 1. Right-click a Hybris        │                                  │
  │    folder → "H2A: Migrate      │                                  │
  │    to Apex"                    │                                  │
  ├───────────────────────────────▶│                                  │
  │                                │ 2. First run only: create a       │
  │                                │    Python venv, install deps      │
  │                                │                                  │
  │                                │ 3. Read settings: provider,        │
  │                                │    API key, engine (agentic/      │
  │                                │    linear), incremental mode       │
  │                                │                                  │
  │                                │ 4. Spawn:                          │
  │                                │    python -m src.main              │
  │                                │      agent-migrate                 │
  │                                │      --input <folder>              │
  │                                │      --output salesforce_<folder>  │
  ├────────────────────────────────┼─────────────────────────────────▶│
  │                                │                                  │ 5. Run the full
  │                                │◀──── progress notifications ──────┤    pipeline (§2 or §3)
  │  6. See progress in the         │                                  │
  │     dashboard / notification    │                                  │
  │                                │◀──── done: exit code + output ────┤
  │  7. Open salesforce_<folder>/   │                                  │
  │     — deployable SFDX project   │                                  │
  │     + reports                   │                                  │
```

**Settings that shape this flow** (VS Code → Settings → H2A Migrator): `provider` (anthropic/openrouter/mock), the matching API key, `engine` (agentic/linear), `incrementalMode`, `customModel`.

## 2. The linear pipeline flow (`repo-migrate`)

```
Input folder
   │
   ▼
[1] Crawl & schedule domains  ──▶  [2] Build call graph
   │
   ▼
[3] Ingest Java + items.xml
   │
   ▼
[4] Derive SObject schema
   │
   ▼
for each domain, in dependency order:
   │
   ├─▶ [5] Comprehend each class (LLM)
   │
   └─▶ [6] Generate Apex (LLM, grounded in schema + scoped signatures)
              │
              ▼
         [7] Validate → issues? → repair (LLM) → re-validate  (bounded retries)
   │
   ▼
[8] Reconcile schema gaps  →  emit Custom Object/Field metadata
   │
   ▼
[9] Translate ImpEx data  +  resolve cron triggers
   │
   ▼
[10] (optional) Deploy-verify + self-heal  →  parity scoring  →  write reports
   │
   ▼
Deployable SFDX project + FEASIBILITY_REPORT.md
```

## 3. The agentic flow (`agent-migrate`) — the richer path

```
Input folder
   │
   ▼
Ingest + derive schema           (same as linear, steps 1–4)
   │
   ▼
Comprehend every class (LLM, routed to the cheap model tier if configured)
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ PLANNER                                                           │
│  For each candidate target, decide:                               │
│    Apex   → build it                                              │
│    Native → recommend a Salesforce product instead (e.g. CPQ)     │
│    Skip   → don't migrate (dead code / framework glue)             │
│  Records the rationale for every decision.                         │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼  (only "Apex" targets continue)
for each target, in dependency order:
   │
   ├─▶ BUILDER: generate Apex + tests (grounded in schema + RAG + scoped deps)
   │        │
   │        ▼
   │    objective repair (governor/schema issues, bounded retries)
   │        │
   │        ▼
   ├─▶ CRITIC: adversarial review
   │        │  checks: behavior preservation · security (FLS/sharing) · fflib conformance
   │        │
   │        ├─ ERROR findings? ──▶ one bounded repair round ──▶ re-review
   │        │
   │        └─▶ accept  OR  mark "needs_review" + log an open question
   │
   ▼
Reconcile schema gaps  →  emit metadata  →  ImpEx data  →  cron triggers
   │
   ▼
Parity strengthening (add test assertions for any business rule not yet covered)
   │
   ▼
(optional) VERIFIER: deploy-verify + self-heal loop (see TDD.md §4)
   │
   ▼
Final validation + parity scoring
   │
   ▼
Write: FEASIBILITY_REPORT.md · MIGRATION_PLAN.md (plan + review + decision log)
       · PARITY.md · MAPPING.md · DATA_MIGRATION.md · CRON_JOBS.md
```

## 4. The self-healing deploy flow (detail)

Only runs when `--verify` is passed (or `verify.deploy: true`) **and** the Salesforce CLI + an authorized org are available.

```
sf project deploy start --dry-run
   │
   ├── compiled cleanly? ──yes──▶ run_tests enabled + coverage < 75%?
   │                                  │
   │                                  ├─ yes ──▶ strengthen tests for
   │                                  │           under-covered classes ──▶ redeploy
   │                                  └─ no  ──▶ DONE (green)
   │
   └── compile errors? ──yes──▶ for each error:
                                    │
                                    ├─ "missing field/object" AND evidenced
                                    │  in the Hybris source?
                                    │     ──▶ add to schema, re-emit metadata
                                    │
                                    └─ otherwise
                                         ──▶ send the real compiler error to
                                             the LLM repair loop, rewrite the class
                                    │
                                    ▼
                              redeploy, repeat (bounded by max_deploy_attempts)
```

## 5. What happens when things go wrong (degradation paths)

| Situation | What happens |
|---|---|
| No API key configured, provider = anthropic/openrouter | Clear error message naming the missing key and where to get one; nothing crashes |
| `--verify` passed but `sf` CLI not installed | Verification step reports "not available" and is skipped; the rest of the pipeline completes normally |
| `--verify` passed, `sf` installed, but no authorized org | Verification reports "no org — run `sf org login web`" and is skipped |
| LLM call fails mid-run (auth error, rate limit) | The current domain is marked skipped, remaining domains are skipped, but everything generated so far is still written to disk with a report explaining what was skipped |
| A provider returns malformed/non-string output | The pipeline coerces it to empty rather than crashing (hardened after a real production incident — see the CHANGELOG in `h2a-vscode-extension/README.md`) |
| A generated field references something not in the schema | Flagged by validation → reconciliation decides add-vs-flag based on real source evidence (§ schema grounding in TDD.md) |

## 6. The command-line flows (equivalent, for CI/terminal use)

```bash
# Full linear migration
python -m src.main repo-migrate --input <hybris_dir> --output <out_dir> [--verify]

# Full agentic migration (Planner + Critic + RAG)
python -m src.main agent-migrate --input <hybris_dir> --output <out_dir> [--verify]

# Just the data (ImpEx → CSV + runbook), standalone
python -m src.main impex --input <hybris_dir> --output <out_dir>

# Just the scheduled jobs (cron triggers → Scheduled Apex runbook), standalone
python -m src.main cronjob --input <hybris_dir> --output <out_dir>

# Just the SObject metadata, standalone
python -m src.main metadata --input <hybris_dir>/items.xml --output <out_dir>

# Connectivity check
python -m src.main ping
```

See [HOW_TO_USE.md](HOW_TO_USE.md) for full setup instructions.
