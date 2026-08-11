# Application Flows

**Product:** SAP Hybris → Salesforce Apex Migrator
**Version:** 0.10.0
**Audience:** Anyone who wants to see exactly what happens, step by step

This document walks through every flow a user or the system goes through — from clicking a button to getting deployable Salesforce code. For the *why* behind these flows, see [TDD.md](TDD.md).

---

## 0. The primary flow — the web cockpit

The surface most users see, and the only one that shows the review gates as they happen.

```
Sign in  ──▶  session cookie; every run is owned by one account, and
   │          another tenant cannot open it (enforced in middleware)
   ▼
Point at a codebase — a server path, or upload a .zip
   │
   ▼
PREFLIGHT runs immediately, before a run object exists
   │
   ├─ not a Hybris project? ──▶ 422 with the reason. Nothing is created,
   │                            nothing is queued, nothing is charged.
   ▼
Run admitted to a FIFO queue (bounded concurrency)
   │  per-run provider / model / key / spend-cap pinned in ContextVars,
   │  so two tenants running at once cannot inherit each other's settings
   ▼
Engine streams events ──▶ cockpit updates live (stages, files, decisions)
   │
   ├──▶ GATE 1/2/3: the engine BLOCKS, the cockpit shows the review screen,
   │    the reviewer decides, and their identity is stamped SERVER-SIDE from
   │    the session (never from the request body) and recorded for sign-off
   ▼
Run completes ──▶ durable SQLite history; reopen it later exactly as it was
   │
   ▼
Records › Reports › ⬇ Download SFDX package
```

**If the browser refreshes or disconnects,** the run continues — it lives in the server
process, not the page. Reconnecting re-attaches to the same event stream.

**If the provider rejects the key,** the run stops with a clear message rather than
degrading every stage to its deterministic fallback and reporting success.

## 1. The VS Code extension flow

This is the flow an in-IDE user experiences.

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
PREFLIGHT — is this a SAP Commerce project at all?   (no LLM, no cost)
   │        rejects a wrong upload before a run exists; reports any
   │        credentials found in the archive
   ▼
Ingest + derive schema           (same as linear, steps 1–4)
   │
   ▼
Radar · Forecast · Org fit       (no LLM — hazards, cost range, org collisions)
   │
   ▼
╔═══ GATE 1 · Discovery ═══╗  reviewer approves what was found
   │
   ▼
Comprehend every class (LLM, routed to the cheap model tier if configured)
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ PLANNER — policy: CONVERT EVERYTHING                              │
│  For each candidate target, decide:                               │
│    Convert → build it. If a native Salesforce product would be a  │
│              better home (e.g. CPQ), the logic is STILL converted │
│              in full and `native_recommendation` flags it for      │
│              human review — never a reason to drop code.          │
│    Skip    → provably dead code / framework glue / pure DTO only,  │
│              and it must carry a reason.                          │
│  Records the rationale for every decision.                         │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
╔═══ GATE 2 · Plan ═══╗  reviewer can flip any target Convert↔Skip
   │
   ▼  (every "Convert" target continues)
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
╔═══ GATE 3 · Build ═══╗  reviewer approves, or sends artifacts back
   │                      to the Builder with feedback (bounded rounds)
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
ASSURANCE — all deterministic, no LLM calls:
   rule ledger · characterization replay · provenance · alignment
   · triage · blast radius · replay record · sign-off contract
   │
   ▼
Write: SIGN_OFF.md · FEASIBILITY_REPORT.md · MIGRATION_PLAN.md · TRIAGE.md
       · BUSINESS_RULES.md · ALIGNMENT.md · PROVENANCE.md · CHARACTERIZATION.md
       · ANTI_PATTERNS.md · ORG_FIT.md · FORECAST.md · DECISION_RECORD.md
       · PARITY.md · MAPPING.md · DATA_MIGRATION.md · CRON_JOBS.md
```

**A snapshot is taken before each gate**, so a reviewer can return to the state they were
looking at when they decided, and diff two plans. See `checkpoints` in
[HOW_TO_USE.md](HOW_TO_USE.md).

**Gates are optional.** With no reviewer attached (CLI, extension, CI) the run proceeds
unattended — and the sign-off contract records it as *unreviewed* rather than approved.

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
