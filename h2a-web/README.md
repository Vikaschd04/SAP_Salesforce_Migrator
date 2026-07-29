# H2A Web Dashboard (Phase 4 — MVP)

A browser dashboard that runs the **same** migration engine as the CLI and the VS Code
extension, and shows **each agent's work live**: analyze → comprehend → **Plan** (the files that
will be migrated) → **Build + Critic** (generated Apex/LWC per file) → Reconcile → Verify → the
**completeness ledger**, reports, and a downloadable Salesforce package.

> **Same engine, second front door.** The Python engine in `../h2a-mvp` is imported and reused
> unchanged. A small non-breaking `on_event` hook lets the dashboard watch the agents; the CLI and
> extension are unaffected (the hook is a no-op when unused).

## What's here

```
h2a-web/
├── backend/
│   ├── app.py           FastAPI: start run, live SSE events, browse files, reports, download zip
│   ├── run_manager.py   drives the engine in a background thread + per-run event log
│   └── requirements.txt fastapi · uvicorn · python-multipart
└── frontend/            static dashboard (no build step — plain HTML/CSS/JS)
    ├── index.html · styles.css · app.js
```

## Two frontends

- **`web/`** — the **modern React + TypeScript cockpit** (Vite, design system, Monaco diff,
  Migration Copilot). This is the primary UI; the backend serves its built `dist/` when present.
- **`frontend/`** — the original dependency-free dashboard, kept as a no-build fallback (served
  only when `web/dist` doesn't exist).

## Run it

```bash
# 1. backend deps (into the engine's venv, which already has the engine installed)
../h2a-mvp/.venv/bin/python -m pip install -r backend/requirements.txt

# 2. build the React cockpit (once, or after UI changes)
cd web && npm install && npm run build && cd ..

# 3. start the server (serves web/dist + all /api routes)
cd backend
../../h2a-mvp/.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8733

# 4. open the cockpit
open http://127.0.0.1:8733
```

For UI development with hot-reload: `cd web && npm run dev` (Vite on :5173, proxies `/api` to :8733).

### The React cockpit adds
- **Modern design system** (dark/light, teal signal accent), animated live pipeline stepper.
- **Diff tab** — Monaco **source-Java ↔ generated-Apex** (and Angular ↔ LWC) side-by-side, per target.
- **✦ Migration Copilot** — ask about the run in natural language (risks, skips, flags, Critic
  findings, a specific class). Grounded in the run's Blackboard; keyless answers in mock mode,
  full conversational answers on Anthropic/OpenRouter.

Then in the browser: keep the default path (`Testing/demo-commerce-suite`) or paste another
codebase path / upload a `.zip`, pick **Provider = Mock** (free, keyless) for a rehearsal, and hit
**Start migration**. Watch the stepper light up and the agent activity stream in real time.

- **Provider**: `mock` (free), `anthropic` (needs a valid key in `../h2a-mvp/.env`), or `openrouter`.
- **Engine**: `agentic` (agents) or `linear`.
- **Supervised (review gates)**: on by default — the run **pauses for your review** (see below). Turn off for Autopilot (run straight through, review at the end).
- **Verify vs org**: runs a validate-only deploy (needs the Salesforce CLI + a default org).

## Supervised mode — human-in-the-loop review gates

With **Supervised** ticked, the migration pauses at two gates and waits for you:

1. **Plan gate** — before any code is written, you see every target the Planner chose and can
   flip each one between **Convert** and **Skip**. Approve to continue. (Excluded targets are then
   truly skipped and show as `skipped` in the completeness ledger.)
2. **Build gate** — after the Builder + Critic finish, you review each generated file (with its
   Critic findings). Approve everything, **or type feedback on any file and “Send back & rebuild”** —
   the Builder regenerates it addressing your note, the Critic re-reviews, and you review again.
   (With the mock provider this exercises the loop; with a real provider your feedback changes the
   output.)

Under the hood the engine gained a small, non-breaking `gate` hook: when supervised, it blocks the
run thread at each gate until the dashboard `POST`s a decision, then resumes — no giant refactor,
because the Blackboard already holds all the state. Autopilot (`gate=None`) and the CLI/extension
are unaffected.

## API (for reference / future React frontend)

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/api/runs` | start a run (`input_path` **or** `upload` zip; `provider`, `engine`, `verify`) |
| `GET`  | `/api/runs/{id}` | status + full event history + result summary |
| `GET`  | `/api/runs/{id}/stream` | **SSE** live event stream |
| `GET`  | `/api/runs/{id}/files` | list generated files + reports |
| `GET`  | `/api/runs/{id}/file?path=…` | one file's content (path-guarded to the output dir) |
| `GET`  | `/api/runs/{id}/report?name=…` | a report rendered to **HTML** (+ raw Markdown) for the visual preview (whitelisted report names) |
| `POST` | `/api/runs/{id}/gate` | submit a review decision — `{action:"approve", overrides:{…}}` (plan) or `{action:"rework", feedback:{target:"note"}}` (build) |
| `GET`  | `/api/runs/{id}/package` | download the SFDX project as a `.zip` |

## Status & next steps

Covered so far: **Autopilot** (watch live, review at the end), **Supervised human-in-the-loop
gates** (Plan + Build review/rework), **visually rendered reports** — the Reports tab shows each
report as a styled HTML preview (headings, tables, code) via `GET /api/runs/{id}/report?name=…` —
and **agent-transparency views** so a reviewer can see *what the AI is actually doing* at each step:

- **Understanding tab** — as the Comprehender reads each class, its understanding is shown per
  class: purpose, the **business rules** it must preserve, the data it queries, side effects, plus
  (smarter analysis) its **dependencies**, concrete **migration risks**, and a **complexity** rating.
- **Plan tab / Plan gate** — every target with its decision, native-review flag, and the Planner's
  **rationale**. In supervised mode the Plan gate now shows each target's **purpose, rules to
  preserve, migration risks, and complexity** so you approve with full context.
- **Artifacts tab** — expandable per file: what the Builder **mapped**, the SObjects and **business
  rules preserved**, LWC bundle parts, and **every Critic finding** — severity/category/message **plus
  a concrete suggested fix** — not just a count. The live feed also shows the **Critic⇄Builder repair
  loop** when it fires.
- **Audit tab** — every agent decision streams into a **live, numbered timeline** as it happens (the
  same ordered trail is also written to `MIGRATION_PLAN.md`).

> Depth scales with the provider: under **mock** these views show structure (purpose, patterns,
> bundle parts) but sparse prose, because the mock stub doesn't invent business rules or findings;
> with a real provider (Anthropic/OpenRouter) the rules, queries, and Critic findings fill in.

Per the proposal
([../docs/WEB_PLATFORM_PROPOSAL.md](../docs/WEB_PLATFORM_PROPOSAL.md)), remaining milestones:

- **In-browser Salesforce OAuth** for the Verify step (replacing the local `sf` CLI).
- **Reconcile gate** + inline code editing (edit a file in the browser, not just send it back).
- **Productionization** — auth/multi-tenant, sandboxed uploads, a job queue for concurrent runs, and
  a proper React SPA (the current no-build dashboard is intentionally dependency-free).

## Notes / limitations (MVP)

- Runs execute one at a time (the engine uses a process-global cwd + `H2A_PROVIDER`); a job queue
  comes in productionization.
- Output/upload folders live under the OS temp dir; not persisted across restarts.
- Local dev server only — do not expose to a network without auth + the hardening above.
