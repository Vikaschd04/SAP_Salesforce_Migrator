# Stakeholder Demo Script

**Product:** SAP Hybris → Salesforce Apex Migrator
**Version:** 0.8.0
**Duration:** ~20–25 minutes (15 min demo + 5–10 min Q&A)
**Audience:** This is the document to run *from* when presenting to stakeholders.

---

## Before you present — checklist

- [ ] Extension installed and configured (`h2aMigrator.provider` set, key entered) — or terminal open with `h2a-mvp/.venv` activated
- [ ] `Testing/dummy-hybris-store/` open in the VS Code Explorer (the demo sample)
- [ ] `Testing/out-real-store/` available as a pre-generated **real Claude** reference (see §5 — for when you want to show production-quality output without spending live API credit)
- [ ] Decide: live run on `mock` (free, ~30 seconds, fully interactive) vs. walking through the pre-generated real output (zero risk, shows true quality)
- [ ] `docs/HOW_IT_WORKS.md` open in a second tab as a plain-English fallback if a question goes deep

---

## 1. Open — the problem (2 min)

**Say:**
> "Migrating a SAP Hybris commerce platform to Salesforce today means manually rewriting every Java class into Apex by hand. That's months of senior-engineer time, and business rules get lost silently in the rewrite — nobody notices a discount rule vanished until it's in production. We built a tool that does this migration automatically, and — this is the important part — **proves its own work** before handing it to a human."

**Show:** [PRD.md](PRD.md) §1–2 if presenting to a business-heavy audience, or skip straight to the live demo for a technical audience.

## 2. The sample project (2 min)

**Say:**
> "Here's a small but representative Hybris store — deliberately built to exercise everything the tool does: multiple business domains that depend on each other, a real data model with dropdown-style fields and relationships, actual data records, a nightly scheduled job, and one piece of logic — a promotions engine — that's a trap for a naive tool, which we'll come back to."

**Show:** `Testing/dummy-hybris-store/` in the Explorer:
- `CustomerDao.java`, `OrderDao.java`, `DefaultOrderService.java`, `OrderController.java` — a normal three-layer commerce module
- `DefaultPromotionService.java` — discount/pricing logic (watch what the AI decides to do with this)
- `OrderCleanupJob.java` + `store-jobs-spring.xml` — a nightly scheduled job
- `store-items.xml` — the data model (note the `OrderStatus` enum and the `Customer → Order` relationship)
- `store-data.impex` — real seed data

## 3. Run it, live (5–8 min)

**Say:**
> "I'll run the full pipeline now. This uses our free 'mock' mode so it's instant and costs nothing to demo — the AI-writing-code part is what you'll see in the pre-generated real output next. What you're watching *right now* is the real system: the planning, the review, the schema handling, the data and job migration — all of that is 100% real, not simulated."

**Do (extension):** right-click `dummy-hybris-store` → **H2A: Migrate to Apex** (with Provider = `mock`).
**Do (terminal, equivalent):**
```bash
cd h2a-mvp && source .venv/bin/activate
H2A_PROVIDER=mock H2A_INCREMENTAL=false python -m src.main agent-migrate \
  --input ../Testing/dummy-hybris-store --output ../Testing/salesforce_dummy-hybris-store
```

**Narrate as it runs:**
- *"Domains: Order, Promotion, OrderCleanup, Customer — order: Customer, Order, OrderCleanup, Promotion"* — **"It figured out on its own that Order depends on Customer, and the cleanup job depends on Order — and sequenced the work accordingly, without being told."**
- *"Planner"* line — **"This is the moment to watch."**

## 4. The Planner's key decision (3 min) — the headline moment

**Show:** open the freshly-generated `Testing/salesforce_dummy-hybris-store/MIGRATION_PLAN.md`.

**Say, pointing at the Plan table:**
> "Four things got built as Apex — a Selector, a Service, a Controller, a Scheduler. But look at `PromotionService`: the AI recommended **Salesforce CPQ** instead of writing custom Apex, with a stated reason — 'discount/promo-code pricing rules are a textbook fit for Salesforce CPQ.' It didn't just translate blindly. It made the same call a senior Salesforce architect would make: don't hand-roll something Salesforce already does natively. That's the difference between a code translator and a migration platform."

**Then show the Critic review table:**
> "Every accepted class was independently reviewed by a second AI pass, specifically checking whether the original business logic survived translation, whether it's secure, and whether it follows Salesforce best practice. Anything it's not confident about gets flagged here instead of silently shipped."

## 5. Real quality — the proof (4 min)

**Say:**
> "That run used our free mode, which produces placeholder code so it's demo-safe. Here's what the *real* AI writes, from an actual run against Salesforce's Claude model."

**Show:** `Testing/out-real-store/force-app/main/default/classes/OrderSelector.cls`.

**Point out, in the code:**
- `getSObjectFieldList()` / `Security.stripInaccessible(...)` — **"This is Salesforce's own recommended enterprise pattern for field-level security — it wrote that unprompted, because it's one of our house rules."**
- `selectByCodes(Set<String> codes)` — **"Bulk-safe by construction — it takes a set of codes, not one at a time, which is what avoids hitting Salesforce's per-transaction limits."**
- The `Priority__c` field being queried — **"That field wasn't even in the original data model declaration — the AI noticed the Java code used it, verified that with real evidence, and added it to the Salesforce data model automatically."**

**Also show:** `Testing/out-real-store/MIGRATION_PLAN.md` — the same CPQ recommendation and Critic review, from a **real** Claude run — confirming it wasn't a scripted mock-mode-only behavior.

## 6. The proof loop — self-healing (2 min, optional if time-limited)

**Say:**
> "None of this matters if the code doesn't actually work. If you give us a real Salesforce sandbox, we deploy the output there for real. If anything fails to compile, we read the *actual* compiler error and fix it automatically — not by guessing, but by feeding the real error back to the AI. If a missing field is genuinely used in your source code, we add it to the data model. If test coverage is below Salesforce's 75% deploy requirement, we automatically write more tests until it clears the bar."

**Show (no need to run live):** [TDD.md](TDD.md) §4 diagram, or describe verbally.

## 7. Everything else it moved (2 min)

**Say, opening the output folder:**
> "Beyond code: it also produced the actual Salesforce data model" — **show `force-app/main/default/objects/Order__c/`, pointing at `Status__c` being a proper dropdown (picklist) derived from the Hybris enum** — **"real seed data as ready-to-load spreadsheets"** — show `data/Order__c.csv` and `DATA_MIGRATION.md` — **"and the nightly scheduled job, translated with its exact original timing"** — show `CRON_JOBS.md`.

## 8. The close — value & ask (2 min)

**Say:**
> "To summarize: this turns a multi-month, expensive, error-prone manual migration into a process measured in minutes to hours for a first draft — with an AI reviewing its own work, proving deployability against a real org, and explicitly telling you what it *didn't* migrate and why. It's not a black box: every decision is logged, every class has a confidence score, and nothing ships without at least a static or org-verified check."

**The ask:** point at [ROADMAP.md](ROADMAP.md) — what's next (business processes, storefront APIs, promotions→CPQ automation, enterprise review workflow) — and propose a pilot on a real (non-production) slice of their actual Hybris codebase.

---

## Anticipated questions & answers

| Question | Answer |
|---|---|
| "Does this replace our Salesforce developers?" | No — it produces a strong first draft with confidence scoring so reviewers know exactly where to focus. See the "Manual Equivalence Checklist" in every feasibility report. |
| "What if the AI makes something up?" | Every SOQL/field reference is checked against your real data model; anything that doesn't check out is either evidence-verified and added, or flagged — never silently guessed. A second AI (the Critic) independently reviews every class. And ultimately the code is deployed to a real org and must actually compile. |
| "Is our code sent to a third party?" | You choose the provider. `mock` mode sends nothing anywhere. With a real provider, only the code you point it at is sent, to the AI vendor you configure — see [TRD.md](TRD.md) §3 (Security requirements). |
| "How much does this cost to run?" | Every run reports exact token usage and estimated cost in `FEASIBILITY_REPORT.md`. Prompt caching keeps repeat-class costs low. |
| "What's not covered yet?" | Full detail in [ROADMAP.md](ROADMAP.md) — currently: Java classes, the data model, data records, and scheduled jobs. Business processes (Flow/Approval), storefront REST APIs, and full CPQ automation are on the near-term roadmap. |
| "Can we run this on our real codebase today?" | Yes — point the CLI or extension at any Hybris source tree. Start with `mock` mode to sanity-check parsing for free, then a real provider for quality. |

## After the demo

- Leave them with: [HOW_TO_USE.md](HOW_TO_USE.md) (if they want to try it themselves) and [ROADMAP.md](ROADMAP.md) (what's coming).
- If they ask for deep technical detail, follow up with [TDD.md](TDD.md) and [TRD.md](TRD.md).
