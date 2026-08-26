# Multi-Platform Migration — Feasibility & Roadmap

**Version:** 0.1 (proposal) · **Date:** 2026-08-12 · **Status:** For decision
**The ask:** add **Adobe Commerce → SAP Hybris** alongside the existing **SAP Hybris →
Salesforce**, under one roof, with the user choosing which migration to run — without
destabilising what already works.

---

## 1. Verdict

**Feasible, and the architecture is already a third of the way there.** This is a
refactor-and-extend job, not a rewrite. But it is a *real* programme — roughly six to eight
months for one experienced engineer — and there are two things worth deciding before a line
of code is written. Both are in §2, up front, because they change what you should build
rather than just how.

We measured the engine rather than estimating it:

| | Lines | Share | What it means for this ask |
|---|---:|---:|---|
| **Platform-agnostic** | 3,960 | **30%** | Reused as-is. This is the assurance layer — the moat. |
| **Platform-specific** | 6,990 | 54% | Needs splitting into source/target adapters. |
| **Orchestration** | 2,098 | 16% | Mostly generic; small amount of coupling to unpick. |
| **Total engine** | 13,048 | | Plus 4,219 lines of tests across 21 files. |

The 30% is the important number. **Everything that makes this product differentiated is
already platform-neutral** — the rule ledger, review triage, blast radius, checkpoints,
deterministic replay, cost forecasting, the sign-off contract. They operate on *classes,
rules, methods and tests*, not on Apex. They will work on a PHP→Java migration on day one.

The clearest example is line-level provenance. It reads as Salesforce-specific — variables
called `apex`, output keys like `apex_without_origin` — but the algorithm is:

```python
apex_src = artifact.main_class          # "the target text"
apex = _symbols(apex_src)               # "find the methods in it"
by_exact[s["name"]] ...                 # "match them to source methods by name"
```

That is *source text vs target text*. The coupling is **naming, not logic**. A rename and a
PHP-aware symbol regex, and it works unchanged.

---

## 2. Two things to decide before building

### 2.1 You would be building a road *onto* a platform the market is leaving

The premise of the product you already have is that enterprises are migrating **off** SAP
Commerce. SAP has published end-of-maintenance timelines for SAP Commerce Cloud, and that
pressure is precisely why Hybris→Salesforce has an audience. Adobe Commerce → **Hybris**
points at that same platform as a destination.

That may still be exactly right — if this came from a specific client engagement, or from
partners standardising on Hybris, it is a real requirement and the roadmap below delivers
it. But it is worth confirming the demand is a named customer rather than a general
"wouldn't it be nice", because the sequencing in §5 is designed to hedge it:

> **Adobe Commerce → Salesforce falls out almost free.** Once an Adobe Commerce *source*
> adapter exists, it can feed the Salesforce *target* adapter that is already built,
> proven, and has a real compiler as its verifier. That pipeline is likely a larger market
> than Adobe→Hybris, costs one extra phase of nothing, and de-risks everything else.

The roadmap therefore builds the Adobe Commerce source adapter **first** (Phase B, giving
you Adobe→Salesforce), then the Hybris target adapter (Phase C, completing the requested
Adobe→Hybris). Your stated requirement is met at the end of Phase C either way; this order
just means you have a shippable second pipeline four months earlier, and if the Hybris
target is ever deprioritised you have not wasted the work.

### 2.2 The strongest claim this product makes does not transport for free

Today's verification loop is: deploy to a real Salesforce org (validation-only), read the
**actual compiler errors**, fix them, repeat until green. That is what lets the product say
*"proven to run"* rather than *"looks right"*. It works because Salesforce gives us a free,
hosted, authoritative oracle — `sf project deploy --dry-run`.

**SAP Commerce has no equivalent.** To compile generated Java against the Hybris platform
you need the platform itself: a licensed SAP Commerce distribution (multi-GB) present in
whatever runs the migration, plus an `ant`/Gradle build. That is not a technical
impossibility, but it means:

- the customer, not you, must supply a licensed platform for the verification step;
- it is minutes per cycle, not seconds, which changes the economics of the self-heal loop;
- without it, an Adobe→Hybris run is **"generated and statically checked"**, not
  **"verified"** — a materially weaker claim.

This is addressable (Phase D) and there are useful intermediate rungs — compiling against a
stub classpath catches most syntax and signature errors without any licence. But it must be
said out loud now rather than discovered in a client demo, and the sign-off contract must
report the difference honestly, exactly as it already reports "not deploy-verified" today.

---

## 3. The architecture

One concept, introduced once: a **Pipeline** is a *source adapter* + a *target adapter* +
a *knowledge pack*, resolved at run start and carried on the Blackboard.

```
                    ┌──────────────── PIPELINE REGISTRY ────────────────┐
                    │  hybris → salesforce   (today, unchanged)          │
                    │  adobe  → salesforce   (Phase B)                   │
                    │  adobe  → hybris       (Phase C — the ask)         │
                    └───────────────────────────────────────────────────┘
                                          │
   SOURCE ADAPTER                         │                    TARGET ADAPTER
   ──────────────                         ▼                    ──────────────
   detect()      ──┐            ┌──────────────────┐          ┌── plan_targets()
   ingest()        │            │                  │          │   generate()
   schema()        ├──────────▶ │   The IR         │ ────────▶│   validate()
   data()          │            │   (normalised    │          │   emit_metadata()
   jobs()          │            │    migration     │          │   emit_data() / jobs()
   processes()     │            │    model)        │          │   verify()  ← the oracle
   frontend()      │            │                  │          └── layout()
   tests()       ──┘            └──────────────────┘
   hazards()                             │
                                         ▼
                        ┌────────────────────────────────────┐
                        │  THE ASSURANCE LAYER — unchanged   │
                        │  rule ledger · characterization    │
                        │  provenance · alignment · triage   │
                        │  blast · replay · forecast         │
                        │  checkpoints · sign-off            │
                        └────────────────────────────────────┘
```

**The IR is the whole design.** And here is the good news: *the engine already has one, it
is simply undocumented and Java-shaped.* `ingest()` produces dicts that `generate()`
consumes; `schema()` produces a dict that metadata emission consumes. Phase A is about
naming that contract, versioning it, and validating at the seam — which is refactoring with
a safety net, not new invention.

### What already exists as data rather than code

Three things are pluggable today with no work at all, which is a strong signal the seams
are in roughly the right place:

| Today | Becomes |
|---|---|
| `src/prompts/*.txt` (4 templates) | one set per pipeline |
| `mappings/hybris_to_apex.yaml` | `adobe_to_hybris.yaml`, etc. |
| `src/agentic/knowledge/*.md` (8 RAG docs) | a knowledge pack per target platform |

### Module disposition

**Reused untouched (30%)** — `triage`, `rule_ledger`, `blast`, `replay`, `checkpoint`,
`forecast`, `pricing`, `signoff`, `runctx`, `state_ledger`, `incremental`, `router`,
`retriever`, `llm`, `slim`, `textio`, `repo_analyzer`, `domain_classifier`, `comprehend`.

**Reused after a rename (small)** — `provenance`, `alignment` (`apex_*` → `target_*`).

**Split into adapters (54%)** — `preflight`, `ingest`, `schema`, `radar`, `orgfit`,
`generate`, `validate`, `verify`, `metadata_generator`, `impex`, `cronjob`, `processes`,
`flow_generator`, `frontend_ingest`, `generate_lwc`, `validate_lwc`, `parity`, `report`.

**Split three ways** — `characterize`. Its behaviour *mining* is source-specific (JUnit vs
PHPUnit), its *planning* is generic, and its *emission* is target-specific (it writes Apex
test syntax today). That three-way split is a good early test of whether the seam is real.

---

## 4. What Adobe Commerce actually contains, and where it lands in Hybris

The structural match is better than it first appears — Magento's module system and Hybris
extensions are close cousins.

| Adobe Commerce (Magento 2) | SAP Hybris counterpart | Difficulty |
|---|---|---|
| `app/code/Vendor/Module/` | a Hybris extension | Low — direct |
| `etc/module.xml`, `registration.php` | `extensioninfo.xml` | Low |
| `etc/di.xml` (preferences, types) | `*-spring.xml` bean definitions | Low–Medium |
| `Model/`, `Api/`, service contracts | Java service + interface pairs | **Medium — PHP→Java** |
| `Model/ResourceModel/` + Collections | DAO + FlexibleSearch | Medium |
| `db_schema.xml` + **EAV attributes** | `*-items.xml` type system | **High — see below** |
| `Setup/Patch/Data`, fixtures | ImpEx | Medium |
| `etc/crontab.xml` | Spring cron triggers + `AbstractJobPerformable` | Low |
| `etc/events.xml` observers | Hybris event listeners | Low–Medium |
| **Plugins (`before`/`after`/`around`)** | interceptors | **High — see below** |
| `Controller/`, `etc/webapi.xml`, GraphQL | OCC REST controllers | Medium |
| PHTML/Blocks/ViewModels/Knockout UI | Accelerator JSP or Spartacus | High |
| PHPUnit + integration tests | JUnit — *and characterization input* | Medium |

### The three genuinely hard parts

**1. PHP is dynamic; Java is not.** Every generated Java signature needs a type the source
never declared. Modern Magento helps — service contracts and PHP 7/8 type hints cover a
lot — but the residue is real, and a wrong inferred type compiles into a subtly wrong
program. *Mitigation:* infer conservatively, prefer the declared interface where one
exists, and route anything unresolved into the existing **review triage** as must-review
rather than guessing silently. The machinery to surface that already exists.

**2. EAV.** Magento's Entity-Attribute-Value model is runtime-extensible; the Hybris type
system is declarative. Attributes live across `db_schema.xml`, setup patches, and the
database itself, so a purely static read will be incomplete. *Mitigation:* read what is
declarable, and report what is not — this is the exact shape of the business-process gap
already solved: parse it, resolve what you can, and put the remainder in the completeness
ledger as `manual` rather than letting it vanish.

**3. `around` plugins.** A Magento `around` plugin can wrap, alter, or entirely skip the
original method. Hybris interceptors have no equivalent to "skip the original". *Mitigation:*
detect and refuse to fake it — flag every `around` plugin as must-review with the original
code attached. Converting it wrongly is far worse than reporting it.

Each of these three has the same answer, and it is the answer the product already gives
everywhere else: **convert what can be converted, and make the remainder impossible to
miss.**

---

## 5. The roadmap

Five phases. Every one ends with something demonstrable, and none of them may break the
existing pipeline — the enforcement mechanism for that is in §6.

Estimates assume **one experienced engineer already familiar with this codebase**. Phases B
and C can run in parallel with two engineers once A is done, taking the calendar to roughly
four months.

### Phase A — Make the seams explicit · 3–4 weeks · *no new platform*

The whole risk of this programme is concentrated here, and it is the phase most likely to
be skipped under pressure. It adds **zero user-visible features**.

- Extract and version the **IR**: document the dict shapes `ingest`/`schema`/`processes`
  already produce, give them dataclasses, validate at the boundary.
- Introduce the **Pipeline registry** with exactly one entry: `hybris→salesforce`.
- Move `prompts/`, `mappings/`, `knowledge/` into per-pipeline **knowledge packs**.
- Split `characterize` into mine / plan / emit.
- Rename `provenance` and `alignment` internals from `apex_*` to `target_*`.
- Add a **golden-output regression harness**: run the reference corpus, snapshot every
  generated file and report, and fail CI on any unintended diff.

**Exit criteria:** all 384 existing tests green, and the golden harness shows the reference
migration is **byte-identical** to before the refactor.

### Phase B — Adobe Commerce source adapter · 8–10 weeks → *ships Adobe → Salesforce*

Reuses the entire proven Salesforce target, including the deploy oracle. This is where the
source seam gets tested for real, under the protection of the strongest verification you
have.

- `detect()` — Magento markers (`composer.json` type, `registration.php`, `etc/module.xml`)
  so preflight refuses a wrong upload, and reports credentials in `env.php`.
- PHP ingest — a `nikic/php-parser`-equivalent (or `tree-sitter-php`) producing IR units.
- `di.xml` / `events.xml` / `crontab.xml` readers.
- `db_schema.xml` + EAV reader → data-model IR, with the undeclarable residue reported.
- PHPUnit miner for characterization.
- ~10 Magento→Salesforce **hazard rules** for the radar (N+1 collection loads, `ObjectManager`
  direct use, `around` plugins, raw SQL).
- PHP symbol regex for provenance.

**Exit criteria:** an Adobe Commerce reference project migrates to deployable Apex, with the
rule ledger, characterization and provenance populated — and it deploy-verifies against a
real org.

### Phase C — SAP Hybris target adapter · 8–10 weeks → *ships Adobe → Hybris (the ask)*

- Java/Spring generation: services, interfaces, DAOs, `AbstractJobPerformable` jobs.
- `*-items.xml` emission from the data-model IR.
- ImpEx emission from the data IR.
- Spring cron trigger emission.
- Business-process XML emission (the inverse of the `flow_generator` just built).
- Extension scaffolding: `extensioninfo.xml`, `build.xml`, directory layout.
- Hybris-flavoured Critic knowledge pack.
- `validate()` — static Java checks: syntax, imports resolve, FlexibleSearch shape.

**Exit criteria:** Adobe Commerce → a SAP Commerce extension that a Hybris developer
recognises as idiomatic, with the completeness ledger accounting for every input.

### Phase D — A verification oracle for the Hybris target · 4–6 weeks

Turns "generated" into "verified" for the new direction. Three rungs, ship in order:

1. **Syntax + resolution** — parse generated Java, check imports and signatures against a
   stub classpath of Hybris platform APIs. No licence needed. Catches most errors.
2. **Real compile** — `javac`/Gradle against a customer-supplied licensed platform, with the
   same read-real-errors-and-heal loop that Salesforce gets today.
3. **Self-heal** — feed real compiler output back to the Builder, bounded, as now.

**Exit criteria:** the sign-off contract distinguishes *statically checked* from *compiled
against a real platform*, and never conflates them.

### Phase E — Multi-pipeline product surface · 3–4 weeks

- **Auto-detect the source, then offer valid targets.** Better than a dropdown pair: preflight
  already identifies the platform, so the cockpit should say *"This is Adobe Commerce 2.4.6 —
  migrate to Salesforce, or to SAP Hybris?"*
- Per-pipeline forecast constants (PHP→Java has different token economics to Java→Apex).
- Reports, decks and the cockpit made pipeline-aware — no "Apex" in a Hybris run's UI.
- Pipeline recorded in the sign-off contract and in checkpoints.

**Exit criteria:** a user runs both pipelines from the same instance without either knowing
about the other.

### Total

| Phase | Weeks | Cumulative |
|---|---:|---:|
| A — seams | 3–4 | 4 |
| B — Adobe source (→ Salesforce ships) | 8–10 | 14 |
| C — Hybris target (**→ the ask ships**) | 8–10 | 24 |
| D — Hybris verification | 4–6 | 30 |
| E — product surface | 3–4 | 34 |

**≈ 26–34 weeks single-engineer; ≈ 16–20 weeks with two after Phase A.**

---

## 6. How we guarantee the current product is not disturbed

Not a promise — a mechanism. Four of them:

1. **The registry defaults to today's pipeline.** Existing CLI invocations, the extension,
   and every stored run resolve to `hybris→salesforce` with no change in behaviour.
2. **The existing test suite is the contract.** 339 engine + 45 backend tests must stay
   green at every commit. They were written against current behaviour, so they *are* the
   regression detector.
3. **Golden-output harness (Phase A).** Test counts prove functions behave; this proves the
   *product* behaves. The reference migration's every generated file and report is
   snapshotted, and CI fails on an unintended diff. Without this, a refactor of `generate`
   can pass all 384 tests and still quietly change what customers receive.
4. **Adapters are additive.** A new pipeline is new files plus one registry line. No phase
   after A modifies the Salesforce target's logic.

---

## 7. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Phase A gets skipped as "not a feature" | Two platform paths tangled in one codebase; every later change risks both | Treat A as the price of admission. Nothing in B–E starts until the golden harness is green. |
| PHP type inference is wrong but plausible | Silently incorrect Java | Conservative inference; anything unresolved becomes must-review triage. Never guess a type to make it compile. |
| EAV model read is incomplete | Missing attributes in the target type system | Report the undeclarable residue in the completeness ledger, exactly as business processes are handled today. |
| No licensed Hybris platform available | Adobe→Hybris cannot be truly verified | Ship rung 1 (static/stub) first; state the difference in the sign-off contract rather than blurring it. |
| Assurance layer quietly acquires target-specific logic | The moat stops being reusable | A lint/CI rule: nothing under the assurance modules may import an adapter or reference a platform name. |
| Scope creep into the Magento storefront | Phase B doubles | Explicitly out of scope for B. PHTML/Knockout → Spartacus is its own phase, later. |
| **The real-provider run is still outstanding** | Everything above is built on a stack validated only against mock | Do the supervised real-key run **before Phase A starts**. It is the cheapest phase in this document and the only one that can invalidate the others. |

---

## 8. What this also buys, on "industry-ready, reliable, efficient"

The refactor is not only a means to a second pipeline — several of the things it forces are
independently valuable:

- **A typed, validated IR** replaces untyped dicts flowing between eight modules. Every seam
  gains a contract that fails loudly rather than producing a plausible-looking wrong result.
- **The golden-output harness** is the regression test this product does not yet have, and
  wants regardless of multi-platform.
- **A no-platform-leakage rule** on the assurance layer keeps the differentiator honest as
  the codebase grows.
- **Per-pipeline cost models** make the forecast accurate for each language pair instead of
  extrapolating Java→Apex constants.
- **Pipeline-scoped incremental reuse** means a customer evaluating both targets from one
  source pays for the comprehension pass once.

Still open from the existing roadmap, and unaffected by this: Postgres (SQLite is
single-writer and will bind first under concurrent tenants), org/project hierarchy, RBAC
beyond admin/member, per-tenant cost metering, and house-style memory.

---

## 9. Success metrics

| Metric | Target |
|---|---|
| Existing pipeline regression | **Zero** unintended diffs in the golden harness, all phases |
| Rule survival, Adobe→X | ≥ the rate achieved on Hybris→Salesforce on a comparable corpus |
| Adobe→Salesforce deploy verification | Green on the reference corpus without hand-editing |
| Adobe→Hybris static verification | 100% of generated Java parses and resolves against the stub classpath |
| Unaccounted inputs | **Zero**, in every pipeline — the ledger's guarantee is platform-independent |
| Assurance-layer purity | No adapter import or platform literal, enforced in CI |

---

## 10. Recommendation

**Proceed — with Phase A committed in full, and after the real-provider run.**

The three-sentence version for a stakeholder:

> The differentiator — proving a migration preserved behaviour — is already
> platform-neutral, so a second migration path reuses it rather than rebuilding it. The
> work is four months of adapters over one month of refactoring, and it lands a third
> pipeline, Adobe Commerce → Salesforce, on the way to the one you asked for. The one
> caveat worth repeating is that migrating *to* Hybris cannot be verified as strongly as
> migrating to Salesforce, because Salesforce lends us a compiler and SAP does not — and
> the product will say so on the report rather than quietly rounding up.

---

## Appendix — measurement method

Line counts from `wc -l` over `h2a-mvp/src/**/*.py` at commit `6688c40`. Classification by
module against the disposition in §3. Coupling assessed by counting platform terms in code
with docstrings and comments stripped, then reading the residue by hand — which is how the
"provenance is coupled by naming, not logic" finding was established rather than assumed.
