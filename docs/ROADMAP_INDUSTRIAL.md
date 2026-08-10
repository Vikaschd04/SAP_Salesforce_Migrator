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

> **Status, kept honest.** Phases 6, 7 and 8's first two items have shipped. What each
> actually delivered — measured, not targeted — is recorded inline below. Anything without
> a ✅ is still open.

## Phase 6 — Performance & scale · ✅ **shipped** (bar two items)

### 6A. Concurrency · ✅ — **measured 7× at concurrency 8**, byte-identical output
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

### 6B. Incremental / delta migration · ✅ — **100% of AI work skipped** on an unchanged re-run
`state_ledger.py` and `incremental: true` exist but the **agentic path never consults them**.
Hash each source file; on re-run, skip classes whose hash and dependencies are unchanged and
reuse the prior artifact. Real migrations are iterative — the second run should take a minute,
not the full two hours.

### 6C. Cost engineering · ⚠️ **partial** — routing measured ~20%, not the 50–70% targeted
- **Turn model routing on by default** — comprehension/planning on the cheap tier, generation
  and criticism on the frontier tier. The routing layer is already written and unused.
- ✅ **Model routing on by default** — cheap tier for comprehend/plan, frontier for
  generate/critic. Measured ~20%: generation and critique carry most of the tokens and
  stay on the frontier tier, so routing alone is a trim, not a halving.
- ✅ **Per-model cost accounting + live spend meter** in the cockpit.
- ✅ **Prompt slimming** — import blocks and provably-trivial accessors stripped from the
  source sent to the model; logic and javadoc kept verbatim. **~9% end-to-end on the
  hand-written demo, 74% on a realistic generated Hybris `*Model` class** — and a real
  estate is mostly those, so the demo badly understates it. Falls back to untouched
  source on anything unexpected.
- ⬜ **Per-run cost cap.**

### 6D. Resilience at scale · ✅
At 900 calls, rare failures become certainties:
- App-level **retry with jittered backoff** on 429/5xx (SDK defaults are not enough at this volume).
- **Partial-failure resume** — a failed class is already contained; make the *run* resumable so
  you re-do 3 classes, not 300.
- ✅ **Streaming progress persistence** — the client stores the run id and rejoins on
  mount, so a refresh, a dropped connection or a closed tab no longer orphans a run.

---

## Phase 7 — Multi-user platform · ✅ **shipped**
- ✅ **cwd-independent engine** — the `os.chdir` turned out to be unnecessary; config,
  mappings and cache already resolve against the engine's own root.
- ✅ **Concurrent, isolated runs** — the process-global `H2A_PROVIDER` write was a real
  race (a mock run could inherit another run's live provider). Replaced with a ContextVar
  propagated into pool workers.
- ✅ **Bounded admission** — FIFO queue with a visible position, capped by
  `H2A_MAX_CONCURRENT_RUNS`. Removing the lock without this traded "one user at a time"
  for "ten users exhaust the box".
- ✅ **Durable run store** — SQLite rather than Postgres, deliberately: the same code runs
  on a laptop and in an extension host, where requiring a database server would make the
  product worse. Behind an interface, so swapping it later touches one file.
- ✅ **Accounts, sessions, tenant isolation** — scrypt passwords, hashed session tokens,
  isolation enforced in SQL *and* middleware. A second tenant gets 404, not 403, so the
  existence of a migration is not disclosed either.
- ✅ **Per-tenant key vault** — Fernet-encrypted under a secret held outside the database.
- ⬜ **Postgres**, org/project hierarchy, RBAC beyond admin/member, per-tenant cost metering.

## Phase 8 — Proof & correctness (the moat) · 🔶 2 of 5
1. ✅ **Business-rule ledger** — completeness measured in *rules preserved*, not files converted.
2. ✅ **Characterization tests** — the customer's own JUnit cases replayed against the
   generated Apex, each graded by evidence strength. The adapter bridge is what makes it
   work against deliberately bulkified output (0% → 56% on our own demo).
3. ✅ **Hybris anti-pattern radar** — eleven rules for the patterns that are ordinary in
   Hybris and hazardous in Apex, surfaced at the Discovery gate before a plan is approved.
   Ten findings on the reference corpus, two critical. Deterministic: no model calls, no org.
4. ⬜ **Risk-ranked review triage** — **next.** The radar now produces the signal it ranks on.
5. ⬜ **Line-level provenance** — the largest of the three and independent of them.

> Also shipped, outside the original list: **source preflight** — a non-Hybris upload is
> refused before a run object exists, and credentials found in the archive are reported by
> file and line (never by value).

## Phase 9 — Enterprise readiness
Observability (metrics/tracing/error tracking), SSO, **deterministic replay for audit**,
signed sign-off contract export, security review, on-prem/VPC packaging, load testing, SLOs.

---

## Suggested sequence & why

| Order | Work | Why now |
|---|---|---|
| ~~1~~ | ~~6A concurrency~~ | ✅ done — 7× measured |
| ~~2~~ | ~~6B incremental~~ | ✅ done — 100% skip on unchanged re-runs |
| ~~3~~ | ~~6C/6D~~ | ✅ resilience; 6C partial — prompt slimming still open |
| ~~4~~ | ~~Phase 7 platform~~ | ✅ done, and moved ahead of Phase 8 in practice: concurrency made isolation and admission control urgent |
| **5** | **Anti-pattern radar → risk triage** | **Next.** Reuses the preflight static-analysis walk; no model calls, no org, demos on a locked-down laptop |
| **6** | Line-level provenance | Unlocks review, audit and impact analysis together |
| **8** | Phase 9 | Procurement gates, not product gates |

> **The one metric to lead with:** *"A 300-class Hybris extension, fully migrated, reviewed,
> and org-verified — in under 20 minutes, for under $X, with every business rule accounted for."*
> Phases 6 and 8 are what make that sentence true.
