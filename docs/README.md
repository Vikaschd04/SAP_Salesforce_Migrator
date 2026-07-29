# SAP Hybris → Salesforce Apex Migrator — Documentation

**Version:** 0.8.0

An AI-powered platform that translates a SAP Hybris (Java/Spring) codebase into deployment-ready Salesforce Apex — code, data model, data, and scheduled jobs — with every output reviewed and verified before it reaches a human. Ships as a VS Code extension and a command-line engine.

This folder is the single home for every project document. Start with whichever fits what you need:

## Start here

| I want to... | Read this |
|---|---|
| **Understand it in plain English, no jargon** | [HOW_IT_WORKS.md](HOW_IT_WORKS.md) |
| **Learn the actual code — how agents work & coordinate** | [CODEBASE_GUIDE.md](CODEBASE_GUIDE.md) |
| **Present the slide deck to management** | `DEMO_DECK.pptx` (10 slides, 10–12 min) + [DEMO_DECK_SCRIPT.md](DEMO_DECK_SCRIPT.md) (what to say per slide, with time budgets) |
| **Run the software live during a demo** | [DEMO_SCRIPT.md](DEMO_SCRIPT.md) |
| **Install and run it myself** | [HOW_TO_USE.md](HOW_TO_USE.md) |

## The full document set

| Document | Purpose |
|---|---|
| [PRD.md](PRD.md) | **Product Requirements** — the problem, what we build, why, who it's for, value proposition, success metrics |
| [TRD.md](TRD.md) | **Technical Requirements** — functional/non-functional requirements, security, environment & dependencies, supported inputs/outputs |
| [TDD.md](TDD.md) | **Technical Design** — architecture, the two orchestration modes, the agentic core, the self-healing loop, design rationale |
| [APP_FLOWS.md](APP_FLOWS.md) | **Application Flows** — step-by-step diagrams for every user and system flow, including failure/degradation paths |
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | **Plain-English guide** — the whole system explained with no technical background required |
| [CODEBASE_GUIDE.md](CODEBASE_GUIDE.md) | **Teacher's walkthrough of the code** — the important classes, what an "agent" really is, how the four agents work and coordinate through the Blackboard, and how a prompt becomes a Claude call |
| [HOW_TO_USE.md](HOW_TO_USE.md) | **Setup & usage guide** — installing, configuring, running, and reading the output, for both the extension and the CLI |
| `DEMO_DECK.pptx` | The 10-slide executive accelerator deck — **editable PowerPoint** (A4 landscape), built for a 10–12 minute presentation |
| [DEMO_DECK_SCRIPT.md](DEMO_DECK_SCRIPT.md) | **Deck speaker script** — what to say per slide, with per-slide time budgets and Q&A quick answers |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | **Live product demo script** — how to run the software live on the sample project, with talking points and Q&A |
| `build_deck.py` | Regenerates `DEMO_DECK.pptx` from code |
| [ROADMAP.md](ROADMAP.md) | **Future scope** — what's shipped, what's in progress, what's next, and the hardest open bets |

## The one-paragraph pitch

Point the tool at a Hybris codebase. A team of AI agents — a Planner, a Builder, a Critic, and a Verifier — decide what should become Salesforce Apex (and what should instead be a native Salesforce feature), write the code following Salesforce's own best-practice patterns, adversarially review it for correctness and security, and optionally deploy it to a real Salesforce org and self-heal any real compiler errors or coverage gaps. The result is a deployable Salesforce DX project plus a full report: what was built, how confident the system is in each piece, and what a human should double check.

## Where the code lives

| Folder | What it is |
|---|---|
| `h2a-mvp/` | The engine — the Python pipeline that does the actual work |
| `h2a-vscode-extension/` | The VS Code extension — bundles a copy of the engine, so it's self-contained |
| `Testing/` | Sample Hybris projects and example outputs, used for development and demos |

## Quick start

```bash
# Free, keyless, instant — exercises the whole pipeline with placeholder code
cd h2a-mvp && source .venv/bin/activate
H2A_PROVIDER=mock python -m src.main agent-migrate \
  --input ../Testing/dummy-hybris-store --output ../Testing/out
```

Full instructions: [HOW_TO_USE.md](HOW_TO_USE.md).
