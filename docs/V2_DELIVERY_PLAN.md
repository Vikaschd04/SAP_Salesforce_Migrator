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
| ~~1.17~~ | ✅ **Numeric fidelity** — `ROUNDING_CONTRACT`, `UNSCALED_DIVIDE`, `FLOAT_MONEY` | A1, A2 | The only failure class invisible to *every* other gate. On the reference corpus it moved `PricingService` out of "routine, safe to approve in bulk" — which is the entire point. No generated code changed. |
| ~~1.30~~ | ✅ **Unguarded getter dereference** — `adapters/java_nullability.py` | A5 | The narrower question, answered from the AST rather than by pattern: *is a getter's result dereferenced in a method that never checks it against null?* 3 findings on the corpus, 0 false positives across its four real guards. Two more artifacts left "safe to approve in bulk" as a result. |
| ~~1.18~~ | ✅ **Picklist restriction follows the source** — `dynamic="true"` → unrestricted, static → restricted, wired ingest → schema → emitter | A3 | Scoped from the register as "emit the values"; checking the emitter first showed those were already correct, and the real gap was that `dynamic` was parsed and thrown away. Five fields changed by one line each; no Apex touched. |
| ~~1.20a~~ | ✅ **API names: collisions and length** — symmetric tagging, stable md5, every adjustment recorded | A9, A10 | The engine had the bug the register described: 4 attributes in, 3 fields out, survivor took the wrong type, nothing warned. |
| 1.20b | **Shape ceilings** — 500-field limit, 2-master-detail limit, duplicate class names | A6, A7, F3 | Split from 1.20a: these need a *modelling decision* (which relation demotes to lookup, how the overflow splits), not a naming rule. Detect and explain first. |
| ~~1.31~~ | ✅ **MAPPING.md reports what was emitted** — built from the same schema the metadata comes from | — | Was wrong on every enum (`Text(255)` for a Picklist), every capitalisation, and would have reported any 1.20a-renamed field under a name not in the org. Tests now hold the report and the metadata to one source of truth. |
| ~~1.23a~~ | ✅ **FlexibleSearch analyser** — `adapters/hybris_flexsearch.py`: blocks JOINs, subqueries and leading wildcards by name; derives SOQL mechanically for the single-type case | C1, C2, C4 | All five reference-corpus queries translate correctly, including `pk`→`Id`, `creationtime`→`CreatedDate` and `?param`→`:param`. Golden green with no re-baseline. |
| ~~1.23b~~ | ✅ **The derived SOQL reaches the Builder** | — | All five reference queries arrive pre-translated, with "do not re-translate the original". Blocked queries are named too — silence invites the model to try. A query that *can* be derived should never be generated, and it was being generated. Cost: +876 prompt tokens across the run; generated code byte-identical. |
| ~~1.21a~~ | ✅ **Platform-invoked hooks are never reported as cleanly converted** | B3a | Scoped as savepoints and trigger guards; looking first found something worse and nearer — a `ValidateInterceptor` converted to an orphaned class while the ledger said `converted`. Also made `completeness_ledger()` read-only: it mutated its subject, so asking twice printed the note twice. |
| ~~1.21b~~ | ✅ **The missing invocation is emitted** — `adapters/apex_triggers.py`: trigger + guarded handler per lifecycle hook | B4 | The engine now generates triggers, which it never did. Everything knowable is written (object, events, bulk shape, re-entry guard); the one unknowable thing — the call into a class whose signature a model wrote — is marked TODO, and the ledger says `scaffolded`. |
| ~~1.21c~~ | ✅ **Savepoint mapping** for `@Transactional` — `adapters/java_transactions.py` | B6 | The mapping turned out to be two mappings, and the old `TRANSACTIONAL` rule gave the wrong one for the common case. A method that rolls back purely by *throwing* needs **no** savepoint: an uncaught exception already rolls back the whole Apex request, and a savepoint would spend one of the 150 DML statements for nothing. A method that *catches* and carries on is a partial rollback, which has no other expression in Apex — that one gets the savepoint. `TRANSACTION_SHAPE` decides which, and the Builder is told before it generates. `TRANSACTIONAL` was removed rather than narrowed: its claim that such a method "will commit its earlier DML and then throw" holds only if a caller catches. |
| ~~1.22~~ | ⊘ **Closed, not built** — `QUERY_NO_LIMIT` already covers it | B10 | Checked before building: it fires on exactly the unbounded `getResult()` calls and its hazard already names the 6 MB heap. The residual case is bounded at runtime by a caller-supplied count and has no static signal. A rule that fires almost never is noise with extra steps. |
| ~~1.19~~ | ✅ **Localized attributes reported, and their types fixed** | A4 | Found a quieter bug in the process: `localized:` was never stripped before the type lookup, so every localized attribute became Text — a localized Integer included, which would not compile against generated arithmetic. |
| ~~1.27~~ | ✅ **Cycles are cut where they are named** | F1 | The planner always broke cycles — silently. The domain cut loose is built **without its dependency's signatures**, so the Builder sees less and the difference reaches the output as a weaker artifact with nothing explaining it. Each cut now names both ends, is printed, recorded on the blackboard, and appears in the sign-off as a caveat telling a reviewer which artifact to look at harder. Reported once per cycle, not once per graph walk. |
| ~~1.28~~ | ✅ **Oversized source handled per stage** — `src/oversized.py` | F4 | *Plan premise corrected:* nothing was silently truncated. The class was sent whole, the provider returned 400, and since 400 is not in the transient set it failed on the first request — one wasted call, reporting the provider's raw error instead of "too large for the model". Comprehension now **chunks** at method boundaries and merges, because understandings union. Generation **refuses**, because there is no union of two half-migrations. |
| 1.29 | **Dead-code flagging** — units referenced only by their own tests | F7 | Budget, and a genuinely useful finding for the customer. |
| ~~1.32~~ | ✅ **Relations** — `src/relations.py` | A6 | The engine converted one relation shape and dropped the rest in silence: on the reference corpus, one of three, with both objects on each side converting so every report showed a clean run. Two facts were being thrown away at parse time — `partof`, which is the only thing separating a relationship that cascades from one that does not, and whether the other end is a type the extension declares. A composition now becomes Master-Detail (with `ControlledByParent`, without which the deploy is rejected), many-to-many becomes a junction object, one-to-one becomes a Lookup that says nothing enforces the *one*, and a relation to an out-of-the-box type is reported as the modelling decision it is rather than emitted as a lookup to an object that will not exist. Verified 68/68 in the dev org. |
| ~~1.35~~ | ✅ **A regression net for the second pipeline** — `tests/test_golden_adobe.py`, 30-file baseline | — | Adobe→Hybris had no product-level test: every defect found in 1.33 and 1.34 was found by running it by hand. Six checks, one baseline, and it earned itself back immediately — on its first run it found that `agent-migrate` on a Magento project with the **default config** refused with a Hybris message, because v1 is a dispatch path that cannot express a second pipeline and the engine flag was gating on it. Also caught the ledger naming files by convention (`AddLoyaltyAttributes.java` for a data patch whose content went to items.xml) and a `layer == "Model"` short-circuit reporting a converted Magento service as absorbed into the schema. |
| ~~1.34~~ | ✅ **The last three emitters, and the flag** — `adapters/hybris_hooks.py` | — | Decorators, interceptors and event listeners now emit; `data` never needed an emitter, because a Magento data patch *is* the data model and `build_items_xml` had been writing its EAV attributes onto the platform type all along — reporting it unwritten claimed a loss that had not happened. Also: di.xml wiring now reaches the planner, so `OrderTotalPlugin` (can skip) and `SubtotalPlugin` (cannot) get different, correct answers instead of both defaulting to the safe superset. Cross-domain duplicate targets are folded, which removes the last overwrite. **`implemented = True`** — 9 of 10 units converted, 14 Java files, rung `static`, 0 issues. |
| ~~1.33~~ | ✅ **Close the seam** — the orchestrator routes through the adapters | — | v2 put a source adapter and a target adapter on either side of the run and left everything between them written for Hybris in and Salesforce out. Seven blockers, none in an adapter: preflight measured every codebase for Java; `build_schema` derived SObjects for every run; `write_schema_metadata` wrote `force-app/` regardless of target; the org check queried Salesforce during an Adobe→Hybris run; `emit` was never handed the source model; the target's own `kind` was dropped between planner and emitter; and the two sources disagreed about whether `DataModel.types` holds dicts or objects. **Adobe→Hybris now runs end-to-end and emits a real extension.** Golden green throughout with no re-baseline. Not yet `implemented=True`: three emitters are missing (see 1.34). |
| ~~1.24~~ | ✅ **Frontend gaps** — `adapters/angular_gaps.py` | D1–D4 | The storefront was outside the radar entirely, which scanned `.java` and nothing else, and the generator's system prompt carried one blanket rule: *RxJS Observable/subscribe → reactive property / @wire*. `@wire` cannot be driven by a timer and two wires cannot be combined into a third, so a polling component translated that way compiles, deploys, renders once and never updates. Now decided per construct — cancellation (`switchMap`), teardown (`interval`), composition (`combineLatest`), the async pipe, locale-aware pipes a getter silently renders wrong, selector slots, runtime instantiation, and a lifecycle hook called by hand. 7 findings on the corpus, all real. |
| ~~1.25~~ | ✅ **Integration surface** — `adapters/rest_surface.py`, `impex.upsert_blockers` | E1–E3 | Apex REST allows one method per verb per class and a `urlMapping` of one literal prefix plus one trailing `*`, so a Spring controller can be untranslatable in two ways that look nothing alike: the class does not compile, or it compiles and the endpoint never matches. Both are now decided before generation. Guest-callable callbacks get the Site/guest-profile/CORS prerequisites as a sign-off item, since a signed-in test proves nothing about them. E3 closed from the other end: an object the runbook offers to load that has no key, no field, or no object at all is a cutover blocker, and platform types and out-of-the-box types are named as such rather than asked for. |

**The rule this phase follows:** *a detector that explains beats a rewrite that guesses.*
Several items above deliberately stop at "flag it, name the fix" — because a flagged
hazard is actionable and a confidently wrong rewrite is a liability the customer discovers
in production. Each new detector ships with a `Testing/` fixture that actually trips it.

**Exit:** every row in the register is `covered` or `partial`; no row is an undocumented
gap; the run tells the customer which of these applied to *their* estate.

## Phase 2 — Adobe Commerce source adapter · **source half complete**

Delivers the source half of **Adobe Commerce → SAP Hybris**. To be unambiguous, because
item 2.13 has caused this question once already: there is no `adobe->salesforce` pipeline
and there is not going to be one. The registry holds exactly two entries —
`adobe->hybris` (in build) and `hybris->salesforce` (shipped) — and every hazard, note and
fix Phase 2 produces is framed against Hybris.

| # | Work item | Done when |
|---|---|---|
| ~~2.1~~ | ✅ **Reference Magento project** — `Testing/acme-commerce-magento`, module `Acme_Loyalty` | 19 files. Same loyalty/pricing domain as the Hybris corpus, so the two pipelines are comparable end to end. Carries G1 (EAV data patch), G2 (an `around` plugin that really does skip `$proceed`), G3 (observer mutating the payload), G5 (di.xml preference), G6 (layout XML `move`/`remove`), G7 (store-view config), G9 (cron), plus db_schema and PHPUnit. |
| ~~2.2~~ | ✅ **`detect()`** — signal-scored, vendor/ excluded, `env.php` credentials reported | 100% on the fixture, 0% on the Hybris corpus. Verdict is `not_yet_supported`, not `reject`: recognising a project and being able to migrate it are different statements, and answering "unidentified" to a Magento repo was the wrong one. `require_runnable()` still refuses the run. |
| ~~2.3~~ | ✅ **PHP reader** — `adapters/php_reader.py` on tree-sitter | 11 units from the fixture with namespaces, interfaces, typed signatures, promoted constructor properties and docblocks kept verbatim. An undeclared type stays `""` — unknown routes to must-review, a guess compiles and is wrong. Optional dependency: the reader reports itself unavailable rather than failing the import. |
| ~~2.4~~ | ✅ **`di.xml` reader** — preferences, plugins, constructor arguments | `around` plugins are classified: the fixture's `aroundGetGrandTotal` is flagged `can_skip_original=True`, a passthrough `around` is `False`, and a plugin whose class is missing is `None` — absent evidence is not evidence of absence. |
| ~~2.5~~ | ✅ **`events.xml` reader** | Observers with their event, area and the fact that Magento dispatches them synchronously — Hybris `EventService` is async by default, so the difference travels with the observer. |
| ~~2.6~~ | ✅ **`crontab.xml` reader** → `ir.ScheduledJob` | Group retained, because a Magento job runs once per cluster and a Hybris cronjob needs explicit node affinity. |
| ~~2.7~~ | ✅ **`db_schema.xml` reader** → `ir.DataType` | Column types, nullability and unique constraints. Every table carries `undeclared_note`: these are the *declared* columns only, and presenting them as the whole entity is the lie EAV makes easy. |
| ~~2.8~~ | ✅ **EAV attribute reader** — `adapters/magento_eav.py` | Both fixture attributes read from the AST with types, labels and source models, grouped as an *extension of* `customer` rather than a new type. Every EAV DataType states that the set is open — a third-party module's patches are invisible unless its source is in scope, and admin-UI attributes are in no file at all. An `addAttribute` whose code is built at runtime is recorded as a gap, because "we saw one we could not read" is not "there are none". |
| ~~2.9~~ | ✅ **PHPUnit miner** — `adapters/php_phpunit_mining.py` | All 7 recorded behaviours from the fixture, including the `expectException` rejection and its negative float. Output shape asserted **identical to the Java miner's**, since the neutral layer above both must not care which platform recorded the behaviour — that is what the 1.13 split bought. |
| ~~2.10~~ | ✅ **11 Magento hazard rules** — `adapters/magento_radar.py` | 13 findings on the fixture, every planted construct caught and located. Framed against Hybris: Salesforce fails at *limits*, Hybris fails at *expressiveness*, so every hazard names what Hybris would do instead. |
| ~~2.11~~ | ✅ **Symbol lookup moved behind the seam** — `source.symbols()` / `target.symbols()` | `provenance` and `alignment` shared one Java-shaped regex for source *and* generated code. On PHP it found 1 method in 6 — no error, just under-reporting, in the two modules whose whole output is how much of the source is accounted for. PHP now finds all 6 from the AST; Java/Apex unchanged, golden green with no re-baseline. |
| ~~2.12~~ | ✅ **Type resolution from declarations only** — `adapters/php_types.py` | Four authorities in descending order (declared → docblock → schema → nothing), each resolution recording which answered. Usage is deliberately *not* a source. 51 resolved / 14 unresolved on the fixture, and an unresolved type is a **forced** must-review, not a weight that happens to clear a threshold. |
| ~~2.13~~ | ⊘ **Dropped, deliberately** — was "pair the Adobe source with the Salesforce target as a test fixture" | It would mean building a throwaway `adobe->salesforce` pipeline that will never ship, to test a source adapter already covered by 100+ tests against a real fixture — and it verifies nothing about the Hybris target, which is where the actual risk is (`has_oracle = False`). Replaced by an accounting test: every file `read()` sees lands in `units`, `tests`, `skipped` or `unreadable`, and a file in no bucket is a file lost. |
| ~~2.14~~ | ✅ **`read()` assembles the SourceModel** | 9 units, 1 test suite, 1 script, 0 unreadable; 3 data types (2 declared tables + the `customer` EAV extension); 2 jobs; 7 recorded behaviours; 13 hazards; di.xml and observers carried in `extra`; 5 units with types no declaration resolves. Refuses to run at all without tree-sitter rather than returning what the XML alone yields. |

**Exit:** 100% of the reference Magento project accounted for in the ledger; the fixture
deploy-verifies.

### What a real org found that 600 tests could not

A dry-run deploy of the *Hybris* reference output against a sandbox: **105 of 106
components validated**, and four genuine defects surfaced, none of them visible locally
because every file was well-formed and individually valid.

| Defect | Why nothing local caught it |
|---|---|
| Jest specs deployed as LWC metadata (`LWC1702`) | Valid JS, valid bundle layout. There was no `.forceignore` at all, so **every** migration this tool has produced would have failed both LWC bundles. |
| `actionCalls` interleaved with `decisions` | Well-formed XML, every element individually valid. The Flow type is an `xsd:sequence`: each kind must be consecutive. |
| Flow pointed at `__NOT_MIGRATED__` | A placeholder that read well and named nothing. A Flow whose action Salesforce cannot find is rejected **in full** — the dangling placeholder cost the whole flow, topology and wired steps included. |
| `recordIds` input vs `recordId` variable, and `.outcome` without `storeOutputAutomatically` | Both spelled correctly; it is the *combination* the platform refuses. |

Re-verified against a clean Developer Edition org: **106 of 106 validate, zero failures.**
The single failure in the first run was `Order__c` colliding with pre-existing
`Test_ApexSharing` components in that particular org, not our output.

**Deploy-verify against the CLI's default org** (`sf project deploy start --dry-run
--source-dir force-app`, no `--target-org`). Two of the authorised orgs are *client*
sandboxes whose usernames do not say so — check the instance URL, never the username.
**Efficiency gate:** PHP slimming ≥30%; comprehension on the cheap tier.
**Estimate:** 8–10 weeks.

---

## Phase 3 — SAP Hybris target adapter **and its oracle**

**Decision, 2026-09-03:** a licensed SAP Commerce platform is being procured. Build the
architecture now and verify when it lands — the plan already separates these, so rungs
3.10 (stub classpath, no licence) proceed and 3.11–3.12 wait.

The one reordering that follows: **3.9 moves first, not last.** If emission ships before
sign-off knows the output was never compiled, every item built in between inherits a
claim nobody checked. Getting the rung ladder in early makes the rest honest by
construction rather than by later correction.

### The adapter

| # | Work item | Done when |
|---|---|---|
| ~~3.0~~ | ✅ **`emit()` assembles the extension** — `adapters/hybris_emit.py` | 15 files, 8 Java, **rung `static`, zero issues**. Assembly is where separately-tested emitters have to agree, and it found three defects immediately: a job named one thing in Java and another in ImpEx; an ImpEx `springId` no bean defined (deploys cleanly, fails when the cronjob first runs); and a bean whose `class` attribute was the bean *id*. Added a **cross-artifact check** — every bean class must be an emitted class, every ImpEx `springId` must have a bean — which the Java parser structurally cannot see. |
| ~~3.1~~ | ✅ **Extension scaffolding** — `adapters/hybris_extension.py` | `extensioninfo.xml` with core/commerceservices, `build.xml`, `*-spring.xml`, and `src`/`testsrc` package trees. An extension that is *nearly* the right shape is worse than an obviously incomplete one: the platform's build finds nothing and says little. |
| ~~3.2a~~ | ✅ **Service interface, impl skeleton and Spring wiring** — `adapters/hybris_service.py` | `PricingService` / `DefaultPricingService`, SAP's own convention. Signatures derived from 2.12's resolutions; an undeclared type is emitted as `/* TYPE-UNRESOLVED */ Object` with the names listed, never guessed. PHP docblocks carried verbatim. Unmigrated bodies **throw** rather than returning a default, which would let the extension build and read as "migrated to do nothing". |
| ~~3.2b~~ | ✅ **`plan()`** — `adapters/hybris_plan.py`, every choice recorded with its reason | The `around` plugin that skips `$proceed` routes to a **decorator**, the one that always proceeds to an **interceptor**. Unclassifiable routes to decorator — the safe superset, because a decorator expresses everything an interceptor can *and* skipping, so the failure directions are not symmetric. Magento's `XInterface` + `X` merge into one Hybris service. 11 of 11 units accounted, and the accounting counts *units represented* rather than targets, because a merge makes those differ. |
| ~~3.3~~ | ✅ **DAO with FlexibleSearch** | Query constants, parameterised via `addQueryParameter`, `setCount(1)` on a find-by-unique-key, setter injection. Bounded deliberately: `QUERY_NO_LIMIT` would otherwise fire on our own output, and emitting a DAO that trips our own hazard rules would be an odd thing to do. |
| ~~3.4~~ | ✅ **`*-items.xml` emission** | Declared tables become generated item types with their own deployment table and a typecode above 10000; a Magento EAV entity becomes `autocreate="false" generate="false"` on the type SAP already owns. Emitting the second as the first produces a parallel `Customer` holding half a customer — it deploys perfectly and splits the entity. The "attribute set is open" note reaches the emitted XML. |
| ~~3.5~~ | ✅ **Configuration and seed data** — `adapters/hybris_data.py` | A Magento codebase contains almost no data, and the configuration it *does* hold is business policy: `discountThreshold = 200` **is** the discount rule. Those become `project.properties` plus Spring bean properties, each recording its source. The seed ImpEx carries `INSERT_UPDATE` headers and **no rows** — every row would be invented, and an ImpEx with plausible sample rows is the kind of file somebody loads into an environment assuming it came from somewhere. It names instead what must be exported from the live system. |
| ~~3.6~~ | ✅ **Jobs and triggers** | `AbstractJobPerformable` per job, plus ImpEx creating the ServicelayerJob, CronJob and Trigger. Unix cron is translated to Quartz: a seconds field is added and **day-of-week shifts by one**, because Unix Sunday is 0 and Quartz Sunday is 1 — off by one runs the job on Saturday and nothing fails. An untranslatable schedule emits no trigger at all, because a guessed schedule is worse than an absent one: absent is noticed. Node affinity is named as a deployment decision rather than guessed. |
| ~~3.7~~ | ⊘ **Not applicable to this pair** | The item assumed a source with process definitions, which Hybris has and **Magento does not** — `SourceModel.processes` is empty for every Adobe Commerce project, by construction rather than by omission. Building an emitter with no possible input would produce a file that is always empty and looks like a gap. It returns when a source that *has* processes is paired with this target. |
| ~~3.8~~ | ✅ **The Adobe→Hybris pack** — four prompts, mappings, five knowledge documents | The last blocker to a runnable pipeline. Also neutralised the *shared* placeholder contract: `{java_source}` would have held PHP and `{apex_code}` Java, the same mistake 1.14 fixed in the provenance keys — now `{source_code}` / `{target_code}` / `{target_kind}`, with a test asserting both packs use identical placeholders. |
| ~~3.9~~ | ✅ **The assurance ladder** — `src/assurance.py`, four rungs | `none / static / compiled / replayed`. Sign-off states the rung *and what it does not establish*, in the running target's own name. An unknown rung defaults **down**, so a typo cannot promote a claim, and a legacy boolean result means `compiled` and never `replayed`. Also paid off half of 4.4: `signoff` no longer says "Salesforce". |

### The oracle — three rungs, in order

| # | Rung | Needs | Done when |
|---|---|---|---|
| ~~3.10~~ | ✅ **Parse + resolve** — `adapters/java_static_check.py` | No licence | Every generated file parses (javalang) and every type it names resolves to one of: emitted here, generated by the platform build **from a declared itemtype**, platform API, or an import. A partial pass is not a rung — `check_tree` returns `static` only when the whole output is clean, and `none` otherwise. Caught a real defect in 3.3 the moment it ran. |
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
| ~~4.1a~~ | ✅ **`pipeline.identify()`** — one question every surface asks | Every surface used to ask `preflight.inspect`, which answers *"is this Hybris?"* — so a Magento project was rejected as "not a Hybris project" by a tool holding an adapter that recognised it at 100%. Three genuinely different answers: `unrecognised`, `recognised` (identified, no runnable target — a useful thing to be told), `runnable`. Each option carries `has_oracle`, because "proven to compile" vs "statically checked" belongs beside the choice rather than in the report afterwards. |
| ~~4.2~~ | ✅ **The audit says which migration it was** | Recorded in the contract *and folded into the contract id*, because which pipeline ran is a certified fact rather than metadata. Checkpoints carry it too, and resuming across pipelines warns loudly — the state loads, which is the danger: comprehensions of PHP would be reused as though they described Java. The **engine version is deliberately absent**: v1 and v2 are asserted byte-identical, so recording which ran would state a difference that does not exist — and it broke that test until removed. |
| ~~4.3~~ | ✅ **Per-pipeline forecast profiles** | The Adobe profile is marked `measured=False` and the forecast leads with that — a caveat arriving after the number has been read is a caveat nobody read. The find was not about cost: `Model` means **opposite things** on the two platforms (Hybris = generated from items.xml, Magento = business logic), and sharing one mechanical-layers set understated review effort by **9×** on the same 20 classes. |
| ~~4.4~~ | ✅ **Reports name the pipeline that ran** | Source adapters gained `code_language` to match the targets', and `provenance`, `alignment` and `signoff` derive both. On the shipped pipeline the text renders *identically* — the only golden change was "the original JUnit suite" → "test suite", since PHPUnit is the Adobe equivalent. **The purity ratchet is now empty**: every assurance module is platform-neutral, and adding vocabulary back fails CI. |
| ~~4.5~~ | ✅ **All three surfaces expose the choice** | CLI `--pipeline`, a new `identify` command, and an `h2aMigrator.pipeline` setting. The default everywhere is **detection**, because there is one valid answer for almost every codebase and a source/target dropdown would mostly offer invalid pairs. `identify` returns three exit codes — 0 runnable, 1 unrecognised, 2 recognised-but-not-yet — so a script can act on the difference rather than parsing prose. An explicit choice that contradicts detection is obeyed *and* said out loud, because the likeliest cause is a wrong flag. |
| ~~4.1b~~ | ✅ **The cockpit redesigned around the choice** | Renamed **Portage**, new mark (a crossing, not an "A" for Apex). The landing is now identify-then-choose: the source is inspected before anything is committed, what it *is* is shown, and the destinations on offer come from the engine — each card carrying whether a run to it could be compile-verified or only statically checked. Same tokens and palette throughout. |
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
