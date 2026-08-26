# Two Pipelines, One Engine — Roadmap

**Version:** 0.2 (scope locked) · **Date:** 2026-08-12 · **Status:** For build
**Supersedes:** v0.1, which explored a general N×M platform matrix. Scope is now fixed at
exactly two migration paths.

## Scope

The product supports **two** migrations, chosen by the user, sharing one engine and one
architecture:

| # | Pipeline | Status |
|---|---|---|
| 1 | **Adobe Commerce → SAP Hybris** | To build |
| 2 | **SAP Hybris → Salesforce** | Shipped, must not regress |

Nothing else. No Adobe→Salesforce as a product, no third platform. That constraint is what
makes the plan below tractable, and two of its consequences are load-bearing — see §2.

---

## 1. The architecture (unchanged from v0.1, now confirmed)

A **pipeline** is a source adapter + a target adapter + a knowledge pack, resolved at run
start and carried on the Blackboard.

```
  SOURCE ADAPTER                  THE IR                  TARGET ADAPTER
  ──────────────           ────────────────────           ──────────────
  Adobe Commerce  ──┐      one normalised        ┌──▶     SAP Hybris
  SAP Hybris      ──┴──▶   migration model  ─────┤        Salesforce
                           units · schema        └──▶
   detect  ingest          data · jobs                    plan  generate
   schema  data            processes                      validate  emit
   jobs    processes       behaviours                     verify ← the oracle
   tests   hazards         hazards                        layout
                                  │
                                  ▼
        ┌──────────────────────────────────────────────────────────┐
        │  THE ASSURANCE LAYER — unchanged, 30% of the engine       │
        │  rule ledger · characterization · provenance · alignment  │
        │  triage · blast radius · replay · forecast · checkpoints  │
        │  sign-off                                                 │
        └──────────────────────────────────────────────────────────┘
```

Measured at commit `6688c40`: **13,048 engine lines — 30% platform-agnostic (3,960), 54%
platform-specific (6,990), 16% orchestration (2,098)**, plus 4,219 lines of tests.

The 30% is reused untouched across both pipelines. It operates on classes, rules, methods
and tests — not on Apex — so it works on a PHP→Java migration on day one. The IR already
exists implicitly: `ingest()` produces dicts `generate()` consumes. Phase 1 names that
contract rather than inventing one.

---

## 2. What locking the scope to two pipelines changes

Two consequences, both of which change the plan rather than merely narrowing it.

### 2.1 The Hybris verification oracle is no longer optional

In v0.1 an Adobe→Salesforce path existed, which meant Adobe-sourced migrations always had
*a* route to a real compiler. With that removed, **Adobe → Hybris is the only Adobe path,
and Hybris has no free hosted compiler.**

Salesforce lends us `sf project deploy --dry-run`: free, authoritative, seconds. That is
what lets the product say *"proven to run"*. SAP has no equivalent — compiling generated
Java needs a licensed multi-gigabyte SAP Commerce distribution present wherever the
migration runs.

So verification stops being a follow-on phase and becomes **part of the definition of done
for pipeline 1**. Phase 3 delivers the Hybris target adapter *and* its oracle together,
because shipping the first without the second would mean the new pipeline cannot make the
claim the product is sold on.

### 2.2 Adobe → Salesforce survives as a test harness, not a product

It would be wasteful to discard the de-risking just because it is not being sold. Once the
Adobe source adapter exists, pointing it at the *existing* Salesforce target costs
essentially nothing and buys the strongest signal available:

> **If Adobe Commerce → Salesforce produces deployable Apex, the IR captured enough.**
> A real compiler has confirmed the source adapter's output is semantically adequate,
> before it is ever paired with a target we cannot verify as strongly.

This lives in the test suite, is never exposed in the UI, and is never offered to a
customer. It is a fixture — the migration equivalent of a golden-master test.

---

## 3. What "100% working and correct" means here

This is the requirement to pin down precisely, because one reading of it is achievable and
testable, and another is not achievable by any tool — and the difference decides what the
acceptance gates measure.

### Achievable, and enforced as hard gates

Every one of these is binary, machine-checkable, and blocks a release:

| Gate | Meaning | Enforced by |
|---|---|---|
| **100% accounted for** | Every input artefact carries a ledger verdict — converted, flagged, scaffolded, skipped-with-reason, manual, or unreadable. **Zero unaccounted.** | Completeness ledger (exists) |
| **100% compiles** | Every generated artefact passes the target's compiler, or is explicitly reported as failed with the real error attached. **No artefact is shipped in an unknown state.** | Verify loop + Phase 3 oracle |
| **100% traceable** | Every generated method resolves to a source origin or is listed as scaffolding. | Provenance (exists) |
| **100% of rules carry a verdict** | asserted / implemented / at_risk / **dropped** — none unclassified. | Rule ledger (exists) |
| **100% deterministic** | Same input + same recipe ⇒ byte-identical output. | Replay cache + golden harness |
| **Zero silent degradation** | No provider error, parse failure or missing file may produce a plausible-looking empty result. It stops, or it is flagged. | Fatal-error latch (exists), extended per adapter |

That last gate is not theoretical. A rejected API key once degraded every stage to its
deterministic fallback while the run still reported success — the migration claimed the
codebase had no business rules. It is fixed and regression-tested, and the pattern
generalises: **every new adapter must fail loudly or flag, never fall back quietly.**

### Not achievable without a human, and surfaced rather than guessed

Three things cannot be certified by any tool, on any platform:

- **Semantic equivalence** of every business rule. Characterization replay gets close —
  your own tests, run against the new code — but it is evidence, not proof.
- **Inferred PHP types.** Adobe Commerce is dynamically typed; Hybris is not. Some
  signatures must be inferred, and a wrong inference compiles into a subtly wrong program.
- **EAV completeness.** Magento attributes live partly in the database, so a static read
  is necessarily incomplete.

For these the gate is **100% surfaced**: every inference and every gap appears in
must-review triage or the completeness ledger. That target *is* achievable, and it is the
honest form of "100% correct" — the tool guarantees you know where to look, not that no
human need look.

> **The one-line version for a stakeholder:** *100% of your code is accounted for, 100% of
> what we generate compiles, and 100% of the judgement calls are on a list — rather than
> buried.*

---

## 4. Efficiency — measured, and pointed at the right bottleneck

We modelled a real estate with the product's own forecaster rather than guessing:

| Classes | Model calls | Compute cost | Wall clock | **Human review** |
|---:|---:|---:|---:|---:|
| 20 | 55 | $1–$3 | 1–2 min | 3–7 h |
| 200 | 550 | $14–$32 | 6–20 min | 27–67 h |
| 500 | 1,375 | $34–$79 | 14–51 min | 67–167 h |
| **2,000** | **5,500** | **$136–$315** | **58–205 min** | **267–667 h** |

**The finding that should drive the efficiency work:** at enterprise scale the AI costs a
few hundred dollars and the *review* costs seven to seventeen person-weeks. Reviewer
attention is the scarce resource by roughly **40×**. Local compute is not even in the
conversation — the deterministic stages run at ~7.6 ms per class, so a 2,000-class estate
spends about 15 seconds outside the model.

So "efficiency" targets are ordered accordingly:

**First — compress review hours.** This is triage's job and it already exists; what it
needs is precision. The `routine` band must be *genuinely* safe to bulk-approve, because
its value is entirely in being trusted. Target: **≥60% of artefacts land in `routine`, with
zero defects found in that band during acceptance review.** A false negative there is worth
more than any token saving.

**Second — never pay twice.** Incremental reuse exists and is keyed to the codebase. Target:
**a re-run after changing 5% of source costs ≤10% of the original.** This is what makes the
stop-and-edit-source loop affordable.

**Third — spend the model where it earns its keep.** Routing (cheap tier for comprehension
and planning, frontier for generation and review), prompt slimming, and the disk cache all
exist. Target: **≥40% of calls on the cheap tier, ≥30% prompt-token reduction from
slimming, cache hit rate reported per run.**

**Fourth — wall clock.** Dependency wavefronts already parallelise. Target: **a 2,000-class
estate completes in under 3 hours at concurrency 8**, with the spend cap enforced
throughout.

Each of these becomes a **budget checked at every phase gate**, not a task at the end —
efficiency added last is efficiency that gets cut.

---

## 5. The phases

### Phase 0 — Real-provider validation · days, not weeks · **blocking**

The proof stack is fully unit-tested and validated against the `mock` provider, and has
**never completed an end-to-end run against a real model.** The first attempt found a
genuine defect. Everything in this roadmap builds on that stack.

This is the cheapest item in the document and the only one that can invalidate the rest.
It needs a valid provider key, not engineering.

**Exit:** one supervised Hybris→Salesforce run against a real model, walked end to end, with
every assurance panel populated and any findings fixed.

---

### Phase 1 — The seam · 3–4 weeks · *no user-visible features*

Where the whole risk of this programme is concentrated, and the phase most likely to be cut
under pressure.

- Extract and version the **IR**: document the shapes `ingest`/`schema`/`processes` already
  produce, give them dataclasses, validate at the boundary.
- Introduce the **pipeline registry** with one entry: `hybris→salesforce`.
- Move `prompts/` (4 templates), `mappings/` (1 file), `knowledge/` (8 RAG docs) into
  per-pipeline **knowledge packs**.
- Split `characterize` into mine / plan / emit — its mining is source-specific, its planning
  generic, its emission target-specific. A good early test of whether the seam is real.
- Rename `provenance` and `alignment` internals from `apex_*` to `target_*`.
- Build the **golden-output harness**: snapshot every generated file and report from the
  reference migration; CI fails on any unintended diff.

**Correctness gate:** all 384 tests green **and** the reference migration byte-identical to
before the refactor.
**Efficiency gate:** no regression in wall clock or call count on the reference corpus.

---

### Phase 2 — Adobe Commerce source adapter · 8–10 weeks

- `detect()` — Magento markers (`composer.json` type, `registration.php`, `etc/module.xml`),
  so preflight refuses a wrong upload and reports credentials in `env.php`.
- PHP ingest via `tree-sitter-php` (or equivalent) → IR units.
- `di.xml`, `events.xml`, `crontab.xml` readers.
- `db_schema.xml` + EAV reader → data-model IR, with the undeclarable residue reported
  rather than silently missing.
- PHPUnit miner feeding characterization.
- ~10 Magento hazard rules for the radar — N+1 collection loads, direct `ObjectManager` use,
  `around` plugins, raw SQL.
- PHP symbol patterns for provenance.

**Validated through the Salesforce target as a test fixture** (§2.2): if Adobe→Salesforce
deploy-verifies, the IR is adequate.

**Correctness gate:** 100% of a reference Magento project accounted for; the Adobe→Salesforce
fixture deploys clean against a real org.
**Efficiency gate:** PHP prompt slimming ≥30%; comprehension routed to the cheap tier.

---

### Phase 3 — SAP Hybris target adapter **and its oracle** · 10–13 weeks

Delivered together, per §2.1 — the pipeline is not done until it can be verified.

**The adapter:**
- Java/Spring generation: services, interfaces, DAOs, `AbstractJobPerformable` jobs.
- `*-items.xml` emission from the data-model IR.
- ImpEx emission from the data IR.
- Spring cron trigger emission.
- Business-process XML emission — the inverse of the Flow generator already built.
- Extension scaffolding: `extensioninfo.xml`, `build.xml`, directory layout.
- Hybris-flavoured Critic knowledge pack.

**The oracle, three rungs, shipped in order:**
1. **Parse & resolve** — generated Java parsed, imports and signatures checked against a
   stub classpath of Hybris platform APIs. No licence required; catches most errors.
2. **Real compile** — `javac`/Gradle against a customer-supplied licensed platform.
3. **Self-heal** — real compiler output fed back to the Builder, bounded, exactly as the
   Salesforce path does today.

**Correctness gate:** 100% of generated Java parses and resolves at rung 1; the sign-off
contract distinguishes *statically checked* from *compiled against a real platform* and
never conflates them.
**Efficiency gate:** repair loop converges within its bound on the reference corpus.

---

### Phase 4 — The two-pipeline product surface · 2–3 weeks

- **Auto-detect the source, then offer the valid target.** Preflight already identifies the
  platform, so the cockpit should say *"This is Adobe Commerce 2.4.6 — migrate to SAP
  Hybris?"* rather than presenting a dropdown pair, most combinations of which are invalid.
- Per-pipeline forecast constants — PHP→Java has different token economics to Java→Apex, and
  the current constants were measured on the latter.
- Reports, decks and cockpit made pipeline-aware — no "Apex" in a Hybris run's UI.
- Pipeline recorded in checkpoints and in the sign-off contract.

**Correctness gate:** a run of either pipeline is indistinguishable in quality from one on a
single-pipeline build; neither knows about the other.

---

### Phase 5 — Scale hardening · 3–4 weeks

The first four phases are validated on reference corpora of tens of classes. This one proves
the numbers in §4 at enterprise size.

- Build a **2,000-class synthetic estate** for each pipeline and run it end to end.
- Measure against the §4 budgets; fix whatever misses.
- Memory: the Blackboard currently holds a `source_corpus` string duplicating every source
  file, and checkpoints embed it. Fine at 36 KB, worth measuring at 50 MB.
- Concurrency and admission behaviour under multiple simultaneous large runs.
- Confirm the spend cap holds and the forecast range brackets actual spend.

**Correctness gate:** all six §3 gates hold at 2,000-class scale, not just on the samples.
**Efficiency gate:** every §4 budget met, published as the product's stated performance.

---

### Totals

| Phase | Weeks | Cumulative | What exists at the end |
|---|---:|---:|---|
| 0 — real-provider validation | ~1 | 1 | Confidence the foundation is real |
| 1 — the seam | 3–4 | 5 | Same product, safe to extend |
| 2 — Adobe source adapter | 8–10 | 15 | Source proven against a real compiler |
| 3 — Hybris target + oracle | 10–13 | 28 | **Adobe → Hybris, verified** |
| 4 — product surface | 2–3 | 31 | Both pipelines, user chooses |
| 5 — scale hardening | 3–4 | 35 | Numbers that hold at enterprise size |

**≈ 27–35 weeks with one experienced engineer.** Phases 2 and 3 can overlap once the IR is
stable, bringing two engineers to roughly **18–22 weeks**.

---

## 6. How pipeline 2 is protected

Four mechanisms, not a promise:

1. **The registry defaults to today's pipeline.** Existing CLI calls, the extension and every
   stored run resolve to `hybris→salesforce` with unchanged behaviour.
2. **The existing suite is the contract.** 339 engine + 45 backend tests green at every
   commit. They were written against current behaviour, so they *are* the regression detector.
3. **The golden-output harness.** Test counts prove functions behave; this proves the
   *product* behaves. Without it, a refactor of code generation can pass all 384 tests and
   still quietly change what customers receive.
4. **Adapters are additive.** A new pipeline is new files plus one registry line. No phase
   after 1 modifies the Salesforce target's logic.

Plus a standing CI rule: **nothing in the assurance layer may import an adapter or reference
a platform name.** That is what keeps the 30% reusable as the codebase grows.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| **Phase 1 skipped as "not a feature"** | Nothing in 2–5 starts until the golden harness is green. It is the price of admission. |
| **No licensed Hybris platform for verification** | Rung 1 (stub classpath) needs no licence and catches most errors. The contract states which rung ran. Confirm platform availability **before Phase 3**, not during. |
| **PHP type inference wrong but plausible** | Conservative inference; anything unresolved goes to must-review triage. Never guess a type to make it compile. |
| **EAV read incomplete** | Residue reported in the completeness ledger, exactly as business processes are handled today. |
| **`around` plugins** | Detect and refuse to fake them — flag as must-review with the original attached. Converting one wrongly is far worse than reporting it. |
| **Triage precision too low** | The 60%-routine target is a gate, not an aspiration. If reviewers find defects in `routine`, the band is retuned before release — its whole value is being trusted. |
| **Efficiency work deferred to the end** | Budgets are checked at every phase gate. |
| **Real-provider run keeps slipping** | It is Phase 0 and blocking. Everything else is built on it. |

---

## 8. Success metrics

| Metric | Target |
|---|---|
| Pipeline 2 regression | **Zero** unintended diffs in the golden harness, every phase |
| Inputs unaccounted for | **Zero**, both pipelines |
| Generated artefacts in an unknown state | **Zero** — compiles, or reported failed with the real error |
| Rules without a verdict | **Zero** |
| Determinism | Byte-identical output for identical input + recipe |
| Silent degradation incidents | **Zero** — every failure stops or flags |
| Routine-band precision | ≥60% of artefacts routine, **zero** defects found there in acceptance |
| Re-run economy | 5% source change ⇒ ≤10% of original cost |
| Scale | 2,000-class estate < 3 h at concurrency 8, within the forecast range and under the cap |

---

## Appendix — measurement method

Line counts from the engine source at commit `6688c40`. Coupling assessed by counting
platform terms with docstrings and comments stripped, then reading the residue by hand —
which is how "provenance is coupled by naming, not logic" was established rather than
assumed. Stage timings measured on the 20-class reference corpus. Cost, wall-clock and
review-hour figures produced by the product's own `src/forecast.py` at the stated class
counts, using the shipped routing configuration; they are ranges by design, and the review
figures assume one reviewer and no rework.
