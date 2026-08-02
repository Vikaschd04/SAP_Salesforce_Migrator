# Roadmap: from impressive demo → high-performance industry product

Companion to [PLATFORM_VISION.md](PLATFORM_VISION.md) (the product vision) and
[DIFFERENTIATORS.md](DIFFERENTIATORS.md) (the competitive bets). **This document is about
the engineering that makes it survive a real customer repository.**

---

## 0. The honest starting point (verified, not assumed)

The intelligence is strong; the **execution engine is a single-threaded prototype**. Four
measured facts:

| Fact | Consequence |
|---|---|
| **No concurrency anywhere** — every LLM call is sequential | a 300-class repo runs ~1.5–2.5 hours |
| **The agentic path ignores `incremental`** | every re-run redoes 100% of the work, even for a 1-line change |
| **Model routing ships disabled** (`routing.enabled: false`) | frontier-model prices for trivial comprehension |
| **One global run lock, in-memory state** | one migration at a time; a restart loses everything |

**The math that matters.** A realistic Hybris extension (~300 classes) needs roughly
300 comprehend + ~150 generate + ~150 critic + repairs ≈ **650–900 LLM calls**. At ~8s each,
**sequential ≈ 1.5–2 hours**. That is the number to attack first — it's the difference between
a tool a team runs *during a meeting* and one they run *overnight and hope*.

---

## Phase 6 — Performance & scale ⭐ *(start here)*

### 6A. Concurrency — the single biggest win (target: **5–8× faster**)
The workload is far more parallel than the current code assumes:

- **Comprehend is embarrassingly parallel.** Every class is analyzed independently — there is
  no reason for 300 sequential calls. Bounded worker pool → near-linear speedup.
- **Build is *wavefront*-parallel.** `get_translation_schedule` already yields a dependency-safe
  order; that's a topological sort, so **everything at the same depth can build simultaneously**.
  Only cross-level ordering must be respected (for signature availability).
- **Critic is parallel** per artifact, and independent of other artifacts.

Implementation notes that keep it safe:
- Bounded pool (`concurrency: 8`, configurable) — respects provider rate limits.
- The Blackboard is mutated from workers, so guard `artifacts`/`registry` writes with a lock,
  or (cleaner) have workers return results and merge on the orchestrator thread.
- Events already carry `target_name`, so the UI stays correct with out-of-order completion —
  the Flow graph becomes genuinely alive (8 nodes lighting up at once).

**Expected: ~2 hours → ~15–20 minutes** on a 300-class repo.

### 6B. Incremental / delta migration (target: **10–50× on re-runs**)
`state_ledger.py` and `incremental: true` exist but the **agentic path never consults them**.
Hash each source file; on re-run, skip classes whose hash and dependencies are unchanged and
reuse the prior artifact. Real migrations are iterative — the second run should take a minute,
not the full two hours.

### 6C. Cost engineering (target: **50–70% cheaper**)
- **Turn model routing on by default** — comprehension/planning on the cheap tier, generation
  and criticism on the frontier tier. The routing layer is already written and unused.
- **Prompt slimming** — stop sending whole-file source for large classes; send the extracted
  signature + relevant regions (the ingest already parses methods/fields).
- **Per-run cost cap + live spend meter**, surfaced in the cockpit before and during a run.

### 6D. Resilience at scale
At 900 calls, rare failures become certainties:
- App-level **retry with jittered backoff** on 429/5xx (SDK defaults are not enough at this volume).
- **Partial-failure resume** — a failed class is already contained; make the *run* resumable so
  you re-do 3 classes, not 300.
- **Streaming progress persistence** so a browser refresh (or a proxy drop) never loses a run.

---

## Phase 7 — Multi-user platform
Turn a single-user tool into a service:
- **Job queue + workers** (replace the process-global lock + `os.chdir`; make the engine
  cwd-independent so runs can be concurrent *and* isolated).
- **Postgres-backed run store** + Blackboard checkpoints per phase → durable, resumable,
  shareable runs and real run history.
- **Auth, orgs/projects, RBAC**, per-run audit trail (the decisions log is already the content).
- **Sandboxed uploads**, per-tenant key vault, cost metering per tenant.

## Phase 8 — Proof & correctness (the moat)
Sequenced from [DIFFERENTIATORS.md](DIFFERENTIATORS.md), highest leverage first:
1. **Business-rule ledger** — completeness measured in *rules preserved*, not files converted.
2. **Line-level provenance** — every Apex line traceable to its Java origin.
3. **Hybris anti-pattern radar** — FlexibleSearch-in-loop, `@Transactional`, interceptors, ImpEx volume.
4. **Risk-ranked review triage** — what makes human review survive 400 classes.
5. **Characterization tests** — replay their own JUnit cases against generated Apex in a scratch org.

## Phase 9 — Enterprise readiness
Observability (metrics/tracing/error tracking), SSO, **deterministic replay for audit**,
signed sign-off contract export, security review, on-prem/VPC packaging, load testing, SLOs.

---

## Suggested sequence & why

| Order | Work | Why now |
|---|---|---|
| **1** | 6A concurrency | Unblocks *every* demo on a real repo. Biggest visible win per unit of effort. |
| **2** | 6B incremental | Makes iteration usable; migrations are never one-shot. |
| **3** | 6C cost + 6D resilience | Both become mandatory the moment runs are big and real. |
| **4** | Phase 8 (rule ledger → provenance) | The differentiation that wins the deal, once runs are fast enough to iterate on. |
| **5** | Phase 7 platform | Needed for multi-user/SaaS, but no customer cares until 1–4 are true. |
| **6** | Phase 9 | Procurement gates, not product gates. |

> **The one metric to lead with:** *"A 300-class Hybris extension, fully migrated, reviewed,
> and org-verified — in under 20 minutes, for under $X, with every business rule accounted for."*
> Phases 6 and 8 are what make that sentence true.
