# H2A — Phase 5 Vision: The Industry-Grade AI Migration Cockpit

**Goal:** evolve the working dashboard into *the* best-in-class tool a migration team
lives in for weeks — modern, trustworthy, and genuinely intelligent — not a script that
emits Apex.

**Version:** 0.1 (vision) · **Date:** 2026-07-29 · **Builds on:** [WEB_PLATFORM_PROPOSAL.md](WEB_PLATFORM_PROPOSAL.md)

---

## 1. Where we honestly are

**Strong core, thin edges.**

- **Engine (mature):** agentic team (Planner / Builder / Critic / Verifier) over a shared
  Blackboard; *convert-everything* policy + completeness ledger; **backend Java→Apex and
  Spartacus/Angular→LWC**; smarter comprehension (dependencies, migration risks, complexity);
  Critic findings with suggested fixes; live audit trail; self-healing deploy loop.
- **Two front doors at parity:** VS Code extension + web dashboard (FastAPI + SSE + a
  dependency-free SPA), supervised human-in-the-loop gates (Plan + Build), visual reports.
- **Gaps that block "industry-ready":** single-user, **in-memory** (runs lost on restart),
  no auth, **one run at a time**, Verify still uses the local `sf` CLI, no in-browser code
  editing, and the UI is hand-rolled (no design system, no diff view, no run history).

## 2. The vision — three pillars

> "Not a converter you run — a **supervised-autonomy cockpit** your team operates, that
> proves its work against a real org and **gets smarter every time you correct it**."

### Pillar 1 — Industry-ready foundation (make it *real*)
- **Persistence + checkpointing:** Postgres; serialize the Blackboard after each stage so runs
  survive restarts, can be paused/resumed, shared, and audited.
- **Concurrency:** a job queue + workers (the engine is currently process-global/one-at-a-time).
- **Auth & multi-tenant:** SSO/OAuth, orgs/projects, RBAC, per-run audit log (the decisions log
  already gives us the audit content).
- **Secure by default:** sandboxed uploads, **BYO-key in a vault** (never in files), AI-cost
  metering + per-run caps, observability + error tracking.
- **Deploy:** Docker/Helm — **SaaS *and* customer-VPC/on-prem** (client Hybris source is sensitive IP).

### Pillar 2 — Modern UI (make it *feel* like the best tool)
- **Real SPA:** React + TypeScript + a design system (tokens, dark/light, a11y, responsive).
- **Live pipeline visualization:** the agent team working in real time — a stage timeline +
  an animated dependency graph, not a log tail.
- **In-browser code review + edit:** **Monaco** with a **source-Java ↔ generated-Apex diff**,
  inline Critic findings, edit-and-resave at the gate (not just "send back").
- **Data-driven report widgets:** confidence gauges, a completeness donut, a **risk heatmap**
  by class/domain — rendered from data, not raw markdown.
- **Project workspace:** run history, search, compare runs, resumable sessions.

### Pillar 3 — Futuristic AI agents (the moat — where we win)
- **Migration Copilot (chat with your migration):** ask in natural language — *"why did you
  convert pricing this way?"*, *"redo OrderService as an fflib Selector"*, *"explain this Critic
  finding"*, *"convert everything under /promotions but flag CPQ"* — and the agents act on it.
- **Autonomy dial:** one control from **full autopilot → step-through gates → per-file approval**,
  so a team scales trust as confidence grows.
- **Visible multi-agent reasoning:** Builder↔Critic debate, reasoning traces, "second-opinion"
  review — transparency is the trust primitive for a critical migration.
- **Org-verified confidence:** confidence is *earned* by the real-org compile + test gate, shown
  live (self-heal rounds), never a fake "100%".
- **Learning loop (the durable advantage):** capture every reviewer edit/override as few-shot
  memory + **org-specific conventions**, so each migration makes the next one better and the
  output matches the customer's house style (naming, patterns, security posture).
- **Org-aware RAG:** ingest the customer's *existing* Apex to match their conventions, not generic ones.

## 3. Phased roadmap

| Phase | Theme | Outcome | Rough effort |
|---|---|---|---|
| **5A** | Foundation | Postgres + checkpointed Blackboard, job queue, auth/multi-tenant → durable, concurrent, multi-user | ~4–6 wks |
| **5B** | Modern UI | React SPA + design system + **Monaco diff editor** + report widgets + run history | ~4–6 wks |
| **5C** | Org loop | In-browser **Salesforce OAuth** verify + live self-heal + one-click deployable package | ~3 wks |
| **5D** | AI moat | **Migration Copilot**, autonomy dial, **learning loop**, org-aware RAG | ~5–6 wks |
| **5E** | Harden & ship | Security review, load test, Docker/Helm, first customer pilot | ~3 wks |

**Fastest "wow" for a stakeholder demo:** a thin vertical slice — **SPA shell + Copilot chat +
Monaco diff review** on top of today's engine (a piece of 5B + 5D). It *looks and feels* like a
next-gen tool immediately, without waiting on the full foundation.

**Fastest path to real usage:** 5A first (durability + concurrency + accounts), because nothing
else is trustworthy for real client work until runs persist and multiple people can use it.

## 4. Recommendation

Two tracks, run slightly in parallel:
1. **Perception track (demo/sales):** the 5B+5D vertical slice — modern SPA + Copilot + diff review.
2. **Substance track (production):** 5A foundation underneath it.

Ship the vertical slice first for the "best tool" impression, then harden. The engine already
does the hard part (translation + review + verification); Phase 5 is about **trust, scale, and a
UI worthy of the intelligence underneath.**
