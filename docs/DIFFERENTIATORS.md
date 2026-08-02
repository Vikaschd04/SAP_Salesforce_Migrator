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

### 1. Line-level provenance ("migration source maps")
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

### 2. Business-rule coverage as the completeness metric
Today's ledger proves every **class** is accounted for. That's the wrong unit. The real
question is *"did every business rule survive?"*

- Promote the rules the Comprehender already extracts into first-class objects: each rule gets
  an ID, a source location, a target implementation, and a **test that asserts it**.
- Headline metric becomes **"147/152 business rules preserved and asserted; 5 need review"** —
  not "100% of files converted."
- **Why it wins:** it reframes the buying conversation from *coverage* to *correctness*, and
  it's a number a competitor can't fake without doing the same deep work.

### 3. Characterization testing (golden-master parity)
Mine the customer's **existing JUnit tests** for input→output pairs, then replay those exact
cases against the generated Apex in a scratch org.

- **Why it wins:** transforms "the AI thinks it's equivalent" into **"here are 340 recorded
  behaviors from your own test suite; 332 reproduce identically, 8 differ — here they are."**
  That is the artifact that gets a migration signed off. Nobody else will do this because it's
  unglamorous plumbing.
- **Build:** you already run Apex tests during Verify — this extends the harness, not replaces it.

### 4. Hybris-specific anti-pattern radar
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

### 5. Pre-flight target-org fit analysis
Every competitor reads only the **source**. Read the **destination** too: connect the org first
and reconcile *before* generating.

- Name collisions with existing objects/fields · reusable existing schema · custom-object and
  field-count headroom · API version · installed packages that already solve a domain (e.g. CPQ
  present → strengthen that flag).
- **Why it wins:** it's the difference between "here's a package" and "here's a package that
  will actually deploy into *your* org." Prevents the classic day-one deploy failure.

---

## Tier 2 — the experience that makes it usable at scale

### 6. Risk-ranked review triage (beat reviewer fatigue)
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

1. **Business-rule ledger** (#2) — biggest narrative shift, mostly reuses extracted rules.
2. **Line-level provenance** (#1) — unlocks review, audit, and impact analysis together.
3. **Anti-pattern radar** (#4) — fastest credibility win in a demo with a real architect.
4. **Risk-ranked triage** (#6) — what makes it survive a 400-class repo.
5. **Characterization tests** (#3) — the proof artifact that closes enterprise deals.

> **The one-line pitch to aim at:** *"Every other tool converts your code. H2A proves it still
> behaves the same — rule by rule, line by line, against your own org."*
