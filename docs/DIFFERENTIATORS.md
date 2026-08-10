# What would make H2A beat every other migration tool

Not a feature list — a set of **specific, defensible bets**. Generic ideas (better prompts,
more models, prettier UI) are table stakes and copyable in a week. These are chosen because
they're hard to copy, they attack the *actual* reason migrations fail, and most are reachable
from data the engine **already computes**.

The thesis: **every competitor sells conversion. Nobody sells _proof_.** A CTO doesn't fear
"will it produce Apex" — they fear "will it silently change how pricing works and we find out
in production." Own *proof* and the category is yours.

---

## Tier 1 — the moat (build these)

### 1. Line-level provenance ("migration source maps") — ✅ **SHIPPED**
Every generated Apex line traceable to the exact Java line(s) that produced it — click Apex
line 42, the Java that caused it highlights, and vice-versa.

- **Why it wins:** the single biggest reviewer objection is *"where did this come from?"*
  File-level mapping is common; **line-level is rare** because it requires capturing the
  mapping at generation time, not reconstructing it after. Once a reviewer can trace any line
  home, trust stops being a leap of faith.
- **Build:** have the Builder emit a `provenance: [{apex_lines:[30,41], java_lines:[42,58], rule:"…"}]`
  array alongside the code (structured-output field). Render as linked gutters in the existing
  Monaco diff.
- **Compounding:** provenance also powers *impact analysis*, *audit*, and *selective re-generation*.

**How it shipped** (`src/provenance.py`, `PROVENANCE.md`): every generated method traced to
the Java that produced it, with exact line ranges on both sides.

> **The build note above turned out to be wrong, and it matters.** Emitting
> `provenance: [{apex_lines, java_lines}]` as a structured-output field does not work —
> models are fluent about structure and unreliable about arithmetic on text they are not
> looking at, so the ranges come back plausible and wrong. A provenance map that is
> confidently wrong is worse than none, because it gets trusted. The mapping is instead
> built by locating *symbols* in both texts deterministically, which models are reliable
> about; the line numbers are then facts. Exact-name matches are labelled a fact,
> normalised matches (a bulkified `placeOrder` → `createOrders`) a strong inference.

The residue is half the value: **Apex with no Java origin** (scaffolding, or invention) and
**Java with no Apex counterpart** (logic that may simply not have been carried over).

### 2. Business-rule coverage as the completeness metric — ✅ **SHIPPED**
Today's ledger proves every **class** is accounted for. That's the wrong unit. The real
question is *"did every business rule survive?"*

- Promote the rules the Comprehender already extracts into first-class objects: each rule gets
  an ID, a source location, a target implementation, and a **test that asserts it**.
- Headline metric becomes **"147/152 business rules preserved and asserted; 5 need review"** —
  not "100% of files converted."
- **Why it wins:** it reframes the buying conversation from *coverage* to *correctness*, and
  it's a number a competitor can't fake without doing the same deep work.

**How it shipped** (`src/rule_ledger.py`, Rules tab, `BUSINESS_RULES.md`): every extracted rule
gets a stable id (`R-49651d37`) and is traced *source class → artifact → test*, then given one
of four verdicts:

| Verdict | Meaning |
|---|---|
| `asserted` | Implemented, and the generated test references the rule's terms |
| `implemented` | In the generated code, but no test evidence |
| `at_risk` | Its target failed to generate |
| `dropped` | **No artifact carries it** — the class was skipped, or the rule was lost |

`dropped` is the row that carries the moat. Everything else reports on work that happened;
this reports on work that *didn't*, and it's the only place a silently-lost rule surfaces.
The UI sorts dropped and at-risk rows to the top and stripes them, so the reviewer meets the
risk before the reassurance.

> **Honest limit:** `asserted` is decided by keyword overlap between the rule text and the
> generated test (`parity._rule_covered`, threshold 0.4). That is real evidence and it is
> reported as such, but it is **not** proof of behavioral equivalence — a test can name the
> right terms and still assert the wrong thing. The report and the UI both say so in those
> words. **#3 (characterization testing) is what upgrades this from evidence to proof**, and
> it is now the highest-value thing left to build, because the ledger has made the gap
> legible and put a number on it.

### 3. Characterization testing (golden-master parity) — ✅ **SHIPPED**
Mine the customer's **existing JUnit tests** for input→output pairs, then replay those exact
cases against the generated Apex in a scratch org.

- **Why it wins:** transforms "the AI thinks it's equivalent" into **"here are 340 recorded
  behaviors from your own test suite; 332 reproduce identically, 8 differ — here they are."**
  That is the artifact that gets a migration signed off. Nobody else will do this because it's
  unglamorous plumbing.
- **Build:** you already run Apex tests during Verify — this extends the harness, not replaces it.

**How it shipped** (`src/characterize.py`, Parity tab, `CHARACTERIZATION.md`): every
`@Test` is mined into a recorded input→output fact and graded by how strong the evidence
actually is.

| Mode | Meaning | Trust |
|---|---|---|
| `direct` | The signature survived; the replay calls the same method with the same recorded values | **Strong** — a failure is a real behavioural difference |
| `adapter` | The migration reshaped the call, so generated bridging code arranges the inputs | Medium — the expected value is still a recorded fact, the plumbing is not |
| `manual` | Mocks, object graphs, or a target that failed to build | None |

> **The finding that shaped the design:** on our own demo, **0 of 18** behaviours were
> `direct`, because the migration deliberately bulkifies —
> `placeOrder(customer, entries)` becomes `createOrders(List<OrderRequest>)` and the old
> method names are simply gone. Deterministic replay alone cannot carry a real migration.
> Bridging took it to 56%.
>
> The constraint that keeps a bridged test *evidence* rather than a second opinion: the
> model arranges and acts, and **never asserts**. It is never sent the expected value and
> its output is never trusted to supply one — the assertion is written by the framework
> from the recorded fact. A bridge containing `System.assert*` is rejected outright.

### 4. Hybris-specific anti-pattern radar — ✅ **SHIPPED**
Generic Apex linting is commoditized. **Hybris→Salesforce failure modes** are not:

| Source pattern | Salesforce hazard |
|---|---|
| FlexibleSearch inside a loop | SOQL-101 governor breach |
| Spring `@Transactional` boundary | no equivalent — silent partial commits |
| Hybris interceptor chains | trigger execution-order + recursion hazards |
| ImpEx volumes | DML row limits / Bulk API required |
| `ServicelayerJob` cron | scheduler concurrency limits |
| Session-scoped beans | Apex is stateless — hidden state loss |

Ship these as **named, explained detections** with a fix. That's earned domain expertise a
generic AI tool can't match, and it's exactly what a Hybris architect will test you on in a demo.

**How it shipped** (`src/radar.py`, Discovery gate, `ANTI_PATTERNS.md`): eleven rules —
query/DML/DAO-call in a loop, unbounded query, `@Transactional`, threads, mutable statics,
interceptors, session-scoped beans, ImpEx volume, cronjob concurrency. Each carries what it
means *on Salesforce* and how to fix it, severity-ranked by consequence rather than by how
odd the Java looks. Ten findings on the reference corpus, two of them critical.

Surfaced at the **Discovery gate**, beside preflight — before a plan is approved and before
anything is generated. That placement is the point: fixing a FlexibleSearch-in-loop in the
Java is one change; fixing the SOQL-in-loop it becomes is two.

> **Precision over recall, deliberately.** A radar that cries wolf gets switched off in a
> week and takes its true findings with it. "In a loop" is decided by tracking brace depth,
> not by looking for a nearby `for`; comments and string literals are stripped first, so a
> Javadoc warning *against* the pattern never fires it; and a query with a `setCount` nearby
> is not reported as unbounded. Nine of the twenty-three tests assert that a rule does *not*
> fire.

### 5. Pre-flight target-org fit analysis — ✅ **SHIPPED**
Every competitor reads only the **source**. Read the **destination** too: connect the org first
and reconcile *before* generating.

- Name collisions with existing objects/fields · reusable existing schema · custom-object and
  field-count headroom · API version · installed packages that already solve a domain (e.g. CPQ
  present → strengthen that flag).
- **Why it wins:** it's the difference between "here's a package" and "here's a package that
  will actually deploy into *your* org." Prevents the classic day-one deploy failure.

**How it shipped** (`src/orgfit.py`, `ORG_FIT.md`): reads the destination org after the
schema is derived and before anything is generated, so a collision costs a rename rather
than a deploy. Four finding kinds — name collision, a standard object that already covers
it, an installed package that already owns the domain (CPQ present turns the Planner's
"consider CPQ" into "you already own this"), and custom-object/field headroom.

> **Via the `sf` CLI, not a browser OAuth flow.** Anyone who can deploy has already
> authorised a CLI org, so this needs no new credentials, no consent screen and stores
> nothing. With no CLI or no authorised org it says so and the migration proceeds
> unchanged — an advisory that blocks a run when it cannot reach an org would be worse
> than no advisory.

Verified against a real org rather than a fixture: it correctly flagged the planned
`Order__c` as duplicating standard `Order`.

---

## Tier 2 — the experience that makes it usable at scale

### 6. Risk-ranked review triage — ✅ **SHIPPED**
The hidden killer of human-in-the-loop is **volume** — nobody reviews 400 classes carefully.

- Score every artifact (complexity × risk × confidence × blast radius) and split into
  **auto-approvable** (DTOs, thin selectors — reviewed in bulk) vs **must-review** (pricing,
  tax, promotions, anything flagged).
- Reviewer sees *"12 files need you; 388 are routine — bulk-approve?"*
- **Why it wins:** it's the difference between HITL that's used and HITL that's switched off on
  day two. This is a *product* insight, not a model insight.

### 7. Semantic alignment view, not text diff
A side-by-side text diff across two different languages is close to useless. Align by **rule**:

> `Java 42-58 · "10% discount over ₹5000"` → `PricingService.cls 30-41` + `Discount__c validation`
> — *asserted by* `PricingServiceTest.testBulkDiscount`

Three columns: **intent · implementation · proof**. This is the review UI the category is missing.

### 8. Blast-radius preview before every change
Before a reviewer approves a rework, show what it breaks: dependent classes, tests to re-run,
schema touched. Derived from the dependency graph you already build.

### 9. Deterministic replay + prompt provenance
Every LLM call is already cached by prompt hash — expose it: **replay any run exactly**, and for
any decision show the prompt, model, and grounding docs that produced it.
- **Why it wins:** in regulated enterprises, *"prove why the AI did that in March"* is a
  procurement requirement. This turns your cache into a compliance feature.

### 10. Cost + duration forecast before you press start
From the scan alone: class count × complexity → estimated tokens, spend, wall-clock, and
reviewer-hours. Enterprises need a number **before** approval, not a surprise bill after.

---

## Tier 3 — compounding advantages

### 11. House-style memory (gets smarter per customer)
Every reviewer correction becomes a few-shot exemplar; ingest the customer's **existing Apex**
to learn their naming, security posture, and patterns. Migration #2 for the same client is
visibly better than #1 — a switching cost no competitor inherits.

### 12. The sign-off contract as a deliverable
Export a signed artifact: who approved which phase, when, with what evidence, plus the rule
coverage and org-verification results. Migrations end in an audit; **make the audit a button.**

### 13. Named checkpoints ("restore to before I approved the plan")
The Blackboard is already one serializable object — snapshot it per phase and let reviewers
branch/compare alternative migration strategies instead of re-running from zero.

---

## What I'd build next, in order

1. ~~**Business-rule ledger** (#2)~~ — ✅ shipped.
2. ~~**Characterization tests** (#3)~~ — ✅ shipped, including the adapter bridge that
   makes it work against bulkified output.
3. ~~**Anti-pattern radar** (#4)~~ — ✅ shipped.
4. ~~**Risk-ranked triage** (#6)~~ — ✅ shipped, on the signal the radar produces.
5. ~~**Line-level provenance** (#1)~~ — ✅ shipped.

> **Tier 1 is complete.** All six items shipped.

> **Also shipped, though not on this list:** a source-side preflight that refuses a
> non-Hybris upload before a run exists and reports credentials found in the archive.
> Note that #5 (*pre-flight target-org fit*) is a different thing — that one inspects the
> destination org so the migration reuses objects the customer already has.

> **The one-line pitch to aim at:** *"Every other tool converts your code. H2A proves it still
> behaves the same — rule by rule, line by line, against your own org."*
