# v2 Delivery Plan — phase by phase

**Branch:** `v2` · **Fallback:** `main` (v1, works, stays working) · **Updated:** 2026-08-12

The strategy is in [ROADMAP_MULTI_PLATFORM.md](ROADMAP_MULTI_PLATFORM.md). This is the
build sheet: every phase broken into work items, each with what "done" means and how it is
checked. Status is current, not aspirational.

## Where we are

| Phase | | Status |
|---|---|---|
| **0** | Real-provider validation | ⛔ **Blocked — needs a provider key** |
| **1** | The seam | 🔶 **~80% — seams for plan/emit/validate, knowledge packs, the purity ratchet, and a second pipeline registered** |
| **2** | Adobe Commerce source adapter | ⏳ Not started |
| **3** | SAP Hybris target adapter + oracle | ⏳ Not started |
| **4** | Two-pipeline product surface | ⏳ Not started |
| **5** | Scale hardening | ⏳ Not started |

Two v1 bugs were found while building Phase 1 and fixed on `main` first, because they cost
money on the shipped pipeline: the recipe hash was non-deterministic across processes (so
incremental reuse never hit, and every re-run re-billed the whole estate), and the console
contradicted the ledger about business processes.

---

## Phase 0 — Real-provider validation

**Blocked on a key, not on engineering.** Everything below is built on a proof stack that
has only ever run against the `mock` provider. The first real attempt found a defect that
339 unit tests had not.

| # | Work item | Done when |
|---|---|---|
| 0.1 | Supervised Hybris→Salesforce run against a real model | All three gates walked; every assurance panel populated |
| 0.2 | Inspect comprehension output on a class with documented rules | Business rules extracted, not empty |
| 0.3 | Inspect the characterization adapter bridge on real output | Bridge guards hold; no model-written assertions |
| 0.4 | Inspect provenance on real renames | `_norm()` catches the renames Opus actually makes |
| 0.5 | Confirm the repair loop converges | Bounded rounds, no runaway |
| 0.6 | Fix whatever 0.2–0.5 surface | Findings closed or explicitly deferred |

**Exit:** a real migration walked end to end, with findings fixed.
**Cost:** ~$2–4 on the reference corpus. One session.

---

## Phase 1 — The seam · **complete**

### Delivered

| # | Work item | Verified by |
|---|---|---|
| 1.1 | **Golden-output harness** — 128 output files snapshotted | `test_reference_migration_is_unchanged` |
| 1.2 | **Determinism check** | `test_two_identical_runs_agree` — found the recipe-hash bug |
| 1.3 | **IR extracted and versioned** (`src/ir.py`) | Lossless round-trip test, incl. unmodelled-field passthrough |
| 1.4 | **Pipeline registry** (`src/pipeline.py`) — registration, detection, resolution | 16 unit tests |
| 1.5 | **Engine-version switch** — flag → env → config → v1 | Precedence and bad-value fallback tested |
| 1.6 | **Hybris source + Salesforce target adapters** (thin) | Adapter reads the whole model incl. processes and hazards |
| 1.7 | **v1 ≡ v2 proof** | `test_v2_engine_matches_v1_exactly` — byte-identical, 128 files |
| 1.8 | **Target adapter owns candidate targets** — the Planner no longer imports `generate.plan_targets` | 6 tests incl. a spy proving the adapter is *actually* called on v2, not silently bypassed |
| 1.9 | **Target adapter owns the output layout** — `emit()` takes an `ir.DataModel` and writes the platform's own tree | 3 tests + a spy run; golden green |
| 1.12 | **Knowledge packs per pipeline** — prompts, mappings and RAG moved to `packs/<pair>/`, resolved from the run context | 8 tests; golden green after moving 14 files and rewiring 7 call sites |
| 1.10 | **Target adapter validates its own output** — 4 agentic call sites routed via `validate_artifact()` | 5 tests + a spy showing 43 real calls through the adapter; golden green |
| 1.15 | **CI purity rule** — the assurance layer may not import an adapter, enforced as a ratchet on platform vocabulary | 24 tests; zero adapter imports today, 4 modules carry vocabulary debt tied to 1.13/1.14 |
| 1.11 | **Verifier moves behind `target.verify()`** — the agent hands over a `VerifyRequest`, not a Salesforce CLI call | Golden green; `--verify` unchanged |
| 1.14 | **`provenance` / `alignment` internals renamed** `apex_*` → `target_*`, `java_*` → `source_*` (cockpit components too) | Golden caught a real bug: `signoff` was reading the old keys, silently dropping every caveat |
| 1.13 | **`characterize` split into mine / plan / emit** — `adapters/java_junit_mining.py` (source), `adapters/apex_characterization.py` (target), neutral planner between | 25 tests; only diff in 128 golden files was one intended word |
| 1.16 | **Comprehension prompt selected per pipeline** — already satisfied by 1.12's packs | Prompt resolves through `packs.prompt()`, verified per pipeline |
| — | **Second pipeline registered (scaffolded)** — `adobe->hybris` with honest stubs, a runnable guard, and its own pack directory | 18 tests; detection/resolution/packs exercised against two platforms |

### What Phase 1 cost, and what it bought

Sixteen items, each a separate commit, each with the golden harness green across it. The
harness was built first and earned it: it caught **three** regressions the 444-test unit
suite did not — a non-deterministic recipe hash that would have re-billed every
incremental re-run, a rename that silently deleted every sign-off caveat, and a
report-wording drift. None of the three would have failed a unit test.

The purity ratchet now stands at **one module clear and three carrying wording debt**:

| Module | Platform vocabulary in code | Owner |
|---|---|---|
| `characterize` | none — cleared by 1.13 | — |
| `provenance`, `alignment`, `signoff` | `apex`, `salesforce` in *report prose* only | 4.4 |

That distinction matters: the keys, the logic and the control flow are neutral. What is
left is the sentence a Salesforce customer reads, which *should* say Apex — making it
follow the pipeline is a feature (4.4), not debt pretending to be one.

**Exit:** every stage reachable through an adapter; v2 still byte-identical to v1; the
purity rule enforced.

> **Design question surfaced by 1.9, for Phase 3.** `bb.schema` is already *target*-shaped —
> a Salesforce SObject model derived from Hybris item types, built by `build_schema()` long
> before any adapter sees it. `write_schema_metadata()` therefore emits Salesforce object
> XML from it. A Hybris target needs `items.xml` from the same source facts, so the schema
> stage itself has to move behind the seam, not just its writer. That is a larger change
> than a call-site rewire and belongs with the Hybris target adapter, not here.
**Estimate for the remainder:** 2–3 weeks.

---

## Phase 1.5 — Edge-case hardening · the differentiator

Phase 1 made a second migration *possible*. This phase is what makes the first one worth
paying for. Every item comes from [`EDGE_CASES.md`](EDGE_CASES.md), which is the register
of places where a plausible-looking conversion is silently wrong — and which is the honest
answer to "why this and not a generic code translator".

Ordered by **damage prevented per unit of work**, not by difficulty.

| # | Work item | Register rows | Why it ranks here |
|---|---|---|---|
| ~~1.26~~ | ✅ **Generated-source detection** — build-owned directories and generator banners; held aside with a reason and a ledger row | E4 | Pure cost, and the cheapest item on the list. The reference corpus contains no generated sources, so golden stayed green with no re-baseline — the saving is real but its size is unmeasured until this runs against a licensed estate. |
| 1.17 | **Numeric-fidelity pass** — `BigDecimal` scale/`RoundingMode`, `double` money, null arithmetic | A1, A2, A5 | The only failure class in the register that is invisible to *every* other gate: it compiles, deploys, passes review, and drifts a cent per order forever. |
| 1.18 | **Picklist metadata for dynamic enums** — emit the values, not just the field | A3 | Deploys green, fails on first use. A green deploy that fails in production is worse than a red one. |
| 1.20 | **Name and shape ceilings** — 40-char API names, 500-field limit, 2-master-detail limit, cross-extension collisions | A6–A10, F3 | Silent *data loss*: two attributes truncating into one field deploys cleanly and merges two columns. |
| 1.23 | **FlexibleSearch → SOQL translator** with an honest refusal | C1–C4 | The most-used single feature in a Hybris estate, and the one where a model most confidently produces text that cannot work. Refusing with a named reason beats guessing. |
| 1.21 | **Transaction and re-entry semantics** — savepoint mapping, recursive-trigger guards | B4, B6 | `maximum trigger depth exceeded` in production, from code that passed every test. |
| 1.22 | **Heap-pressure rule** — a query under the row cap and over the 6 MB heap cap | B10 | Falls between the two rules that exist today. |
| 1.19 | **Localized attributes → Translation Workbench** | A4 | For an EU retailer this is most of their content, and flattening loses it without a warning. |
| 1.27 | **Cycle-breaking in the wavefront planner**, recorded where it broke | F1 | Correctness of the run itself; applies to both pipelines. |
| 1.28 | **Oversized-unit chunking** — comprehend and stitch rather than truncate | F4 | Silent truncation is the worst failure mode there is: output looks complete. |
| 1.29 | **Dead-code flagging** — units referenced only by their own tests | F7 | Budget, and a genuinely useful finding for the customer. |
| 1.24 | **Frontend gaps** — RxJS chains, slot selectors, CMS-driven instantiation | D2–D4 | Lower rank only because the frontend path already refuses more honestly than the backend one. |
| 1.25 | **Integration surface** — `@RestResource` caps, guest-user/CSP prerequisites, External Id for upsert | E1–E3 | Deployment-time prerequisites; better as a checklist in the sign-off than as generated code. |

**The rule this phase follows:** *a detector that explains beats a rewrite that guesses.*
Several items above deliberately stop at "flag it, name the fix" — because a flagged
hazard is actionable and a confidently wrong rewrite is a liability the customer discovers
in production. Each new detector ships with a `Testing/` fixture that actually trips it.

**Exit:** every row in the register is `covered` or `partial`; no row is an undocumented
gap; the run tells the customer which of these applied to *their* estate.

## Phase 2 — Adobe Commerce source adapter

Delivers the source half. Validated against the **Salesforce** target as a test fixture —
never shipped as a product, but it means the new adapter is proven against a real compiler
before it is ever paired with a target we cannot verify as strongly.

| # | Work item | Done when |
|---|---|---|
| 2.1 | Reference Magento project in `Testing/` | Realistic module: DI, observers, plugins, crontab, EAV, PHPUnit |
| 2.2 | `detect()` — `composer.json` type, `registration.php`, `etc/module.xml` | Preflight refuses a non-Magento upload; reports `env.php` credentials |
| 2.3 | PHP parser integration (`tree-sitter-php` or equivalent) | Classes, methods, params, type hints → IR units |
| 2.4 | `di.xml` reader — preferences, types, plugins | Wiring in the IR; **`around` plugins flagged, never faked** |
| 2.5 | `events.xml` observer reader | Observers as IR units with their event |
| 2.6 | `crontab.xml` reader | `ScheduledJob` entries |
| 2.7 | `db_schema.xml` reader | Declared tables/columns → `DataModel` |
| 2.8 | EAV attribute reader | What is declarable is read; **the residue is reported, not omitted** |
| 2.9 | PHPUnit miner | `RecordedBehaviour` entries for characterization |
| 2.10 | ~10 Magento hazard rules | N+1 collection loads, `ObjectManager` use, `around` plugins, raw SQL |
| 2.11 | PHP symbol patterns for provenance | Methods located in PHP as reliably as in Java |
| 2.12 | Conservative type inference + triage routing | Every unresolved type lands in must-review, never guessed |
| 2.13 | Adobe→Salesforce fixture in the test suite | Deploys clean against a real org |

**Exit:** 100% of the reference Magento project accounted for in the ledger; the fixture
deploy-verifies.
**Efficiency gate:** PHP slimming ≥30%; comprehension on the cheap tier.
**Estimate:** 8–10 weeks.

---

## Phase 3 — SAP Hybris target adapter **and its oracle**

Shipped together — per the roadmap, a pipeline that cannot be verified cannot make the
claim the product is sold on.

### The adapter

| # | Work item | Done when |
|---|---|---|
| 3.1 | Extension scaffolding | `extensioninfo.xml`, `build.xml`, correct directory layout |
| 3.2 | Java service + interface generation | Idiomatic Spring services from IR units |
| 3.3 | DAO generation with FlexibleSearch | Queries shaped as a Hybris developer would write them |
| 3.4 | `*-items.xml` emission | Data model from the IR, with EAV residue noted |
| 3.5 | ImpEx emission | Seed data, idempotent |
| 3.6 | Spring cron trigger + `AbstractJobPerformable` emission | Same timing as the source |
| 3.7 | Business-process XML emission | The inverse of the Flow generator already built |
| 3.8 | Hybris Critic knowledge pack | Reviews against Hybris idiom, not Salesforce |
| 3.9 | `has_oracle` reflects reality per rung | Sign-off never claims more than the rung that ran |

### The oracle — three rungs, in order

| # | Rung | Needs | Done when |
|---|---|---|---|
| 3.10 | Parse + resolve against a **stub classpath** of platform APIs | No licence | 100% of generated Java parses and resolves |
| 3.11 | Real `javac`/Gradle against a licensed platform | **Customer-supplied SAP Commerce** | Compiles, real errors captured |
| 3.12 | Self-heal from real compiler output | 3.11 | Bounded loop, as Salesforce has today |

> **Confirm platform availability before this phase starts, not during.** Rung 1 needs no
> licence and catches most errors; rungs 2–3 are gated on something we do not control.

**Exit:** Adobe → Hybris produces an extension a Hybris developer recognises, everything
accounted for, and the sign-off distinguishes *statically checked* from *compiled*.
**Estimate:** 10–13 weeks.

---

## Phase 4 — Two-pipeline product surface

| # | Work item | Done when |
|---|---|---|
| 4.1 | Auto-detect source, offer valid target | Cockpit says "This is Adobe Commerce 2.4.6 — migrate to SAP Hybris?" |
| 4.2 | Pipeline recorded in sign-off and checkpoints | An audit says which migration it was |
| 4.3 | Per-pipeline forecast constants | PHP→Java measured, not extrapolated from Java→Apex |
| 4.4 | Reports and cockpit made pipeline-aware | No "Apex" anywhere in a Hybris run |
| 4.5 | Extension + CLI expose the pipeline choice | Same choice on all three surfaces |
| 4.6 | Docs, decks and COCKPIT_GUIDE updated | Both pipelines documented |

**Exit:** either pipeline runs from one instance; neither knows about the other.
**Estimate:** 2–3 weeks.

---

## Phase 5 — Scale hardening

Phases 1–4 are validated on corpora of tens of classes. This proves the numbers at
enterprise size.

| # | Work item | Target |
|---|---|---|
| 5.1 | 2,000-class synthetic estate per pipeline | Runs end to end |
| 5.2 | Triage precision measured | ≥60% `routine`, **zero** defects found in that band |
| 5.3 | Incremental re-run economy | 5% source change ⇒ ≤10% of original cost |
| 5.4 | Routing + slimming measured | ≥40% cheap-tier calls, ≥30% prompt reduction |
| 5.5 | Wall clock at concurrency 8 | <3 h for 2,000 classes |
| 5.6 | Memory profile | `source_corpus` duplication and checkpoint size measured at 50 MB |
| 5.7 | Concurrent large runs | Admission and isolation hold |
| 5.8 | Forecast accuracy | Actual spend inside the quoted range; cap holds |

**Exit:** all six correctness gates hold at 2,000-class scale, every efficiency budget met
and published.
**Estimate:** 3–4 weeks.

---

## The rules that apply to every phase

1. **v1 stays the default and stays working.** `main` is the fallback until v2 has earned
   the switch.
2. **The golden harness is green at every commit.** If output changes, the change is
   deliberate and the manifest diff is explained in that commit.
3. **Correctness gates before efficiency gates.** A faster wrong answer is worse.
4. **Nothing in the assurance layer learns a platform name.** Enforced in CI from 1.15.
5. **Surface, never guess.** Every inference and every gap goes to triage or the ledger.

## Definition of done, for the whole programme

Both pipelines run from one instance. All six correctness gates hold at 2,000-class scale
on both. Every efficiency budget is met and published. `main` and `v2` are merged, and the
sign-off contract states, for any run, which pipeline produced it and which verification
rung it reached.
