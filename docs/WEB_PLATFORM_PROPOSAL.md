# Proposal — H2A Web Platform (Phase 4)

**A hosted, visual, human-in-the-loop migration cockpit built on top of the existing engine.**

**Version:** 0.1 (proposal) · **Status:** ✅ **DELIVERED — kept as the design record** · **Date:** 2026-07-29

> **This proposal has been built.** The cockpit, the live agent dashboard, the three review
> gates, per-file review and rework, and the downloadable package all shipped in
> `h2a-web/`. It is kept because it records *why* the platform is shaped the way it is;
> for what exists today read [COCKPIT_GUIDE.md](COCKPIT_GUIDE.md) (every screen),
> [APP_FLOWS.md](APP_FLOWS.md) §0 (the flow) and [SETUP.md](SETUP.md) (running it).
> Anything below that reads as future tense is history, not a plan.

---

## 1. What was asked (from the stakeholder demo)

Move the migrator from a CLI / VS Code extension into a **web application** where a user can:

1. **Select a repository or upload a codebase** from their local system.
2. **Watch the whole process on a dashboard**, with **each agent's work shown at every step**:
   - **Planner** → shows the list of files that *will* be migrated (and what's skipped/flagged); user can inspect them.
   - **Builder** → shows each generated file; user can review it after generation.
   - **Critic** → shows the review findings; **user can give input / corrections if something's wrong**, and the tool fixes it.
   - **Verifier** → user gets a **deployable package** that can be verified against their Salesforce org.
3. See **all reports, all flagged files, confidence scores** — everything rendered visually.
4. A **complete, supervised-autonomous system** — build **on top of the current tool**.

**Verdict: yes, this is very buildable — and the current architecture was, almost accidentally, designed for it.**

---

## 2. One important reframing: "autonomous" **with** human gates

The ask mixes two ideas — "complete autonomous system" *and* "user reviews/fixes at each step." Those pull in opposite directions, so the right product is a **human-in-the-loop cockpit with two run modes**:

- **Supervised mode** — the pipeline **pauses at review gates** (after Plan, after Build+Critic, after Reconcile). The user inspects, edits, approves, or sends work back. This is the "see every agent, correct anything" experience.
- **Autopilot mode** — the pipeline runs straight through (today's behavior) and the user reviews everything at the end.

Same engine, same agents; the only difference is whether it stops at the gates. This framing is what makes the build tractable.

---

## 3. Why this is ~60–70% "wrap", not "rebuild"

The heavy lifting already exists and is reusable **unchanged**:

| Already built (reused as-is) | Becomes, in the web app |
|---|---|
| **Blackboard** ([blackboard.py](../h2a-mvp/src/agentic/blackboard.py)) — one object holding schema, plan, artifacts, decisions, open questions, review flags, completeness ledger | The **run state / checkpoint model** the UI reads and the user edits between gates |
| **The four agents** (Planner, Builder, Critic, Verifier) | The **steps** on the dashboard — each already produces structured output |
| **Planner output** — `PlanItem`s (Convert/Skip + native flags) | The **"files that will be migrated"** screen |
| **Builder output** — generated Apex/LWC on artifacts | The **per-file review** screen (with diffs/syntax) |
| **Critic output** — structured `findings` (severity/category/message) | The **review & override** screen |
| **Verifier** — `deploy_and_heal` against a real org ([verify.py](../h2a-mvp/src/verify.py)) | The **"verify against your org"** step + live self-heal display |
| **Reports** — `MIGRATION_PLAN.md`, `FEASIBILITY_REPORT.md`, the **completeness ledger**, per-item **confidence scores** | Dashboard **widgets** (rendered from data, not markdown) |
| **The VS Code webview** ([webview.ts](../h2a-vscode-extension/src/webview.ts)) — already visualizes results + a call graph | Proof the visualization layer is a known quantity; we generalize it into a full SPA |

**The engine's translation logic does not change.** We wrap it, stream it, checkpoint it, and put a UI on it.

---

## 4. The one real architectural change: a resumable, checkpointed pipeline

Today the orchestrator ([orchestrator.py](../h2a-mvp/src/agentic/orchestrator.py) `run_agentic_migration`) runs **start-to-finish in a single call** and prints progress. For supervised mode we refactor it into **discrete, resumable stages**, each of which:

1. does its work on the Blackboard,
2. **serializes the Blackboard** to a checkpoint (DB row / JSON — it's already a dataclass, so this is straightforward),
3. **returns control** so the server can show the UI and wait for the user's decision,
4. resumes the next stage from the (possibly user-edited) checkpoint.

```
 upload/clone → INGEST ─▶ [gate] PLAN review ─▶ [gate] BUILD+CRITIC review ─▶
   [gate] RECONCILE review ─▶ VERIFY (org) ─▶ REPORTS + download package
                    ▲ each ── serialize Blackboard checkpoint ──┘
```

This is the single biggest engineering item, and it's very achievable **precisely because all state already lives on one object.** Autopilot mode just calls the stages back-to-back with no gate.

---

## 5. Target architecture

```
┌──────────────────────────────  BROWSER (SPA)  ──────────────────────────────┐
│  React + TypeScript dashboard                                                │
│  • Upload / repo-URL picker            • Pipeline timeline (live)            │
│  • Per-agent panels (Plan/Build/Critic/Verify)   • Code viewer + diffs       │
│  • Review-gate actions (approve / edit / send back)                          │
│  • Reports: completeness ledger, confidence, flagged files                   │
│  • Salesforce org connect + deploy results   • Download SFDX package         │
└───────────────▲───────────────────────────────────────────────▲────────────┘
                │  REST (actions)                │  WebSocket / SSE (live progress)
┌───────────────┴────────────────────────────────┴───────────────────────────┐
│                          BACKEND API  (FastAPI, Python)                      │
│  • Run manager (create/advance/resume runs)   • Event stream (agent → UI)    │
│  • Job queue for long migrations (async workers)                            │
│  • Blackboard checkpoint store (Postgres/JSON)  • Auth / multi-tenant       │
│  • Git clone + sandboxed upload handling      • Salesforce OAuth + deploy   │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │        EXISTING ENGINE (reused, unchanged logic)                      │  │
│  │  agents · blackboard · generate/generate_lwc · verify · reports · RAG │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Stack choice (recommended):** FastAPI (Python — same language as the engine, so zero rewrite; native async + WebSockets), React + TypeScript + a component lib, Postgres for run/state, Redis + a worker (RQ/Celery) for long jobs, S3-compatible storage for uploads/output packages. Monaco editor for the in-browser code review/edit.

---

## 6. The stepped experience, mapped to what exists

| Step | User sees | Powered by (existing) | User can |
|---|---|---|---|
| **Start** | Upload zip or paste a Git URL; pick options (provider, supervised/autopilot) | new: upload/clone service | choose scope |
| **1 · Analyze & Plan** | File tree of the codebase; the **migration plan** — every target as Convert / Skip / **flagged (e.g. "consider CPQ")**; domains & order | `ingest`, `PlannerAgent`, completeness ledger | inspect files, **toggle include/skip**, edit a decision, approve |
| **2 · Build** | Each generated **Apex/LWC file** with syntax highlighting + source-vs-output view; live "building X of N" | `BuilderAgent`, `generate` / `generate_lwc` | review each file, flag one for rework |
| **3 · Review (Critic)** | The Critic's **findings** per file (behavior/security/governor), accept/override; **user can add a correction note** | `CriticAgent` findings | **inject feedback → re-run Builder** on that file, approve/override |
| **4 · Reconcile** | Schema changes the tool made (e.g. auto-added `Priority__c` with evidence) | `reconcile_schema` | approve/adjust |
| **5 · Verify** | Connect Salesforce org → **validate-only deploy** with live results + self-heal rounds; per-file **confidence** | `deploy_and_heal`, confidence scoring | connect org, run verify, re-heal |
| **6 · Deliver** | The **completeness ledger**, all **flagged files**, the full **feasibility report** — visual; **download the SFDX package** | reports + `write_outputs` | download, export report |

Everything in the "Powered by" column exists today. The work is the UI + the gate/resume plumbing.

---

## 7. Build plan & timeline

Assumes a small team: **1 backend/Python eng, 1 frontend eng, ~0.5 full-stack/DevOps** (a 3rd engineer shortens the calendar). Estimates are calendar time, sequential milestones with some overlap.

| Milestone | Scope | Effort |
|---|---|---|
| **M0 — Service foundation** | FastAPI wrapping the engine; kick off a migration via API; convert the engine's `print` progress into a structured **event stream** (SSE/WebSocket); run history in Postgres | **~3 weeks** |
| **M1 — Live read-only dashboard** | React SPA; upload/repo-URL; live pipeline timeline; file tree; **code viewer** for generated files; reports rendered (ledger, confidence, flagged). *Autopilot mode only* | **~4 weeks** |
| **M2 — Human-in-the-loop gates** ⭐ | Refactor orchestrator into **resumable, checkpointed stages**; Blackboard serialization; **Plan / Build+Critic / Reconcile review gates**; edit-and-resume; "send back to Builder with feedback" | **~5–6 weeks** |
| **M3 — Org verification + package** | In-browser **Salesforce OAuth**; validate-only deploy against the user's org; live self-heal display; **download SFDX zip** | **~3 weeks** |
| **M4 — Productionization** | Multi-user auth + tenancy, RBAC, **sandboxed/secure upload handling**, job queue + concurrency, AI-cost metering, observability, audit log | **~4–5 weeks** |
| **M5 — Pilot hardening & deploy** | Security review, load test, deploy (cloud or on-prem), docs, first customer pilot | **~2–3 weeks** |

- **Compelling stakeholder demo (MVP):** M0 + M1 + the **Plan gate** slice of M2 → **~6–8 weeks**. This already shows: upload → watch agents live → see files-to-be-migrated → see generated code → see reports.
- **Full production platform:** **~5–6 months** end-to-end with the team above.

A 2-week spike at the very start (M0 kickoff) to prove the **checkpoint/resume** refactor on one gate is strongly recommended — it de-risks M2, the only genuinely hard part.

---

## 8. Key decisions & risks to settle up front

1. **Hosting & code sensitivity (biggest one).** Clients' Hybris source is sensitive IP. Offer **both** a hosted SaaS *and* a **customer-VPC / on-prem** deployment (Docker Compose / Helm). This also lets a customer keep AI calls inside their own boundary. Decide the default before M4.
2. **Where the AI runs.** Same providers as today (Anthropic / OpenRouter / free offline mock). For a hosted product, decide whether the platform holds the AI key (metered billing) or the customer brings their own.
3. **Salesforce connection.** Move from local `sf` CLI to a proper **OAuth web flow** (JWT/connected app) so deploys work from the browser. Non-trivial but standard.
4. **Long-running jobs.** A repo can take many minutes. Needs a **job queue + workers + resumability**, not a request thread. (M0/M4.)
5. **Concurrency & AI cost at scale.** Rate limits, per-run cost caps, the existing model-routing (cheap vs frontier) becomes a real cost lever.
6. **Secure upload handling.** Untrusted uploaded code must be parsed in a **sandbox** (we only parse/generate, never execute it — lower risk, but still isolate).
7. **Auth/multi-tenant + audit.** Enterprise buyers will need SSO, roles, and an audit trail (the decisions log already gives us the content for the audit trail).

---

## 9. Recommendation

**Proceed, in two commitments:**

1. **Now → ~8 weeks: the MVP cockpit** (M0 + M1 + Plan gate). Reuses the engine wholesale; delivers the "watch the agents work, inspect the files, see the reports" experience the stakeholders asked for — enough to demo and to validate the UX direction.
2. **Then → ~3–4 more months: the production platform** (M2 full HITL, M3 org verify, M4 hardening, M5 pilot).

The reason the timeline is this short for something this ambitious: **we are not building a migrator — we already have one.** We're building a supervised-autonomy UI around a state model (the Blackboard) that was purpose-built to be inspected and checkpointed. That is the leverage.

---

### Appendix — the smallest first step (proves the whole thing)
A 1–2 week spike: a FastAPI endpoint that runs `run_agentic_migration` on an uploaded zip, streams the existing stage `print`s as SSE events, and renders them on a one-page React timeline — plus serializing the Blackboard to JSON after the Plan stage and showing the plan table. If that feels good, the rest is execution.
