# SAP Hybris → Salesforce Apex Migrator

**An AI agent team that migrates a SAP Hybris (Java/Spring) codebase into deployment-ready Salesforce Apex — code, data model, data, scheduled jobs and Lightning Web Components — and then proves the result still behaves the same.**

Ships as a **web cockpit**, a **VS Code extension**, and a **command-line engine** over one shared engine, powered by Anthropic Claude.

> **Every other tool converts your code. This one proves it still behaves the same** — rule by rule, line by line, against your own org.

---

## What it does, in one sentence

Point it at a Hybris codebase. Before spending anything it tells you what the codebase is, what the run will cost, what will collide in your Salesforce org and where the hazards are. Then a **Planner** decides what to convert (a native-product fit like CPQ is *flagged for review*, never a reason to silently drop logic), a **Builder** writes the code and tests following Salesforce's own enterprise patterns, a **Critic** adversarially reviews every artifact, and a **Verifier** deploys to a real org and self-heals genuine compile errors — with three points along the way where you decide.

What comes out is a deployable package **plus the evidence**: every business rule tracked from source to generated method, your original JUnit tests replayed against the new Apex, every method traced to the Java that produced it, and a sign-off contract recording who approved what — including, prominently, whatever could not be proven.

## 📖 Full documentation

Everything lives in **[`docs/`](docs/README.md)**.

| I want to... | Read this |
|---|---|
| Understand it in plain English | [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) |
| Explain each screen during a demo | [docs/COCKPIT_GUIDE.md](docs/COCKPIT_GUIDE.md) |
| Know why anyone would buy this | [docs/DIFFERENTIATORS.md](docs/DIFFERENTIATORS.md) |
| Present it to stakeholders | [docs/DEMO_DECK_SCRIPT.md](docs/DEMO_DECK_SCRIPT.md) + `docs/DEMO_DECK.pptx` |
| Run a live demo | [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) |
| Install and use it | [docs/HOW_TO_USE.md](docs/HOW_TO_USE.md) |
| Run it for a team | [docs/SETUP.md](docs/SETUP.md) |
| See the architecture | [docs/TDD.md](docs/TDD.md) · `docs/architecture-diagram.png` |
| See what's next | [docs/ROADMAP.md](docs/ROADMAP.md) |

## Quick start (free, no API key)

```bash
cd h2a-mvp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

H2A_PROVIDER=mock python -m src.main agent-migrate \
  --input ../Testing/acme-commerce-hybris --output /tmp/out

cat /tmp/out/SIGN_OFF.md                        # what it did, and what it can't prove
python -m src.main checkpoints --output /tmp/out # snapshots taken before each gate
```

This exercises the entire pipeline — preflight, planning, code generation, schema derivation, data migration, scheduled-job translation, the full assurance stack and reporting — with clearly-labelled placeholder Apex, at zero cost.

> `mock` runs every stage for free but does not *infer* anything, so the panels that depend on real comprehension (business rules, alignment) come out empty. That is the mock provider being honest, not a bug.

For the web cockpit:

```bash
cd h2a-web/backend && pip install -r requirements.txt
uvicorn app:app --port 8000     # then open http://localhost:8000
```

## Repository layout

| Folder | What it is |
|---|---|
| [`docs/`](docs/README.md) | All project documentation |
| [`h2a-mvp/`](h2a-mvp/README.md) | The Python engine — parsing, the agentic core, the assurance stack, the CLI. 296 tests. |
| [`h2a-web/`](h2a-web/README.md) | The web platform — FastAPI backend + React cockpit, accounts, per-tenant keys, run queue, durable history. 44 tests. |
| [`h2a-vscode-extension/`](h2a-vscode-extension/README.md) | The VS Code extension (bundles a synced copy of the engine) |
| [`Testing/`](Testing/) | `acme-commerce-hybris`, a realistic SAP Commerce sample, plus a deterministic capability tour |

## Status

**v0.10.0** — Phases 0–5 delivered: verifiable correctness, the agentic core, Spartacus→LWC, the "convert everything" policy, all thirteen proof differentiators, and the web platform. Open: business processes → Flow, OCC REST → Apex REST, Postgres, RBAC, and house-style memory.

**One honest caveat:** the proof stack is fully unit-tested and validated against the mock provider, but has not yet completed an end-to-end run against a real model. Full detail in [docs/ROADMAP.md](docs/ROADMAP.md).
