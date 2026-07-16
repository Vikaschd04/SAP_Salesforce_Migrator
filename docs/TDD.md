# Technical Design Document (TDD)

**Product:** SAP Hybris → Salesforce Apex Migrator
**Version:** 0.8.0
**Audience:** Engineers who need to understand, extend, or debug the system

This document explains the **architecture** — how the pieces fit together and why they're built this way. For plain-English "what does it do," see [HOW_IT_WORKS.md](HOW_IT_WORKS.md). For requirements, see [PRD.md](PRD.md) / [TRD.md](TRD.md).

---

## 1. System at a glance

```
                         ┌─────────────────────────────┐
                         │   VS Code Extension (UI)    │
                         │   right-click → migrate      │
                         └──────────────┬───────────────┘
                                        │ spawns
                                        ▼
                         ┌─────────────────────────────┐
                         │   Python Engine (h2a-mvp)     │
                         │   same engine, CLI-driven      │
                         └──────────────┬───────────────┘
                                        │
                  ┌─────────────────────┼─────────────────────┐
                  ▼                                             ▼
      ┌───────────────────────┐                    ┌───────────────────────┐
      │   Linear Pipeline       │                    │   Agentic Core          │
      │   (repo-migrate)        │                    │   (agent-migrate)       │
      │   fixed 10-stage flow   │                    │   Planner→Builder→      │
      │                          │                    │   Critic→Verifier over  │
      │                          │                    │   a shared Blackboard   │
      └───────────┬───────────┘                    └───────────┬───────────┘
                  │                                             │
                  └─────────────────────┬─────────────────────┘
                                        ▼
                         ┌─────────────────────────────┐
                         │   Shared stage functions       │
                         │   ingest · schema · generate ·  │
                         │   validate · repair · reconcile │
                         │   metadata · impex · cronjob ·  │
                         │   verify · parity · report      │
                         └──────────────┬───────────────┘
                                        ▼
                         ┌─────────────────────────────┐
                         │   LLM Provider Layer            │
                         │   anthropic | openrouter | mock  │
                         └─────────────────────────────┘
```

Two orchestration modes share the same underlying stage functions — this is a deliberate design choice (§6): new capability is built once, as a stage function, and both the linear and agentic paths get it for free.

## 2. The linear pipeline (`repo-migrate`)

A fixed, deterministic sequence — the original, simpler execution mode. Ten stages, always in this order:

| # | Stage | Module | What it does |
|---|---|---|---|
| 1 | Crawl & schedule | `repo_analyzer.py`, `domain_classifier.py` | Groups classes into "domains" (e.g. all `Order*` classes), detects cross-domain dependencies via whole-word identifier matching, topologically sorts so dependencies are translated first |
| 2 | Call graph | `repo_analyzer.py` | Emits `.call_graph.json` for the dashboard visualizer |
| 3 | Ingest | `ingest.py` | Parses Java (AST via `javalang`) and `items.xml` (item types, enums, relations, modifiers) |
| 4 | Schema | `schema.py` | Derives the target SObject/field catalog — the single source of truth for what exists |
| 5 | Comprehend | `comprehend.py` | One structured LLM call per class → `{purpose, inputs, outputs, business_rules, ...}` |
| 6 | Generate | `generate.py` | LLM translates each class to Apex, using a **cached system prompt** (rules + schema, reused across every class) and a **scoped** set of upstream signatures (only what this class actually depends on) |
| 7 | Validate & repair | `validate.py` | Governor-limit lints + schema-grounding checks; failures go back to the LLM for a targeted fix (bounded retries) |
| 8 | Reconcile + Metadata | `schema.py`, `metadata_generator.py` | Evidence-based schema gap-filling, then emits deployable Custom Object/Field metadata |
| 9 | Data + Jobs | `impex.py`, `cronjob.py` | Translates `.impex` to CSV + upsert runbook; resolves cron triggers to a scheduling runbook |
| 10 | Verify + Report | `verify.py`, `parity.py`, `report.py` | Optional real-org deploy + self-heal; behavioral parity scoring; writes the feasibility report |

## 3. The agentic core (`agent-migrate`) — Phase 1

The linear pipeline runs the same steps for every input. The agentic core adds **judgment**: it can decide *what* to build, review its own output, and revise — the way a small engineering team would, not a single fixed script.

### 3.1 The Blackboard

A shared, mutable object (`agentic/blackboard.py`) that every agent reads from and writes to — schema, migration plan, generated artifacts, a full decision log, and open questions for human review. This is what lets work be *revisited* (Critic finds a problem → sent back to the Builder) instead of only flowing one direction, the way the linear pipeline does.

### 3.2 The agents

| Agent | File | Role |
|---|---|---|
| **Orchestrator** | `agentic/orchestrator.py` | The manager — runs the loop, routes work, calls every stage function in the right order |
| **Planner** | `agentic/planner.py` | Decides each target's home: build as **Apex**, recommend a **Native** Salesforce feature instead (e.g. CPQ for pricing rules), or **Skip**. This is the single highest-value agentic decision — knowing what *not* to hand-translate. Falls back to "everything is Apex" deterministically under the `mock` provider. |
| **Builder** | `agentic/builders.py` | Generates one target's Apex + tests (reuses `generate.py`), then runs objective repair |
| **Critic** | `agentic/critic.py` | Adversarially reviews each artifact: does it preserve the original **behavior**? Is it **secure** (FLS, sharing)? Does it follow **fflib** patterns? Findings marked `ERROR` trigger one bounded repair round before the artifact is accepted or flagged `needs_review` |
| **Verifier** | `agentic/builders.py` (`VerifierAgent`) | Owns the real-org deploy + self-heal loop (§4) |
| **Retriever** | `agentic/retriever.py` | Grounds Builder/Critic prompts in a bundled Salesforce/Apex/fflib knowledge base (§5) |

### 3.3 Model routing

`agentic/router.py` optionally routes different task families to different model tiers — a cheap/fast model for comprehension and planning, a frontier model for generation, repair, and critique — configured in `config.yaml`'s `agentic.routing` block. This is a cost lever: the same quality-critical work uses the best model, while classification-like work doesn't need to.

## 4. The self-healing deploy loop — Phase 0

The part of the system that turns "the AI wrote some Apex" into "the output is proven to work." Lives in `verify.py`'s `deploy_and_heal()`, used by both pipelines.

```
deploy (sf CLI, --dry-run)
   │
   ├─ compiles? ─ no ─▶ is it a MISSING FIELD/OBJECT error?
   │                        ├─ yes, and evidenced in the Hybris source ─▶ add it to the
   │                        │    schema + re-emit metadata (not an Apex rewrite)
   │                        └─ no ─▶ feed the real compiler error to the LLM repair loop,
   │                                  rewrite the class, retry
   │
   └─ compiles ─ yes ─▶ coverage < 75%? ─ yes ─▶ strengthen the under-covered
                                                    class's tests, retry
                          │
                          no ─▶ done — green, with measured coverage
```

Three distinct healing mechanisms, applied automatically and in the right order, bounded by `verify.max_deploy_attempts`:
1. **Metadata healing** — a "no such column" error is evidence-checked against the real source and, if genuine, becomes a schema addition rather than a broken Apex patch.
2. **Apex repair** — remaining compiler errors are fed back into the same LLM repair loop used for offline validation.
3. **Coverage healing** — once it compiles, if org test coverage is below Salesforce's 75% deploy threshold, the under-covered classes' tests are expanded (error paths, bulk scenarios) and re-verified.

This entire loop is optional and gracefully degrades: with no `sf` CLI or no authorized org, it's a clean no-op — the rest of the pipeline is unaffected.

## 5. Grounding — schema, RAG, and reconciliation

Three related mechanisms keep the AI honest about what actually exists:

- **Schema grounding** (`schema.py`) — before generation, the AI is shown the exact SObject/field catalog derived from `items.xml`. After generation, every SOQL/field reference is checked against that catalog.
- **Schema reconciliation** (`schema.reconcile_schema`) — when a reference doesn't match, the system checks whether the underlying name genuinely appears in the Hybris Java source. If yes, it's a real field `items.xml` never declared, and it's added (with an inferred Salesforce type — `BigDecimal`→Currency, `boolean`→Checkbox, etc.). If no, it's flagged as a likely hallucination for human review — never silently guessed.
- **RAG (retrieval-augmented generation)** (`agentic/retriever.py`) — a lightweight, dependency-free (TF-IDF, no vector database) retriever over a small bundled knowledge base (`agentic/knowledge/*.md`: governor limits, fflib patterns, SOQL/security rules, testing conventions). Relevant snippets are injected into Builder/Critic prompts so they cite real facts. This is explicitly a **scaffold** — the interface (`retrieve()` / `grounding_block()`) is designed to swap in a full Salesforce documentation corpus + semantic embeddings later without changing any calling code.

## 6. Design decisions & rationale

| Decision | Rationale |
|---|---|
| **Two orchestration modes sharing one set of stage functions** | The agentic core is strictly additive — it adds planning and review around the same proven generation/validation/repair machinery, rather than duplicating it. A bug fix or new capability (e.g. cronjob support) lands in both paths by construction. |
| **Structured outputs (JSON schema) instead of text markers** | Earlier iterations parsed `===MAIN_CLASS===...===END_MAIN_CLASS===` markers from free-form text — fragile. Structured outputs guarantee parseable JSON from the LLM, eliminating a whole class of parsing bugs. |
| **Prompt caching for the system prompt** | The stable, large prefix (rules + type table + constraints + schema) is identical for every class in a repo, so it's cached and reused at roughly 10% of the token cost on repeat classes. |
| **Scoped dependency signatures, not global** | A class only needs the public signatures of what it actually calls, not every class generated so far. This keeps prompts small and cost-bounded as a repository grows. |
| **Determinism-first for anything that doesn't need judgment** | Parsing Java/XML/ImpEx, deriving the schema, emitting metadata, and cron-expression validation are 100% deterministic Python — no LLM call, no cost, no nondeterminism, fully unit-testable. The LLM is reserved for genuinely judgment-requiring work: understanding code, writing Apex, reviewing quality. |
| **Every provider is swappable, same prompts** | `mock` (free, keyless, deterministic), `openrouter` (cheap/free models for iteration), `anthropic` (production quality) all run the identical pipeline — only `llm.py`'s provider adapter changes. This makes the whole system CI-testable at zero cost. |
| **Graceful degradation everywhere** | No external dependency (an LLM key, the `sf` CLI, a live org) is load-bearing for the core pipeline to run. Each is checked and, if absent, skipped with a clear message — never a crash. |

## 7. Technology stack

| Layer | Technology |
|---|---|
| Engine | Python 3.10+ |
| Java parsing | `javalang` (AST) |
| LLM SDKs | `anthropic` (native), `openai` SDK (OpenRouter, OpenAI-compatible) |
| Config | YAML (`config.yaml`) + `.env` |
| Extension host | TypeScript, VS Code Extension API |
| Salesforce verification | Salesforce CLI (`sf`), invoked as a subprocess |
| Output format | Salesforce DX (SFDX) project layout |

## 8. Key algorithms — quick reference

| Algorithm | Where |
|---|---|
| Whole-word cross-domain dependency detection (comment/string-stripped) | `repo_analyzer._strip_comments_and_strings` |
| Topological domain scheduling | `repo_analyzer.get_translation_schedule` |
| SObject schema derivation (incl. enum→picklist, modifiers→constraints) | `schema.build_schema` |
| Evidence-based schema reconciliation | `schema.reconcile_schema`, `schema._evidenced_in_source` |
| Field-type inference from Java source | `schema.infer_field_type` |
| Governor-limit static validation | `validate.validate_tier1` |
| Self-healing deploy loop | `verify.deploy_and_heal` |
| Behavioral parity scoring (keyword-overlap heuristic) | `parity.build_parity`, `parity._rule_covered` |
| Cron expression validation (Quartz pass-through) | `cronjob.translate_cron` |
| ImpEx reference → SObject relationship mapping | `impex.build_data_plan` |
| Lexical (TF-IDF) retrieval | `agentic.retriever.Retriever` |
| Per-task model routing | `agentic.router.route_model` |

## 9. Where to go next

- **Step-by-step user/system flows:** [APP_FLOWS.md](APP_FLOWS.md)
- **Non-technical explanation:** [HOW_IT_WORKS.md](HOW_IT_WORKS.md)
- **Setup & usage:** [HOW_TO_USE.md](HOW_TO_USE.md)
- **What's next:** [ROADMAP.md](ROADMAP.md)
