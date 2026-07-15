# Product Roadmap — SAP Hybris → Salesforce Apex Migrator

**From a code translator to an autonomous, verifiable migration platform.**

> Interactive version of this roadmap:
> https://claude.ai/code/artifact/cbe5e7ae-2bb4-4891-97ee-3863fb955b66

---

## Status snapshot (v0.7.0)

| Phase | Status |
|---|---|
| **Phase 0 — Prove correctness** | ✅ Core delivered (self-healing deploy loop, confidence scoring, schema reconciliation, parity harness + strengthening) |
| **Phase 1 — Agentic core** | ✅ Core delivered (Blackboard, Planner, Builder+Critic, Verifier, model routing, RAG scaffold) |
| **Phase 2 — Full-surface coverage** | 🔶 In progress — done: ImpEx data migration, deeper `items.xml` metadata, cronjobs → Scheduled Apex. Open: business processes, OCC REST, promotions → CPQ |
| **Phase 3 — Enterprise platform** | ⏳ Not started |
| **Phase 4 — Learning system & GTM** | ⏳ Not started |

---

## North star

An enterprise points the platform at a full Hybris repository and receives a
**deployment-ready, behavior-verified** Salesforce implementation — every
artifact traced to its source, scored for confidence, and gated by real org
deployment before a human ever reviews it.

Every phase moves the product along one axis: from **output you have to trust**
toward **output you can verify**. That axis is the moat.

---

## Baseline this roadmap started from (v0.4.1)

**Shipped & working at the time Phase 0 began**

- 10-stage pipeline: crawl → call-graph → ingest → schema → comprehend →
  generate → validate → repair → metadata → report.
- fflib enterprise patterns (Selectors own SOQL, bulkified stateless Services,
  thin `@RestResource` controllers).
- SObject-schema grounding from `items.xml` (SOQL validated against real fields).
- Structured outputs + prompt caching (Claude path); scoped dependency signatures.
- Three interchangeable providers: `anthropic`, `openrouter`, `mock`.
- Eval harness, incremental delta tracking, call-graph dashboard.

**Known gaps at that time → became this roadmap**

- Validation was a *proxy*, not proof — addressed in Phase 0.
- Schema warnings shipped as caveats rather than resolved fixes — addressed in Phase 0.
- FlexibleSearch → SOQL is best-effort and unverified for result-set equivalence — still true; noted under "hardest bets" below.
- Java classes only — ImpEx, cronjobs done in Phase 2; business processes, OCC still open.
- A linear pipeline, not an agent team; no RAG — addressed in Phase 1 (RAG as a scaffold).

---

## Six capability pillars

### 1. Correctness you can prove *(the trust moat)*
Behavioral-equivalence harness (replay a golden I/O corpus through both systems,
diff outputs); self-healing deploy loop; tests that assert behavior, not just
line coverage; per-artifact confidence scores and risk flags.

### 2. From pipeline to an agent team *(agentic core)*
Planner/Architect agent, focused specialist agents (Selector, Service,
Trigger/Flow, Test, Integration, Data), an adversarial Critic agent, and a
Verifier agent — sharing a blackboard (schema, call graph, decision log) with
real tool use and per-task model routing.

### 3. Beyond Java — the whole suite *(full surface)*
ImpEx → Bulk API + External IDs; cronjobs → Scheduled Apex; business processes →
Flow/Approval; OCC REST → Apex REST/Connect/Experience Cloud; promotions →
CPQ; deep `items.xml` model (relationships, record types, validation & sharing
rules, layouts).

### 4. RAG & target-org awareness *(grounded intelligence)*
RAG over Salesforce docs, the Apex guide, governor limits, and fflib; org
introspection via Metadata/Tooling API to reuse existing objects; migration
memory (vector store of approved pairs as dynamic few-shot); a versioned
pattern library.

### 5. Human-in-the-loop & governance *(enterprise platform)*
Migration workspace with side-by-side Java↔Apex diff + confidence + approval
gates; a feedback flywheel where reviewer edits become few-shot signal; audit
trail (source + prompt + model + reviewer); private deployment (Bedrock / VPC /
self-hosted), PII redaction, SSO/RBAC, data residency.

### 6. The learning system & the wedge *(compounding quality)*
Eval-gated CI on a golden dataset; distillation to a cheap model for the bulk;
a standalone **assessment SKU** (point at a repo → complexity/effort/risk +
"won't auto-migrate" report) as the pre-sales wedge; A/B model & prompt
experiments.

---

## Sequenced launch plan

### Phase 0 — Prove correctness · ✅ core delivered
Turn the demo into something a pilot will trust. Smallest change, largest
credibility payoff.

- [x] **Self-healing deploy loop** — real `sf` compiler errors are fed back into
      the LLM repair loop; offending classes are rewritten on disk and
      re-deployed until green or the repair budget is spent
      (`verify.auto_repair`, `verify.max_deploy_attempts`).
- [x] **Per-artifact confidence scores** — evidence-based (offline validation +
      org-deploy result + healing rounds); surfaced in the feasibility report.
- [x] **On-org coverage** reporting when `verify.run_tests` is enabled, flagged
      against Salesforce's 75% threshold.
- [x] **Auto-resolve schema warnings** — evidence-based reconciliation: fields
      the Hybris source really uses (but `items.xml` never declared) are added to
      the schema and emitted as SObject metadata; references with no source
      evidence stay flagged as likely hallucinations.
- [x] **Deployable SObject metadata** — the pipeline emits custom
      objects/fields from the reconciled schema (previously classes only), so the
      output can actually deploy.
- [x] **Behavioral parity harness** — scores how well each generated test asserts
      the comprehended business rules; emits `PARITY.md`. (Full dual-execution
      equivalence against a live Hybris instance remains a later phase — it needs
      a runnable Hybris + representative data.)
- [x] **Metadata self-healing** — a "missing custom field/object" deploy error
      adds the source-evidenced field/object to the schema + metadata, rather than
      trying to LLM-repair the Apex.
- [x] **Coverage self-healing** — if `run_tests` coverage is below 75%, the
      under-covered classes' tests are strengthened and re-deployed until they
      clear the threshold.
- [x] **Field type inference** — auto-added fields take their type from the Java
      source (`BigDecimal` → Currency, `boolean` → Checkbox, …) instead of
      defaulting to Text.
- [x] **Parity-driven test strengthening** — the parity harness *closes* the
      gap it measures: uncovered business rules are fed back to the model to add
      explicit assertions, before deploy verification (skipped for `mock`).

*Exit:* a Hybris slice deploys green to a scratch org, with measured coverage
and a per-file confidence score — unattended. **Met.**

**Remaining Phase 0 stretch (optional):** golden-set regression gate, turnkey
ephemeral scratch-org lifecycle, migration-readiness summary.

### Phase 1 — Agentic core · ✅ core delivered
Refactor the linear pipeline into an orchestrated agent team with a shared
blackboard, tool use, RAG grounding, and target-org awareness.

- [x] **Blackboard** — shared state (schema, plan, artifacts, decisions log,
      open questions); emits `MIGRATION_PLAN.md`.
- [x] **Planner agent** — decides each target's home: custom **Apex**, a
      **Native** Salesforce product (CPQ / Flow / Approval Process), or **Skip**;
      "what not to migrate" is a first-class output. Deterministic fallback under mock.
- [x] **Builder + Critic loop** — Builder reuses Phase-0 codegen; the Critic
      adversarially reviews each artifact for behavior/security/governor safety
      and feeds ERROR findings into a bounded repair round before accepting.
- [x] **Verifier agent** — the Phase-0 self-healing deploy loop, promoted to an agent.
- [x] **Model routing** — cheap model for comprehension/planning, frontier for
      generation/repair/critique (anthropic; config-gated).
- [x] **RAG grounding — scaffold.** Lexical (TF-IDF) retrieval over a small bundled
      Salesforce/fflib knowledge base (`src/agentic/knowledge/`), injected into the
      Builder + Critic prompts. Interface (`Retriever.retrieve/grounding_block`) is
      ready; production = swap in the full corpus + embeddings (no downstream change).

> **Deferred to Phase 3** (both need external infrastructure — a production doc
> corpus and live customer-org credentials): **production RAG** (full Salesforce
> corpus + semantic embeddings) and **target-org introspection** (Metadata/Tooling
> API to reuse a customer's existing objects). *LLM-native tool calling +
> dependency-aware planning* remains an optional Phase 1 refinement.

*Exit:* the agent team plans (incl. what-not-to-migrate), reviews, and self-heals;
cost-per-class falls via routing. **Met.**

### Phase 2 — Full-surface coverage · 🔶 in progress
Beyond Java — the difference between a slice and a whole-suite migration.
- [x] **ImpEx → Salesforce data migration** *(done)* — parses Hybris `.impex`
      into per-object CSV + an idempotent `sf data upsert` runbook; maps
      `[unique=true]` → an External ID; simple references become
      `Rel__r.Key__c` relationship columns.
- [x] **Deeper `items.xml` metadata** *(done)* — enum types → **picklist** fields
      (value set + default); attribute modifiers → **required** (`optional="false"`),
      **unique**, and default values. (Record types, validation & sharing rules,
      layouts still open.)
- [x] **Cronjobs → Scheduled Apex** *(done)* — a Job class (`extends
      AbstractJobPerformable`) is a new "Job" layer, translated to `Schedulable`
      Apex through the normal agentic pipeline; its Spring XML / ImpEx cron
      trigger is resolved and validated (Quartz cron is shared between Hybris
      and Salesforce) into `CRON_JOBS.md` + `schedule.apex`.
- [ ] Business processes → Flow / Approval Processes
- [ ] OCC REST → Apex REST / Connect / Experience Cloud
- [ ] Promotions & pricing → CPQ *(the Planner already recommends this — the gap
      is automating the CPQ configuration itself, not just the recommendation)*

*Exit:* an end-to-end reference commerce module migrates across code, data,
process, and integration layers.

### Phase 3 — Enterprise platform · not started
Review workspace, approval gates, audit trail, SSO/RBAC, private/VPC models,
CI/CD integration. **Plus carried from Phase 1:** production RAG (full corpus +
embeddings) and target-org introspection (reuse the customer's existing objects).
*Exit:* a regulated customer can run a migration in their own tenancy with full
traceability and human sign-off gates.

### Phase 4 — Learning system & GTM · not started
Eval-gated CI, feedback flywheel, distilled cost tier, assessment SKU, partner
motion.
*Exit:* quality trends up and cost trends down with volume; the assessment
report drives inbound.

---

## The hardest bets — stated honestly

- **Behavioral equivalence is genuinely hard.** Proving Apex behaves like Java
  needs runnable Hybris and representative data. *Bet:* seed from existing
  integration tests; treat equivalence as scored evidence, not a binary claim.
- **Some logic shouldn't be migrated at all.** Cart/checkout/promotions often
  belong in native Salesforce Commerce/CPQ, not hand-written Apex. *Bet:* the
  platform's judgment about *what not to translate* is a first-class output —
  proven working in Phase 1 (the Planner's CPQ recommendation).
- **LLM nondeterminism.** *Bet:* bound every output with deployment + behavioral
  verification — correctness comes from the loop, not the model alone.
- **Enterprise data sensitivity.** Many buyers won't send source to a public
  API. *Bet:* prioritize private deployment (Bedrock/VPC/self-hosted) and PII
  redaction early — this is why Phase 3 pairs target-org introspection with
  enterprise/private-deployment work rather than shipping it standalone.

---

## See also

- [PRD.md](PRD.md) — what we build and why
- [TDD.md](TDD.md) — how it's architected
- [DEMO_SCRIPT.md](DEMO_SCRIPT.md) — a guided walkthrough that shows this roadmap in action
