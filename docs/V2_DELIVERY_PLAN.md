# v2 Delivery Plan — phase by phase

**Branch:** `v2` · **Fallback:** `main` (v1, works, stays working) · **Updated:** 2026-08-12

The strategy is in [ROADMAP_MULTI_PLATFORM.md](ROADMAP_MULTI_PLATFORM.md). This is the
build sheet: every phase broken into work items, each with what "done" means and how it is
checked. Status is current, not aspirational.

## Where we are

| Phase | | Status |
|---|---|---|
| **0** | Real-provider validation | ⛔ **Blocked — needs a provider key** |
| **1** | The seam | 🔶 **~40% — registry, IR, adapters and golden harness landed** |
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

## Phase 1 — The seam · ~40% delivered

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

### Remaining

Each item moves one stage behind the seam. **Every one is a separate commit, and the
golden harness must stay green across it** — that is what makes this safe to do
incrementally rather than in one irreversible change.

| # | Work item | Files | Done when |
|---|---|---|---|
| 1.8 | Target adapter takes over `plan_targets` | `adapters/salesforce_target.py`, `orchestrator.py` | Golden green; v2 ≡ v1 |
| 1.9 | Target adapter takes over `write_outputs` / layout | same | Golden green |
| 1.10 | Target adapter takes over `validate` | `validate.py` call sites | Golden green |
| 1.11 | Verifier moves behind `target.verify()` | `builders.py::VerifierAgent` | Golden green; `--verify` unchanged |
| 1.12 | Knowledge packs per pipeline | `prompts/`, `mappings/`, `knowledge/` → `packs/hybris_to_salesforce/` | Golden green; pack path resolved from the pipeline |
| 1.13 | Split `characterize` into mine / plan / emit | `characterize.py` → 3 units | Golden green; mining is source-side, emission target-side |
| 1.14 | Rename `provenance` / `alignment` internals `apex_*` → `target_*` | 2 modules + their tests | Golden green; report wording unchanged |
| 1.15 | **CI purity rule** — the assurance layer may not import an adapter or name a platform | new lint test | Test fails if `triage.py` imports `adapters` |
| 1.16 | Comprehension prompt selected per pipeline | `comprehend.py`, packs | Golden green |

**Exit:** every stage reachable through an adapter; v2 still byte-identical to v1; the
purity rule enforced.
**Estimate for the remainder:** 2–3 weeks.

---

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
