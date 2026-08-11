# Understanding the Codebase — A Teacher's Walkthrough

**Version:** 0.10.0 · **Audience:** anyone who wants to *actually understand* how this engine works — no prior AI-agent background assumed.

This is the "sit down and explain it to me" document. We'll build your mental model from the top down: first the big idea, then the journey one migration takes, then the agents (what they *really* are), how they coordinate, and finally the machinery that turns an "agent" into a real Claude API call.

> **The single most important takeaway, up front:** an "agent" here is **not** a mysterious autonomous being. It is **a plain Python class with a method** that (usually) makes one well-crafted call to Claude and interprets the answer. The intelligence comes from *how the classes are organised and how they hand work to each other* — not from any one magic object. By the end of this doc that sentence will feel obvious.

---

## Part 1 — The big picture in one paragraph

You point the tool at a folder of SAP Hybris code (Java + `items.xml` + ImpEx + Spring cron config). The tool reads and understands that code, decides what each piece *should become* on Salesforce, writes the Salesforce Apex + tests + data model, double-checks its own work, and (optionally) deploys it to a real org to prove it compiles. Out comes a ready-to-review Salesforce project plus a report. That's it. Everything below is just *how* each of those verbs happens.

## Part 2 — The map: where things live

```
h2a-mvp/
├── config.yaml            ← the control panel (which model, which features on/off)
├── src/
│   ├── main.py            ← THE FRONT DOOR: parses the command, calls the right handler
│   ├── llm.py             ← THE PHONE LINE to Claude (+ mock, caching, cost accounting)
│   │
│   │   ─── the "assembly line" stage functions (shared by both modes) ───
│   ├── ingest.py          ← reads & parses the Java / items.xml into Python dicts
│   ├── repo_analyzer.py   ← works out domains + dependency order (what to convert first)
│   ├── comprehend.py      ← asks Claude "what does this class DO?" → a summary
│   ├── schema.py          ← builds the SObject/field catalog; reconciles gaps
│   ├── generate.py        ← turns one target into Apex + a test class
│   ├── validate.py        ← objective checks (governor limits, schema) + repair()
│   ├── metadata_generator.py ← writes the object/field XML files
│   ├── impex.py           ← ImpEx data → CSV + a load runbook
│   ├── cronjob.py         ← Spring cron triggers → Scheduled Apex runbook
│   ├── verify.py          ← deploy to a real org + self-heal (the verification engine)
│   ├── parity.py          ← "did we keep every business rule?" checklist
│   ├── report.py          ← writes FEASIBILITY_REPORT.md
│   │
│   │   ─── before any spend (no model calls at all) ───
│   ├── preflight.py       ← is this even SAP Commerce? leaked credentials?
│   ├── forecast.py        ← what this run will cost, as a range
│   ├── orgfit.py          ← reads the DESTINATION org for collisions
│   ├── radar.py           ← Hybris habits that become Salesforce hazards
│   │
│   │   ─── the proof layer (Part 13) ───
│   ├── rule_ledger.py     ← every rule → asserted / implemented / at_risk / dropped
│   ├── characterize.py    ← replays the customer's JUnit against the Apex
│   ├── provenance.py      ← generated method → its Java origin, by symbol
│   ├── alignment.py       ← rule → implementation → proof, on one row
│   ├── triage.py          ← which artifacts actually need a human
│   ├── blast.py           ← what else is in question if this is reworked
│   ├── signoff.py         ← the audit as a deliverable
│   ├── replay.py          ← every model call, keyed and auditable
│   └── checkpoint.py      ← snapshot before each gate; diff two plans
│   │
│   └── agentic/           ← THE AGENT TEAM (Phase 1) — the smart mode
│       ├── orchestrator.py    ← THE CONDUCTOR: runs the whole agentic show
│       ├── blackboard.py      ← THE SHARED WHITEBOARD everyone reads/writes
│       ├── planner.py         ← Agent 1: decides Convert / Skip (+ native flag)
│       ├── builders.py        ← Agent 2 (Builder) + Agent 4 (Verifier)
│       ├── critic.py          ← Agent 3: adversarial reviewer
│       ├── router.py          ← picks a cheap vs frontier model per task
│       ├── retriever.py       ← RAG: pulls facts from bundled Salesforce notes
│       └── knowledge/*.md     ← those bundled notes (governor limits, fflib, etc.)
```

**A mental shortcut:** everything *outside* `agentic/` is the "hands" — deterministic functions that do one concrete job. Everything *inside* `agentic/` is the "brain" — it decides *when* and *how* to use those hands. The agents don't re-implement code generation; they **call the same `generate.py`, `validate.py`, `verify.py`** that the simple mode uses. (`builders.py` says this in its own docstring: "deliberately thin… reuse the proven Phase-0 stage functions.")

## Part 3 — Two modes, one engine

There are two ways to run a migration, and they share all the "hands":

| Mode | Command | What runs it | Character |
|---|---|---|---|
| **Linear** | `repo-migrate` | `pipeline_driver.py` | A fixed assembly line: stage 1 → 2 → 3 … Always the same order. Cheaper, fewer Claude calls, no judgement. |
| **Agentic** | `agent-migrate` | `agentic/orchestrator.py` | A team of agents around a shared whiteboard. Makes judgement calls (Convert, with a native-product flag where one fits), reviews its own work, can send a piece *back* to be fixed, and pauses at three human review gates. This is the default and the interesting one. |

The VS Code extension's **Engine** setting flips between them. The rest of this guide is about the **agentic** mode, because that's where "agents" live.

## Part 4 — Follow one migration from start to finish

Open [orchestrator.py](../h2a-mvp/src/agentic/orchestrator.py) and read `run_agentic_migration` — it's ~150 lines and it *is* the whole show. Here is that function narrated in plain English. (The orchestrator is a **function**, not an agent — it's the conductor waving the baton; the agents are the musicians.)

**Step 0 — Set up the whiteboard.**
```python
bb = Blackboard(input_dir=input_dir, output_dir=output_dir, offline=offline)
```
`bb` (the Blackboard) is a single object that will hold *everything* for this run — the schema, the plan, every generated file, a decisions log. Every agent gets handed `bb`. Remember this object; it's the heart of the coordination story (Part 6).

**Step 1 — Analyse the repo.** `get_translation_schedule` + `build_dependency_graph` group the classes into **domains** (e.g. "Order", "Promotion") and figure out a safe **order** — if `OrderCleanup` depends on `Order`, then `Order` is converted first. This is plain graph code, no AI.

**Step 2 — Ingest.** `ingest()` parses the Java and `items.xml` into Python dictionaries and stores them on the whiteboard (`bb.all_classes`, `bb.item_types`, …). `build_schema()` turns the data model into the SObject/field catalog (`bb.schema`).

**Step 3 — Comprehend (first AI step).** For each class:
```python
model = route_model(config, f"comprehend_{cls['class_name']}")
bb.comprehensions[cls["class_name"]] = comprehend_class(cls, offline=offline, model=model)
```
This asks Claude, *"What does this class do — its purpose, its queries, its business rules?"* and stores the answer. Cheap, classification-ish work → the **router** (Part 8) can send it to a cheaper model.

**Step 4 — Plan.** `PlannerAgent().run(bb)` — Agent 1 decides, for each target, **Convert** or **Skip**, and records a `native_recommendation` where a Salesforce product (e.g. CPQ) would be a better home. A native fit never suppresses the conversion; it becomes a review flag on code that was built anyway. Writes its decisions onto `bb.plan`. (Detail in Part 5.)

**Step 5 — Build + Critic loop.** This is the core coordination. For each domain, in dependency order, for each thing to build:
```python
art = builder.build(item, bb, scoped, mappings, max_repair, retriever=retriever)   # Agent 2 writes Apex
findings = critic.review(art, bb.schema, ...)                                        # Agent 3 reviews it
if any ERROR in findings:
    builder.apply_critic_repair(...)      # send it BACK to be fixed
    findings = critic.review(...)         # review the fix
art.status = "accepted" if no ERRORs else "needs_review"
bb.artifacts.append(art)
registry.register(domain, art.target_name, builder.signatures(art))   # remember its method signatures
```
Notice the shape: **build → review → maybe send back → re-review.** That "send it back" is the thing a straight assembly line *cannot* do. (Detail in Part 5.)

**Step 6 — Reconcile schema.** After building, `reconcile_schema` looks at fields the generated Apex referenced that *aren't* in `items.xml`. If the field is genuinely used in the original Java (evidence!), it's added — e.g. the `Priority__c` field in the demo. Never guessed.

**Step 7 — Write everything.** `write_outputs` + `write_schema_metadata` write the `.cls` files and object/field XML. Then `impex.py` writes CSV data, `cronjob.py` writes the schedule runbook.

**Step 8 — Parity strengthening.** `close_parity_gaps` adds test assertions for any business rule the tests don't yet check (real provider only).

**Step 9 — Verify + self-heal (optional).** If verify is on, `VerifierAgent().run(bb, config)` — Agent 4 — deploys to a real org and heals real compiler errors. (Detail in Part 5.)

**Step 10 — Reports.** `generate_report` writes `FEASIBILITY_REPORT.md` (per-class confidence, cost), and `_write_plan_doc` writes `MIGRATION_PLAN.md` (the plan + Critic findings + the full decisions log). Done.

---

## Part 5 — The four agents, for real

Here's the honest answer to *"are agents just some piece of code?"* — **yes.** Look at the actual shape of one:

```python
class PlannerAgent:
    name = "Planner"
    def run(self, bb) -> None:
        ...
```

That's an agent. A class, a `name`, and a method that takes the Blackboard. What makes it "intelligent" is that *inside* that method it (a) does some deterministic prep, (b) writes a careful prompt, (c) calls Claude, and (d) records structured decisions back onto the whiteboard. There is no hidden runtime, no daemon, no autonomy. **An agent = a role + a prompt + a place to write the result.**

Let's meet the four.

### Agent 1 — The Planner ([planner.py](../h2a-mvp/src/agentic/planner.py))
**Job:** decide each target's *home*: `Apex`, `Native`, or `Skip`.

It works in two passes — and this two-pass design is a pattern worth internalising:
1. **Deterministic pass:** `plan_targets()` derives the *structural* targets (an `OrderDao` → an `OrderSelector`). This is fixed code so target names are stable and testable.
2. **Judgement pass:** it hands Claude the list of targets plus their business rules and asks it to label each `Apex` / `Native` / `Skip`, using a **structured-output schema** (`PLANNER_SCHEMA`) so the answer comes back as guaranteed-parseable JSON, not prose:
```python
result = call_structured("plan_repo", prompt, PLANNER_SCHEMA, ...)
decisions = {d["target_name"]: d for d in result["parsed"]["decisions"]}
```
This is why, in the demo, the promotion logic comes back as **Convert + "consider Salesforce CPQ"**: the Planner recognised "this is pricing, Salesforce has a product for that" — and then converted it anyway.

**The policy is convert everything.** An earlier version let the Planner mark a target `Native` and
skip it, which meant a native-product *recommendation* silently deleted working business logic. It
now always builds, and records the recommendation as a `native_recommendation` review flag on the
generated artifact. Whether to adopt CPQ instead is a decision for the customer's architect, taken
with the converted code in hand rather than instead of it. `Skip` survives only for provably dead
code, framework glue and pure DTOs, and it must carry a reason.

**Safety net:** on `mock`/offline (no key), it skips the LLM pass and defaults everything to Convert — so the pipeline still runs, deterministically, for free.

### Agent 2 — The Builder ([builders.py](../h2a-mvp/src/agentic/builders.py))
**Job:** turn one planned target into an Apex class + a test class.
It's deliberately thin — it calls the shared `generate_apex()` and then repairs objective problems:
```python
gen = generate_apex(target, bb.comprehensions, scoped_sigs, schema=bb.schema, grounding=grounding)
...
self._repair_objective(art, bb.schema, max_repair, ...)   # fix governor/schema issues, bounded loop
```
Two subtle, important things it receives:
- **`scoped_sigs`** — the *method signatures of the domains this one depends on*, from the `SignatureRegistry`. So when the Builder writes `OrderService`, it knows the real methods on `OrderSelector` and calls them correctly instead of inventing them.
- **`grounding`** — relevant facts retrieved from the bundled Salesforce docs (Part 9), injected into the prompt so it cites real governor limits/patterns.
It also has `apply_critic_repair()` — the entry point for "the Critic found a real bug, rewrite the class."

### Agent 3 — The Critic ([critic.py](../h2a-mvp/src/agentic/critic.py))
**Job:** adversarially review each built artifact for what a compiler can't see — did it **preserve the original behaviour**, is it **secure** (field-level security, `with sharing`), is it **bulk-safe**?
It reviews in two layers:
1. **Objective floor (always runs, even on mock):** `validate_all()` — governor limits + schema grounding. A real gate with zero cost.
2. **Adversarial LLM review (real provider only):** it sends Claude the original Java, the business rules, the generated Apex, and the schema, and asks for structured `findings` with a `severity` of `ERROR` or `WARNING`.
The orchestrator treats an `ERROR` as "send it back to the Builder"; `WARNING`s are recorded. This is the demo's "the zero-total rule got dropped → blocked" moment — a second AI catching what the first one missed.

### Agent 4 — The Verifier ([builders.py](../h2a-mvp/src/agentic/builders.py), `VerifierAgent`)
**Job:** own the Salesforce org — deploy the output and heal real errors. It's a thin wrapper over `deploy_and_heal()` in [verify.py](../h2a-mvp/src/verify.py). It runs a **validate-only** deploy (nothing is written to the org), reads the *actual* compiler output, and loops: metadata-heal (add a missing evidenced field), code-heal (feed the real error back to Claude to rewrite), coverage-heal (write more tests until ≥75%). It stops when the org says "green" or flags what it couldn't fix.

> **See the pattern across all four?** Prep deterministically → craft a prompt → call Claude (via `call_structured`/`generate_apex`) → write a structured result to the Blackboard. Same skeleton, different role. That's *all* an agent is.

---

## Part 6 — How they coordinate: the Blackboard

This is the concept that ties the team together, and it's simpler than "agents messaging each other."

There is **no direct agent-to-agent communication.** The agents never call each other. Instead they all share one object — the **Blackboard** ([blackboard.py](../h2a-mvp/src/agentic/blackboard.py)) — and coordinate by reading and writing it. Think of a real whiteboard in a meeting room: the planner writes the plan on it, the builder reads the plan and writes the code up, the critic reads the code and writes notes, everyone can see everything.

The Blackboard is just a `@dataclass` holding fields like:
```python
schema          # the SObject catalog
comprehensions  # class_name -> "what it does"
plan            # [PlanItem]  ← Planner writes, Builder reads
artifacts       # [Artifact]  ← Builder writes, Critic annotates
decisions       # an append-only audit log  ← everyone writes
open_questions  # things an agent couldn't resolve  ← surfaced to the human
```
Two methods make the audit trail:
```python
bb.record("Planner", "planned", "12 targets → 10 Apex, 1 native, 1 skip")  # → decisions log
bb.ask("Critic", "OrderService: zero-total rule dropped")                   # → open_questions
```
Every `record()` call is why `MIGRATION_PLAN.md` can show a full decision log, and every `ask()` is why the report can list "here's what a human should look at." **Coordination = shared memory + an ordered loop in the orchestrator**, not a swarm of things talking to each other. That's what makes it debuggable: to see what happened, you read one object.

Why a Blackboard instead of just passing arguments down a chain of functions? Because a chain only flows one way. The Blackboard lets work be **revisited** — Critic → back to Builder → back to Critic — which is exactly the capability that separates the agentic mode from the linear assembly line. (The blackboard's own docstring makes this point.)

---

## Part 7 — What is *not* an agent (so the word stays meaningful)

It's easy to over-use "agent." In this codebase, these are deliberately **not** agents — they're plain deterministic functions, and that's a feature (fast, free, testable, same answer every time):

- `ingest`, `build_dependency_graph`, `build_schema`, `validate_all`, `write_outputs`, `impex`, `cronjob`, `report`.

The rule of thumb the project follows: **use an agent (an LLM call) only where genuine judgement is needed** — understanding code, deciding its home, writing it, reviewing it, healing it. Everything mechanical stays ordinary software. That's the "AI on only 4 of 10 stages" point from the deck, and it's a cost and reliability decision, not a limitation.

---

## Part 8 — From "agent" to a real Claude call: the LLM layer

Every agent's intelligence ultimately funnels through one file: [llm.py](../h2a-mvp/src/llm.py). Understanding this removes the last bit of mystery.

**The public doors** are `call_llm(...)` and `call_structured(...)`. An agent calls one of these with a `stage` name, a `prompt`, and (optionally) a JSON `schema`. Inside, `call_llm`:

1. **Reads config** to find the provider (`anthropic` / `openrouter` / `mock`).
2. **Builds a cache key** from `(stage, provider:model, full prompt)` and checks a **disk cache** first — so re-runs and `--offline` replay are free and deterministic.
3. **Dispatches to the provider**:
   - `anthropic` → `_call_anthropic` → the real Claude SDK (`client.messages.create`). *This is the exact line that threw your `401` earlier — it's where the key is actually used.*
   - `mock` → `_call_mock` → a **deterministic local stub** that returns structurally-valid placeholder Apex. It's not a hidden fixture library: the output is generated from the request and is always labelled `provider=mock` so it's never confused with a real migration.
4. **Records accounting** — tokens and per-provider request counts, so the report can print real cost.

Two production touches worth knowing:
- **Prompt caching:** the big, stable part of the prompt (mapping rules, type tables, schema) is sent as a cached system prefix, so every class in a repo reuses it at ~0.1× cost instead of re-billing it.
- **Structured outputs:** `call_structured` passes a JSON schema and returns `parsed` — guaranteed-parseable JSON — which is why the Planner and Critic get clean objects instead of scraped text.

### The router — cheap vs frontier ([router.py](../h2a-mvp/src/agentic/router.py))
`route_model(config, stage)` looks at the stage's task family (`comprehend`, `plan`, `generate`, `critic`, …) and returns which model to use based on a **tier** — `cheap` or `frontier`. The idea: don't pay Opus prices to summarise a class; do pay them to *write* and *review* the Apex. It only applies to the `anthropic` provider (the model ids are Claude ids). It's **off by default** (`routing.enabled: false`), so unless you turn it on, everything uses your configured `model` (Opus 4.8).

### The retriever — RAG grounding ([retriever.py](../h2a-mvp/src/agentic/retriever.py))
Before the Builder writes or the Critic reviews, `retriever.grounding_block(query)` pulls the most relevant chunks from the bundled notes in `agentic/knowledge/*.md` (governor limits, fflib patterns, SOQL security, Apex testing) and injects them into the prompt. So the model is reminded of *real* facts instead of relying on memory. It's a **scaffold**: dependency-free TF-IDF text matching (no embeddings, no vector database, no network) — deterministic and testable, with a clean interface to later swap in a bigger semantic corpus.

---

## Part 9 — How the agents are *configured* ([config.yaml](../h2a-mvp/config.yaml))

Agents aren't hard-wired — their behaviour is turned on/off and tuned in `config.yaml`. The blocks that matter:

```yaml
provider: anthropic
model: claude-opus-4-8        # the default model (used when routing is off)

agentic:
  critic: true                # run the Critic review gate on each artifact
  rag:
    enabled: true             # inject bundled Salesforce facts into prompts
    top_k: 3                  # how many doc chunks per prompt
  routing:
    enabled: false            # turn on to use a cheap model for comprehend/plan
    models: { cheap: claude-haiku-4-5-20251001, frontier: claude-opus-4-8 }
    tiers:  { comprehend: cheap, plan: cheap, generate: frontier, critic: frontier, ... }

verify:
  deploy: false               # true (or --verify) to deploy-check against a real org
  run_tests: false            # also run Apex tests for coverage
  coverage_threshold: 75      # heal tests until coverage ≥ this %
  auto_repair: true           # feed deploy errors back into repair + re-deploy
```
So "configuring an agent" mostly means: which model it uses (via `model`/`routing`), whether it runs at all (`critic`, `verify.deploy`), and how many repair rounds it's allowed (`max_repair_attempts`, `max_deploy_attempts`). No code changes needed to, say, turn off the Critic or switch to a cheaper model.

---

## Part 10 — A worked example: the demo project through the machine

Using `Testing/acme-commerce-hybris` (5 classes), here's what actually happens:

1. **Analyse:** domains found → `Order`, `OrderSummary`, `OrderCleanup`, `Promotion`; order sorted so `Order` precedes `OrderCleanup` (the job depends on it).
2. **Comprehend:** Claude summarises each class. `DefaultOrderService` → *"places orders; rule: total must be > 0."*
3. **Plan:** `OrderDao`→`OrderSelector`, `DefaultOrderService`→`OrderService`, `OrderController`→`OrderController`, `OrderCleanupJob`→`OrderCleanupScheduler` — all Convert. **`DefaultPromotionService`→`PromotionService`, Convert + flagged "consider Salesforce CPQ"** (the judgement call, recorded rather than acted on).
4. **Build + Critic, in order:** `OrderSelector` built first; its method signatures are registered. `OrderService` built next *with those signatures in scope* so it calls the selector correctly. Critic checks the zero-total rule survived; if the Apex dropped it, that's an `ERROR` → back to the Builder → re-review.
5. **Reconcile:** the Apex used `Order__c.Priority__c`, which isn't in `items.xml`; but `priority` *is* in the Java → `Priority__c` is added with evidence.
6. **Write + data + cron:** `.cls` files, object/field XML, `Customer__c.csv`/`Order__c.csv`/…, and the `OrderCleanupScheduler` schedule runbook.
7. **Verify (if on):** validate-only deploy to your org; heal any real errors; write per-class confidence into `FEASIBILITY_REPORT.md`.
8. **Docs:** `MIGRATION_PLAN.md` shows the CPQ recommendation and the Critic's findings; the decisions log records every step.

(Remember: steps 3 and 5's *intelligence* only appears on a **real** Claude run — mock mode is deterministic and defaults promotions to Apex.)

---

## Part 11 — Cheat-sheet: the classes/files that matter most

| If you want to understand… | Read this | It's a… |
|---|---|---|
| The whole agentic flow | `agentic/orchestrator.py` → `run_agentic_migration` | function (the conductor) |
| How agents share state | `agentic/blackboard.py` | dataclass (shared memory) |
| Deciding Convert/Skip (+ native flag) | `agentic/planner.py` | agent |
| Writing the Apex | `agentic/builders.py` → `BuilderAgent` | agent |
| Reviewing the Apex | `agentic/critic.py` | agent |
| Deploy + self-heal | `agentic/builders.py` → `VerifierAgent`, `verify.py` | agent + engine |
| Cheap-vs-frontier model choice | `agentic/router.py` | function |
| RAG grounding | `agentic/retriever.py` | class |
| Talking to Claude (+ mock, cache, cost) | `llm.py` | gateway |
| The actual code generator | `generate.py` | function (a "hand") |
| Objective checks + repair | `validate.py` | functions |
| The control panel | `config.yaml` | config |

---

## Part 12 — Newest capabilities: complete-conversion + frontend→LWC

Two additions build directly on everything above.

### "Convert everything, flag natives" (never silently drop logic)
Earlier, the Planner could tag a target `Native` (e.g. pricing→CPQ) or `Skip` and **generate no
code**. That's changed. The Planner vocabulary is now **`Convert`** or **`Skip`**:
- **Convert** is the default for anything with business logic. Even when a native Salesforce product
  (CPQ, Flow, Approval Process) would be a better long-term home, the logic is **still fully
  converted to Apex** and the suggestion is attached as a *review flag* — a banner comment in the
  `.cls` plus an open question in the report. See `PlanItem.is_code` in
  [blackboard.py](../h2a-mvp/src/agentic/blackboard.py) (`True` for everything except `Skip`) and the
  rewritten prompt in [planner.py](../h2a-mvp/src/agentic/planner.py).
- **Skip** is reserved for code with no business logic (pure DTOs, framework glue), and always
  carries a reason.
- A **completeness ledger** (`bb.completeness_ledger()`) accounts for *every* ingested class as
  `converted | flagged | skipped | unaccounted` — printed at the end of a run and written into both
  `MIGRATION_PLAN.md` and `FEASIBILITY_REPORT.md`. It's the proof nothing was dropped.

### Frontend: Spartacus (Angular) → LWC
The engine now migrates the storefront, not just the backend. New pieces, all mirroring the backend
path:
- [frontend_ingest.py](../h2a-mvp/src/frontend_ingest.py) — discovers `*.component.ts` (+ paired
  `.html`/`.scss` + injected services), emits them as `Component`-layer classes; records NgModules /
  type-only files as skipped-with-reason.
- [generate_lwc.py](../h2a-mvp/src/generate_lwc.py) — translates one component into an LWC **bundle**
  (`.js`/`.html`/`.css`/`.js-meta.xml` + a Jest test) and, when it reads data, a thin
  `@AuraEnabled` **Apex controller** the LWC `@wire`s to.
- [validate_lwc.py](../h2a-mvp/src/validate_lwc.py) — the objective LWC gate (the big one: **no
  expressions in `{ }` template bindings** — they must be getters).
- The **Builder** branches on the `Component` layer to `generate_lwc`; the **Critic** reviews the
  LWC bundle (behavior parity + template rules) instead of Apex; the **Verifier** needs no change —
  LWC is metadata, so the same deploy-check compiles it. Four new RAG docs under
  `agentic/knowledge/` ground it all.

The agents, the Blackboard, the router, the LLM layer — **none of that changed shape.** A new output
target slotted into the same team. That's the payoff of the architecture in Parts 5–8.

## Part 13 — The assurance layer: the modules that prove the work

The agents *produce* the migration. This second set of modules *proves* it — and none of
them makes a model call. They read what the run already recorded, which is what makes them
deterministic, free, and hard to argue with.

They matter more than they look. Any tool can emit Apex; this is the part a customer's
architect actually interrogates.

### Before anything is spent (all AI-free, all shown at the Discovery gate)
| Module | What it does |
|---|---|
| [preflight.py](../h2a-mvp/src/preflight.py) | Is this really a SAP Commerce project? Verdict, confidence, blockers — plus any credentials found in the upload. Refuses a wrong upload before a run exists. |
| [forecast.py](../h2a-mvp/src/forecast.py) | What this run will cost, as a **range**. Constants are measured from instrumented runs and kept in one place so drift is visible. |
| [orgfit.py](../h2a-mvp/src/orgfit.py) | Reads the **destination** org via the `sf` CLI and reconciles it against the plan: collisions, reusable standard objects, installed packages, limits headroom. |
| [radar.py](../h2a-mvp/src/radar.py) | Eleven Hybris→Salesforce hazard rules (query-in-loop, `@Transactional`, session-scoped beans…). Java and XML are stripped separately — the Java stripper erases XML attribute values. |

### After the build — the proof stack
| Module | The question it answers |
|---|---|
| [rule_ledger.py](../h2a-mvp/src/rule_ledger.py) | Did each business rule survive? Four verdicts: asserted / implemented / at_risk / **dropped**. |
| [characterize.py](../h2a-mvp/src/characterize.py) | Does it *behave* the same? Mines the original JUnit suite and replays it. The adapter bridge lets the model arrange and act but **never write the assertion** — that comes from the recording. |
| [provenance.py](../h2a-mvp/src/provenance.py) | Where did each generated method come from? Symbols located in both texts, **never model-reported line numbers**. |
| [alignment.py](../h2a-mvp/src/alignment.py) | Rule → implementation → proof on one row. It labels its own weakest link (rule→method is keyword overlap) wherever that link appears. |
| [triage.py](../h2a-mvp/src/triage.py) | Which of these need a human? Bands plus the plain reasons — the score is a sorting device and is never shown alone. |
| [blast.py](../h2a-mvp/src/blast.py) | What else comes back into question if I rework this one? Reverse walk over `referenced_types`; direct and transitive kept separate. |
| [signoff.py](../h2a-mvp/src/signoff.py) | Who approved what, on what evidence — and what this does **not** certify. An unattended run reads *unreviewed*, never *approved*. |
| [replay.py](../h2a-mvp/src/replay.py) | Every model call, keyed and replayable. Prompts are deliberately **not** stored. |
| [checkpoint.py](../h2a-mvp/src/checkpoint.py) | Snapshots the Blackboard before each gate, so you can return to *before you decided* and diff two runs. |

### Cross-cutting infrastructure
| Module | Why it exists |
|---|---|
| [runctx.py](../h2a-mvp/src/runctx.py) | Per-run provider / model / key / spend-cap in `ContextVar`s. Two concurrent tenants used to race over one process global — a mock run could inherit a real provider. `propagate()` copies **values**, not the Context. |
| [pricing.py](../h2a-mvp/src/pricing.py) | Per-model rates. An unpriced model makes a total a **floor**, and it says so rather than under-reporting. |
| [slim.py](../h2a-mvp/src/slim.py) | Trims imports and trivial accessors out of prompts. **Javadoc is always kept** — it is where the business rules live. |
| [textio.py](../h2a-mvp/src/textio.py) | One encoding fallback chain (utf-8-sig → utf-8 → cp1252 → iso-8859-1). Real estates contain latin-1 files, and a `UnicodeDecodeError` used to abort a whole run. |
| [state_ledger.py](../h2a-mvp/src/state_ledger.py) · [incremental.py](../h2a-mvp/src/agentic/incremental.py) | Reuse whatever provably hasn't changed, so a re-run isn't re-billed for it. |

### One rule that shaped several of these
**Where the AI could grade its own homework, it isn't allowed to.** The characterization
bridge can't write assertions; provenance never asks for line numbers; the rule ledger
inspects generated *text* rather than asking the model whether it did the job. Each of
those was a place where the easy design would have produced a number that always looked
good.

## Part 14 — Glossary (plain words)

- **Agent** — a Python class with a role and a method; it preps data, calls Claude, and writes a structured result to the Blackboard. Not autonomous, not magic.
- **Orchestrator** — the top-level function that runs the agents in the right order. The conductor.
- **Blackboard** — one shared object holding all state for a run; how agents coordinate without talking to each other.
- **Domain** — a group of related source classes (e.g. everything "Order").
- **Target** — one thing to generate on Salesforce (e.g. `OrderSelector`).
- **Artifact** — a generated target tracked through its lifecycle (`planned → generated → reviewed → accepted/needs_review`).
- **Structured output** — asking Claude to answer in a fixed JSON shape so the result is guaranteed-parseable.
- **Routing** — choosing a cheaper or costlier model per task to save money.
- **RAG / grounding** — injecting relevant reference facts into the prompt so the model doesn't rely on memory.
- **Reconciliation** — adding a schema field the code needs *and* the source proves is real.
- **Self-heal** — deploy → read real errors → fix → redeploy, in a bounded loop.
- **Mock provider** — a keyless, deterministic stub that exercises the whole pipeline for free; always labelled so it's never mistaken for a real run.

---

### The one-sentence summary to carry away
> The engine is a set of ordinary, testable functions (the "hands") plus a small team of **agents** — each just a class that makes one careful Claude call for a specific judgement — coordinating through a single shared **Blackboard**, run in order by an **orchestrator**, and configured (not recoded) through `config.yaml`.
