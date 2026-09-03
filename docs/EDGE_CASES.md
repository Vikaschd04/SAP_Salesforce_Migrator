# The Edge-Case Register

**Why this file exists.** Any model can turn a Java class into an Apex class. What
separates a tool you bet a migration on from a code translator is the list below: the
several dozen places where a *plausible-looking* conversion is silently wrong, and the
failure surfaces in production six weeks later as a penny of rounding drift per order or
a picklist that rejects one status value in forty.

Every row is a real failure mode, not a category. Each carries a status:

- **covered** — the engine detects or handles it today, with a test
- **partial** — detected but not resolved, or handled for some shapes and not others
- **gap** — known and planned; the owning item is named

A gap is not an embarrassment. An *undocumented* gap is. The purpose of a register is
that the run tells the customer which of these applied to their estate, rather than
producing a green tick that means nothing.

---

## A. Type system and data fidelity — SAP Hybris → Salesforce

| # | Edge case | Why a plausible conversion is wrong | Status |
|---|---|---|---|
| A1 | `BigDecimal.divide()` scale and `RoundingMode` | Java carries explicit scale; Apex `Decimal.divide(b)` without scale uses a different default. A margin calculation converts cleanly, compiles, passes review — and drifts by a cent per line item, every order, forever. This is the single highest-value check in the register because it is invisible to every other gate. | **covered** — 1.17. `ROUNDING_CONTRACT` extracts the scale and mode from the source and reports them once per class; `UNSCALED_DIVIDE` flags division that names no scale |
| A2 | `double` money arithmetic | Hybris code that used `double` for prices carries binary float error. Apex `Decimal` is exact, so the *migrated* code disagrees with the legacy system's recorded output — a characterization `direct` failure that is actually the new code being right. Must be reported as such, not "fixed". | **covered** — 1.17. `FLOAT_MONEY` says so in the hazard: read the difference as the legacy error, not a migration defect |
| A3 | Hybris enums, static vs `dynamic="true"` | Both become a Salesforce picklist, so a converter that stops at "emit the values" looks finished. The difference is whether the target *enforces* the set, and it fails in a different direction each way: a static enum left unrestricted accepts a typo the legacy platform rejected, silently and forever; a dynamic enum made restricted rejects values the legacy system happily stored, surfacing as a failed data load at go-live on records that were always valid. | **covered** — 1.18. *Register corrected:* the values were already emitted; `dynamic` was the attribute being dropped |
| A4 | Localized attributes (`getName(Locale)`) | Hybris localized strings have no Salesforce field equivalent. Flattening to one field silently discards every non-default locale, which for an EU retailer is most of their content. | **covered** — 1.19. Reported per items.xml and per field in MAPPING.md. Also fixed a quieter bug it exposed: the `localized:` prefix was never stripped, so *every* localized attribute became Text — a localized Integer included |
| A5 | Null-returning getters | `getAttribute()` returns null freely in Hybris. Apex arithmetic on a null `Decimal` throws at *runtime*, not compile time, so it passes deploy verification and fails in the org. | **gap** — 1.30. Deliberately *not* folded into 1.17: deciding whether a getter can return null, and whether the caller guards it, needs type resolution across files. A regex would be noisy in both directions, and a noisy rule gets ignored |
| A6 | Many-to-many relations | Become junction objects — but Salesforce allows a maximum of **2 master-detail** relationships per object. A Hybris type with three owning relations cannot be mapped 1:1 and needs an explicit modelling decision recorded, not a silent lookup downgrade. | **gap** — 1.20 |
| A7 | 500-custom-field ceiling | Hybris `Product` in a real estate routinely exceeds Salesforce's per-object field limit. The overflow needs a documented split (related object / JSON blob), decided once and applied consistently. | **gap** — 1.20 |
| A8 | Reserved and standard API names | Hybris attributes named `Status`, `Type`, `Currency`, `Owner`, `Name` collide with Salesforce reserved words or standard fields. | **partial** — validator catches some at deploy; not at plan time |
| A9 | 40-character API name limit | `deliveryModeForAlternativeDeliveryAddress__c` exceeds it. Naive truncation makes two distinct attributes collide into one field — data loss that deploys cleanly. | **covered** — 1.20. Over-length names are shortened with a hash of the full original, so two long names cannot truncate onto each other |
| A10 | Attribute-name collisions across extensions | Two extensions defining the same attribute on related types flatten to one API name. | **covered** — 1.20. *The engine had this bug:* four attributes went in and three fields came out, the survivor keeping the later attribute's type. Colliding names are now tagged **symmetrically**, so neither side wins on iteration order |

## B. Governor limits and execution shape

| # | Edge case | Why a plausible conversion is wrong | Status |
|---|---|---|---|
| B1 | Unbounded FlexibleSearch | No `LIMIT` against a 50,000-row cap. Passes every test with three records. | **covered** — `QUERY_NO_LIMIT` |
| B2 | Query or DML inside a loop | The classic N+1. Detected per character position, so single-line loop bodies are caught too. | **covered** — `SOQL_IN_LOOP`, `DML_IN_LOOP`, `DAO_CALL_IN_LOOP` |
| B3 | Interceptors are per-item; triggers are per-200 | A `ValidateInterceptor` translated literally becomes a per-record SOQL inside a bulk trigger. Correct-looking, and it dies at 201 records. | **covered** (detected) / **partial** (the rewrite to a bulk shape is the Builder's job and is not verified) |
| B3a | **A lifecycle hook loses its *invocation*, not its logic** | The engine had this: the corpus `ValidateInterceptor` enforcing four rules on every Order save was converted into a correct Apex class that **nothing calls**, and the ledger recorded it as `converted`. The rules stopped being enforced while the migration reported success. | **covered** — 1.21. Never plain `converted`. The missing invocation is now *emitted* — a trigger with the correct object, events and re-entry guard — and the row reads `scaffolded`, because the call into the converted class is left for a human rather than invented |
| B4 | Recursive trigger re-entry | Hybris interceptor chains do not re-enter; Apex triggers do. Without a static guard: `maximum trigger depth exceeded`. | **covered** — 1.21b. Every emitted handler carries the guard, and says what it prevents |
| B5 | Cronjobs sized for Batch, not `@future` | A `ServicelayerJob` over 1M records must become Batch Apex (per-chunk limits), not Scheduled or `@future` (per-transaction limits). Choosing wrong is a run that dies at 10,001 records. | **partial** — `CRONJOB_CONCURRENCY` flags it; the sizing decision is not made |
| B6 | Savepoint semantics | `@Transactional` rollback maps to `Database.rollback(savepoint)`, and Salesforce permits far fewer savepoints per transaction than Hybris permits nested transactions. | **covered** (detected via `TRANSACTIONAL`) / **gap** (the mapping) — 1.21 |
| B7 | Static mutable state | Hybris singletons hold state across requests. Apex statics reset per transaction — code that "works" becomes subtly stateless. | **covered** — `STATIC_MUTABLE_STATE` |
| B8 | Threading | `ExecutorService`, `Thread`, `@Async` have no Apex equivalent. | **covered** — `THREADING` |
| B9 | Session-scoped beans | No request/session scope in Apex. | **covered** — `SESSION_SCOPED_BEAN` |
| B10 | 6 MB heap on sync, 12 MB async | A FlexibleSearch returning 20k rows into a list is under the row cap and over the heap cap. | **covered in practice** — `QUERY_NO_LIMIT` fires on exactly these unbounded `getResult()` calls and its hazard already names the heap. *Register corrected:* the residual case is a query bounded at runtime by a caller-supplied count, which has no static signal — a rule for it would fire almost never and add noise. 1.22 is closed rather than built |

## C. Query translation

| # | Edge case | Why a plausible conversion is wrong | Status |
|---|---|---|---|
| C1 | FlexibleSearch JOINs | SOQL has no JOIN. A three-table FS query must become relationship traversal (max 5 levels up, 1 down) or two queries plus an in-memory join. A model asked to "convert this query" will produce SOQL-shaped text that does not compile — or worse, compiles against the wrong relationship. | **covered** — 1.23. Blocked with the reason named; no SOQL is attempted, because an attempt looks like an answer |
| C2 | Leading-wildcard `LIKE '%x%'` | Not indexed in SOQL and disallowed in some contexts; needs SOSL, which has different result semantics. | **covered** — 1.23. Leading wildcard blocked; trailing is fine and passes |
| C3 | `IN` lists over 2,000 ids | FS handles it; SOQL fails. | **partial** — 1.23 names the 2,000-id ceiling in the subquery fix; it cannot be detected statically from the query alone |
| C4 | Arbitrary subqueries | FS allows them anywhere; SOQL semi-joins are one level deep and cannot be nested. | **covered** — 1.23. All blocking reasons are reported at once, so fixing one does not reveal the next |

## D. Frontend — Spartacus/Angular → LWC

| # | Edge case | Why a plausible conversion is wrong | Status |
|---|---|---|---|
| D1 | `[(ngModel)]` two-way binding | No LWC equivalent; needs an explicit change handler, or the field silently never updates. | **partial** — knowledge pack covers the pattern; not verified in output |
| D2 | RxJS operator chains | `switchMap` / `combineLatest` have no `@wire` equivalent — `@wire` is push-based but not composable. A literal translation loses cancellation semantics. | **gap** — 1.24 |
| D3 | Content projection with selectors | `<ng-content select=".x">` → LWC named slots, which do **not** support CSS selectors. | **gap** — 1.24 |
| D4 | CMS-driven dynamic components | Spartacus instantiates components by CMS type at runtime. LWC has no general runtime instantiation. | **gap** — 1.24 |
| D5 | `*ngIf` on a component root | Needs a wrapping `<template>` in LWC; omitted, the directive is silently ignored. | **partial** — pattern in the pack |

## E. Integration and non-code assets

| # | Edge case | Status |
|---|---|---|
| E1 | OCC REST endpoints → `@RestResource`, with 6 MB request / 12 MB response caps and no streaming | **gap** — 1.25 |
| E2 | PSP callbacks need a Site, guest user, and CSP/CORS entries — guest-user permissions fail silently | **gap** — 1.25 |
| E3 | ImpEx volume and `INSERT_UPDATE` ≈ upsert on External Id, which must exist as a field | **covered** (volume) / **gap** (the External Id requirement) |
| E4 | Generated `*Model.java` / `*Data.java` must be skipped, not converted — otherwise most of the run's budget is spent regenerating generated code | **covered** — 1.26. Detection uses machine-written evidence only (a build-owned directory, or a generator's banner); `extends Generated*` is deliberately *not* evidence, because Hybris generates an editable half of that pair |

### Found while building 1.20

`MAPPING.md` derived its field names and types independently of the schema the metadata is
built from, so the report and the output disagreed: it said `fulfilmentState__c ·
Text(255)` where the metadata said `FulfilmentState__c · Picklist`. **Fixed in 1.31** —
both now read the same schema, and tests assert every reported field and type against the
metadata actually emitted. Two sources of truth for one fact is how a report starts
describing a migration that did not happen.

## F. The migration process itself — platform-neutral

These apply to **both** pipelines, which is why they live in the assurance layer.

| # | Edge case | Status |
|---|---|---|
| F1 | Cyclic dependencies between source units — the wavefront planner must break the cycle deliberately and record where | **gap** — 1.27 |
| F2 | A file that parses but has no convertible content (interfaces, `package-info`, annotations) — must be `skipped` with a reason, never `converted` | **covered** — completeness ledger |
| F3 | Duplicate simple class names across extensions colliding on one target name | **gap** — 1.20 |
| F4 | A single class larger than the model's context — must chunk and stitch, or it truncates silently | **gap** — 1.28 |
| F5 | Non-UTF8 or mixed-encoding source | **covered** — `unreadable` outcome, reported not dropped |
| F6 | Resumption after a provider auth failure mid-wavefront | **covered** — checkpoints + `ProviderAuthError` latch |
| F7 | Dead code referenced only by its own tests — converting it burns budget | **gap** — 1.29 |
| F8 | A run that will exceed its budget — must stop at the cap, not after it | **covered** — cost cap checked *before* each call |

## G. Adobe Commerce → SAP Hybris — for Phases 2 and 3

Registered now because they shape the adapter design, not after the adapter is written.

| # | Edge case | Why it is hard |
|---|---|---|
| G1 | **EAV → typed items** | Magento attributes are *runtime rows*; Hybris `items.xml` is *build time*. Attribute sets must be mined from data, not code, and become item types. The single largest structural difference between the platforms. |
| G2 | **`around` plugins that skip `$proceed`** | Magento's `around` interceptor can decline to call the original. Hybris interceptors cannot — this needs a decorator bean, and a converter that maps `around` → interceptor produces code that always calls through. |
| G3 | **Events mutate their payload** | Magento observers are synchronous and can modify the event object. Hybris `EventService` is asynchronous by default — a literal port loses both the ordering and the mutation. |
| G4 | **PHP dynamic typing** | `$product->getData('price')` is `mixed`. Types must be inferred per attribute from the EAV schema, not from the call site. **Covered by 2.12** — resolved only from a declaration (signature, docblock, or schema); anything else forces must-review rather than being guessed. |
| G5 | **`di.xml` preferences** | Global type substitution, closer to bytecode weaving than to a Spring bean override. |
| G6 | **Layout XML** | Blocks are moved and removed by reference at runtime; there is no static equivalent to resolve against. |
| G7 | **Store-view scoping** | Magento's website/store/store-view config cascade does not line up with BaseSite/BaseStore/Catalog. Some values have no Hybris peer at all. |
| G8 | **PHP traits** | Multiple inheritance → Java single inheritance plus composition. |
| G9 | **Cluster-aware cron** | Magento cron on four nodes runs once; Hybris cronjobs need explicit node affinity or they run four times. |
| G10 | **Indexers / `mview`** | Partial-reindex semantics differ from Solr indexing; a literal port re-indexes everything. |

---

## How this register is meant to be used

1. **A gap is scheduled, not hidden.** Every one names its item; the items are in
   `V2_DELIVERY_PLAN.md`.
2. **Detection before rewriting.** Adding a *detector* for an edge case is worth more than
   attempting an automatic fix, because a flagged hazard with a named fix is actionable
   and a wrong automatic rewrite is a liability. Several rows above are deliberately
   "detect and explain" rather than "convert".
3. **Every new detector needs a source fixture** in `Testing/` that actually trips it —
   a rule with no failing example is a rule nobody has tested.
4. **The golden harness stays green.** A detector that changes the reference output
   changes the manifest in the same commit, reviewed as part of it.
