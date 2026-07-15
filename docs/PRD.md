# Product Requirements Document (PRD)

**Product:** SAP Hybris → Salesforce Apex Migrator
**Version:** 0.7.0 · **Status:** Active development, Phase 2 in progress
**Audience:** Product owners, engineering leadership, stakeholders evaluating the product

---

## 1. The problem

Companies running **SAP Hybris** (now "SAP Commerce Cloud") commerce platforms often want to move to **Salesforce** — for cost, ecosystem, or strategic reasons. That migration is normally:

- **Slow.** A mid-size Hybris codebase has hundreds of Java classes, a custom data model (`items.xml`), scheduled jobs, and integrations. Manually rewriting all of it in Apex takes months to years.
- **Expensive.** It requires senior engineers who understand *both* platforms — a rare and costly combination.
- **Risky.** Manual rewrites lose business logic silently. A rule like "orders under $0 must be rejected" can vanish in translation, and nobody notices until it's in production.
- **Opaque.** Traditional migration engagements produce a lot of PowerPoint and very little working code until very late in the project.

## 2. What we build

An **AI-powered migration platform** that takes a Hybris codebase as input and produces a **deployable Salesforce project** as output — Apex classes, data objects, data records, and scheduled jobs — automatically, with every output checked for correctness before it's handed to a human.

It ships two ways:
1. **A VS Code extension** — right-click a Hybris folder, get a Salesforce project back. This is the primary, demo-ready product.
2. **A command-line engine** (`h2a-mvp`) — the same engine, for CI/CD pipelines or engineers who prefer the terminal.

## 3. Why we build it this way

| Design choice | Why it matters |
|---|---|
| **AI does the translation, not a rigid rule-engine** | Business logic in Hybris is expressed in arbitrary Java — a fixed rule-based translator breaks the moment the code doesn't match its assumptions. An LLM (Claude) reads and *understands* the code the way a senior engineer would. |
| **Every output is verified, not just generated** | An AI can hallucinate. So we don't stop at "the AI wrote some Apex" — we deploy it to a real Salesforce org, read the real compiler errors, and have the AI fix them automatically. See [TDD.md](TDD.md) §4 for the self-healing loop. |
| **An agent *team*, not one AI call** | A Planner decides *what* to build (and — importantly — what **not** to build as custom code); Builders write it; a Critic reviews it adversarially before it's accepted. This mirrors how a real engineering team works, and it catches bugs a single-pass AI call would miss. |
| **Three swappable AI providers** | Anthropic Claude for production quality, OpenRouter free models for cheap iteration, and a keyless "mock" mode for testing the pipeline itself with zero cost. |
| **Grounded in your actual data model** | The AI is shown the real Salesforce object/field catalog derived from your `items.xml` before it writes a single line of SOQL — so it can't invent fields that don't exist. |

## 4. Who it's for

| Persona | What they get |
|---|---|
| **Salesforce migration consultancies / SIs** | A tool that turns a multi-month migration project into a multi-day one, with an auditable trail of every AI decision. |
| **Enterprise architects evaluating a Hybris→Salesforce move** | A fast, low-cost way to see *concretely* what a migration would look like — before committing budget to a full engagement. |
| **In-house engineering teams** | A CLI/extension they run directly against their own repository, with full control over which AI provider and model is used, and their code never has to leave their machine (`mock` mode) or their chosen AI vendor. |

## 5. What "done" looks like for one migration run

Point the tool at a Hybris folder. It produces:

- Deployable **Apex classes** (Selectors, Services, Controllers, Scheduled jobs) + matching test classes, following Salesforce's fflib Enterprise Patterns.
- The **Salesforce data model** (custom objects, fields, picklists, relationships) derived from `items.xml`.
- The **actual data** (`.impex` → CSV + an upsert runbook).
- **Scheduled jobs** (Hybris cronjobs → Salesforce `Schedulable` Apex + a ready-to-run scheduling script).
- A **feasibility report** — validation results, confidence score per class, deploy status, code coverage.
- A **migration plan document** — what the AI decided to build as Apex vs. recommend as a native Salesforce feature (e.g., "use Salesforce CPQ instead of hand-rolled discount code"), and every finding the review agent raised.

See [APP_FLOWS.md](APP_FLOWS.md) for the exact step-by-step flow, and [HOW_IT_WORKS.md](HOW_IT_WORKS.md) for a plain-English walkthrough.

## 6. Value proposition — how this helps

| Without this tool | With this tool |
|---|---|
| Months of manual rewriting | A working first-draft migration in minutes to hours |
| Business rules silently lost in translation | A dedicated review step ("Critic") checks that Apex preserves the original logic, and a "parity" score tracks how many business rules are actually asserted in tests |
| "Trust me, it compiles" | The output is dry-run deployed to a real Salesforce org and self-corrected until it actually compiles and passes coverage |
| One-size-fits-all code generation | The AI explicitly recommends *not* writing custom Apex where a native Salesforce feature (like CPQ) is the better fit — reducing future technical debt |
| A black box | A full decision log and confidence score for every generated class, so a human reviewer knows exactly where to focus |

## 7. Non-goals (what this is not, today)

- **Not a one-click, zero-review migration.** The output is a strong first draft that a Salesforce developer should review — see the confidence scores and open questions in every run's `MIGRATION_PLAN.md`.
- **Not a full Hybris platform replica.** Complex Hybris-native concepts (e.g. some commerce workflows) are explicitly flagged for a **native Salesforce product** (CPQ, Flow) rather than blindly re-implemented in Apex.
- **Not yet handling every Hybris surface.** See [ROADMAP.md](ROADMAP.md) for what's covered today (Java classes, data, schema, scheduled jobs) vs. what's planned (business processes, storefront/OCC REST APIs, full CPQ mapping).

## 8. Success metrics

| Metric | How it's measured |
|---|---|
| **Deploy success rate** | % of generated classes that dry-run deploy cleanly to a Salesforce org (`FEASIBILITY_REPORT.md` §2b) |
| **Behavioral parity** | % of the original business rules that are actually asserted by the generated tests (`PARITY.md`) |
| **Cost per class** | LLM token spend per translated class (tracked in the report's token-accounting section) |
| **Time to first draft** | Wall-clock time from "point at a repo" to "deployable output" |
| **Reviewer effort saved** | Proportion of classes that land at High confidence (needing only a skim) vs. Low confidence (needing a rewrite) |

## 9. Future scope

Full detail lives in [ROADMAP.md](ROADMAP.md). In short:
- **Phase 2 (in progress):** more Hybris surfaces — business processes → Flow, storefront APIs → Apex REST, promotions → CPQ.
- **Phase 3:** enterprise platform features — a human review UI, audit trail, private/VPC model deployment, org introspection (reuse a customer's existing Salesforce objects instead of duplicating them).
- **Phase 4:** a learning flywheel (the tool gets better and cheaper with every migration) and a standalone "migration assessment" product as a sales tool.

## 10. How to use it

See [HOW_TO_USE.md](HOW_TO_USE.md) for setup, and [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for a guided walkthrough you can run live for stakeholders.
