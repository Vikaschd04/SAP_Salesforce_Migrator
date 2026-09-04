# Portage — Documentation

**Version:** 0.11.0

An AI-powered platform that migrates a commerce codebase from one platform to another and
then **proves the result still behaves the same** — rule by rule, method by method, against
evidence rather than assertion.

Two pipelines run today, over one engine:

| Migration | Reads | Writes | Strongest claim available |
|---|---|---|---|
| **SAP Hybris → Salesforce** | Java, Spring, `items.xml`, ImpEx, Spartacus | Apex, SObjects, Flows, LWC | **deploy-verified** against a real org |
| **Adobe Commerce → SAP Hybris** | PHP, `di.xml`, `db_schema.xml`, EAV patches | A Hybris extension: services, DAOs, jobs, interceptors, listeners, `items.xml` | **type-checked** — SAP lends no hosted compiler |

That last column is the point, and it is why the two rows differ. Salesforce lends a free
hosted compiler, so a Hybris→Salesforce run can say *proven to run*. SAP does not, so an
Adobe→Hybris run says *statically checked and type-checked against a stand-in* — and the
sign-off says exactly that rather than borrowing the stronger word.

It ships as three surfaces over one engine: a **web cockpit**, a **VS Code extension**, and
a **command-line engine**.

This folder is the single home for every project document.

## Start here

| I want to... | Read this |
|---|---|
| **Understand it in plain English, no jargon** | [HOW_IT_WORKS.md](HOW_IT_WORKS.md) |
| **Explain what each screen shows during a demo** | [COCKPIT_GUIDE.md](COCKPIT_GUIDE.md) |
| **Learn the actual code — how agents work & coordinate** | [CODEBASE_GUIDE.md](CODEBASE_GUIDE.md) |
| **Know why anyone would buy this over a competitor** | [DIFFERENTIATORS.md](DIFFERENTIATORS.md) |
| **Introduce the project to a client in 5 slides** | `CLIENT_DECK.pptx` — pictorial, high level |
| **Present the slide deck to management** | `DEMO_DECK.pptx` + [DEMO_DECK_SCRIPT.md](DEMO_DECK_SCRIPT.md) |
| **Present the architecture to engineers** | `ARCHITECTURE_DECK.pptx` + `architecture-diagram.png` |
| **Run the software live during a demo** | [DEMO_SCRIPT.md](DEMO_SCRIPT.md) |
| **Install and run it myself** | [HOW_TO_USE.md](HOW_TO_USE.md) |
| **Run it for a team (accounts, keys, queue, spend caps)** | [SETUP.md](SETUP.md) |
| **Deploy the web platform** | [DEPLOY_RENDER.md](DEPLOY_RENDER.md) |
| **Know what's shipped vs still open** | [ROADMAP.md](ROADMAP.md) · [ROADMAP_INDUSTRIAL.md](ROADMAP_INDUSTRIAL.md) |
| **Understand how one engine runs two migrations** | [ROADMAP_MULTI_PLATFORM.md](ROADMAP_MULTI_PLATFORM.md) |
| **Run or verify the v2 engine** | [V2_ENGINE.md](V2_ENGINE.md) |
| **See what is built and what is next, task by task** | [V2_DELIVERY_PLAN.md](V2_DELIVERY_PLAN.md) |
| **Understand where a plausible-looking conversion is silently wrong** | [EDGE_CASES.md](EDGE_CASES.md) |

## The one-paragraph pitch

Point the tool at a commerce codebase. Before it spends a penny it tells you what the
codebase is, which migrations can run against it, what the run will cost, and where the
migration hazards are — in that platform's own vocabulary, because a Magento estate is not
measured for Java habits. Then a team of AI agents — a Planner, a Builder, a Critic and a
Verifier — convert **everything** (a native-product fit is flagged for review, never a
reason to silently drop logic), review it adversarially, and check the result as strongly
as the target platform allows. You stop at three review gates along the way.

What comes out is a deployable package **plus the evidence**: every business rule tracked
from source to generated method, every generated method traced back to the source that
produced it, a completeness ledger accounting for every input file, and a sign-off contract
recording who approved what — including, prominently, whatever it could not prove.

> **The one-line version:** *Every other tool converts your code. This one proves it still
> behaves the same.*

## The full document set

### Product & design
| Document | Purpose |
|---|---|
| [PRD.md](PRD.md) | **Product Requirements** — the problem, what we build, who for, success metrics |
| [TRD.md](TRD.md) | **Technical Requirements** — functional/non-functional, security, environment, supported I/O |
| [TDD.md](TDD.md) | **Technical Design** — architecture, orchestration modes, the agentic core, the self-healing loop |
| [APP_FLOWS.md](APP_FLOWS.md) | **Application Flows** — step-by-step for every user and system flow, including failure paths |
| [PLATFORM_VISION.md](PLATFORM_VISION.md) | Where the platform goes beyond a migration tool |

### Understanding it
| Document | Purpose |
|---|---|
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | **Plain-English guide** — the whole system, no technical background required |
| [CODEBASE_GUIDE.md](CODEBASE_GUIDE.md) | **Teacher's walkthrough of the code** — what an "agent" really is, how the four coordinate through the Blackboard, how a prompt becomes a Claude call |
| [DIFFERENTIATORS.md](DIFFERENTIATORS.md) | **The moat** — the thirteen capabilities that make this more than a code translator, and how each shipped |

### Using it
| Document | Purpose |
|---|---|
| [HOW_TO_USE.md](HOW_TO_USE.md) | **Setup & usage** — installing, configuring, running and reading the output, for all three surfaces |
| [SETUP.md](SETUP.md) | **Operating it for a team** — accounts, per-tenant keys, the run queue, spend caps, server settings |
| [DEPLOY_RENDER.md](DEPLOY_RENDER.md) | Deploying the web platform to Render |

### Presenting it
| Document | Purpose |
|---|---|
| [COCKPIT_GUIDE.md](COCKPIT_GUIDE.md) | **Screen-by-screen guide** — what every tab and sub-tab shows, in plain words, with the line to say for each |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | **Live product demo script** — running the software on the sample project, with talking points and Q&A |
| [DEMO_DECK_SCRIPT.md](DEMO_DECK_SCRIPT.md) | **Deck speaker script** — what to say per slide, with time budgets |
| `CLIENT_DECK.pptx` | **The 5-slide client intro** — 16:9, almost entirely diagrams: what it does, the architecture, how a run flows, and why the output can be trusted. For the meeting where nobody has seen it before. |
| `DEMO_DECK.pptx` | The executive accelerator deck — editable PowerPoint, built for 10–12 minutes |
| `ARCHITECTURE_DECK.pptx` | The **architecture deck** for a technical audience — surfaces, layers, pipeline, run lifecycle, stack, deployment |
| `architecture-diagram.png` | The full layered architecture as **one image** — drop it into any deck or wiki |

### Planning
| Document | Purpose |
|---|---|
| [ROADMAP.md](ROADMAP.md) | **Future scope** — what's shipped, what's next, and the hardest open bets |
| [ROADMAP_INDUSTRIAL.md](ROADMAP_INDUSTRIAL.md) | The industrial-readiness track — proof, platform, and what each was for |
| [EDGE_CASES.md](EDGE_CASES.md) | **The register** — every failure mode where a convincing conversion is wrong, each marked covered / partial / gap, each gap owned by a delivery item. The honest answer to "why this and not a generic code translator" |
| [V2_DELIVERY_PLAN.md](V2_DELIVERY_PLAN.md) | **The build sheet** — every phase broken into work items, with current status, what "done" means, and how each is checked |
| [V2_ENGINE.md](V2_ENGINE.md) | **Running the v2 engine** — how to select a version, and the three tests that prove v1 is untouched |
| [ROADMAP_MULTI_PLATFORM.md](ROADMAP_MULTI_PLATFORM.md) | **Two Pipelines, One Engine** — the scope-locked build plan for Adobe Commerce → SAP Hybris alongside Hybris → Salesforce: the adapter architecture, six testable correctness gates, four efficiency budgets, and how the shipped pipeline is protected |

### Regenerating the artifacts
| Script | Regenerates |
|---|---|
| `build_client_deck.py` | `CLIENT_DECK.pptx` |
| `build_deck.py` | `DEMO_DECK.pptx` |
| `build_arch_image.py` | `architecture-diagram.png` |
| `build_arch_deck.py` | `ARCHITECTURE_DECK.pptx` (embeds the diagram — run `build_arch_image.py` first if stale) |

## Where the code lives

| Folder | What it is |
|---|---|
| `h2a-mvp/` | **The engine** — the Python pipeline that does the actual work, both pipelines and the adapters between them. 1,109 tests. |
| `h2a-web/` | **The web platform** — FastAPI backend + React cockpit, with accounts, per-tenant keys, a run queue and durable history. 45 tests. |
| `h2a-vscode-extension/` | **The VS Code extension** — bundles a synced copy of the engine, so it is self-contained |
| `Testing/` | Three sample estates: `acme-commerce-hybris` (SAP Commerce), `acme-commerce-magento` (a single Magento module, the fast regression fixture) and `acme-commerce-magento-full` (an industry-scale three-module Adobe Commerce suite), plus a deterministic capability tour |

## Quick start

Both pipelines run keylessly with the `mock` provider. The source is detected, so you
point it at a codebase rather than choosing a migration.

```bash
cd h2a-mvp && source .venv/bin/activate

# Which migrations can run against this codebase?
python -m src.main identify --input ../Testing/acme-commerce-magento-full

# SAP Hybris → Salesforce
H2A_PROVIDER=mock python -m src.main agent-migrate \
  --input ../Testing/acme-commerce-hybris --output /tmp/sf

# Adobe Commerce → SAP Hybris
H2A_PROVIDER=mock python -m src.main agent-migrate \
  --input ../Testing/acme-commerce-magento-full --output /tmp/hy

# What each run left behind, and what it could not prove
cat /tmp/sf/SIGN_OFF.md
cat /tmp/hy/SIGN_OFF.md
```

> **Note on `mock`:** it exercises every stage for free but does not *infer* anything — so
> the panels that depend on real comprehension (business rules, alignment) will be empty,
> and the provenance report says in as many words that its coverage figure is measuring
> placeholders. That is the mock provider being honest, not a bug.

Full instructions: [HOW_TO_USE.md](HOW_TO_USE.md).
