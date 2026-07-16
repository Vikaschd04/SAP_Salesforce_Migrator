# SAP Hybris → Salesforce Apex Migrator

**An AI agent team that migrates a SAP Hybris (Java/Spring) codebase into deployment-ready Salesforce Apex — code, data model, data, and scheduled jobs — and proves its own work before a human ever reviews it.**

Ships as a **VS Code extension** (right-click a folder → done) and a **command-line engine**, powered by Anthropic Claude.

---

## What it does, in one sentence

Point it at a Hybris codebase. A **Planner** decides what should become Salesforce Apex (and what should instead be a native Salesforce feature, like CPQ); a **Builder** writes the code and tests following Salesforce's own enterprise patterns; a **Critic** adversarially reviews every artifact for behavior, security, and correctness; and a **Verifier** deploys the result to a real Salesforce org and self-heals any real compile errors or coverage gaps — before you ever see the output.

## 📖 Full documentation

Everything — product requirements, architecture, app flows, a plain-English guide, a setup guide, a stakeholder demo deck + script, and the roadmap — lives in **[`docs/`](docs/README.md)**.

| I want to... | Read this |
|---|---|
| Understand it in plain English | [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) |
| Present it to stakeholders | [docs/DEMO_DECK_SCRIPT.md](docs/DEMO_DECK_SCRIPT.md) + `docs/DEMO_DECK.pptx` |
| Run a live demo | [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) |
| Install and use it | [docs/HOW_TO_USE.md](docs/HOW_TO_USE.md) |
| See the architecture | [docs/TDD.md](docs/TDD.md) |
| See what's next | [docs/ROADMAP.md](docs/ROADMAP.md) |

## Quick start (free, no API key)

```bash
cd h2a-mvp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

H2A_PROVIDER=mock python -m src.main agent-migrate \
  --input ../Testing/dummy-hybris-store --output ../Testing/out
```

This exercises the entire pipeline — planning, code generation, schema derivation, data migration, scheduled-job translation, and reporting — with clearly-labeled placeholder Apex, at zero cost. See [docs/HOW_TO_USE.md](docs/HOW_TO_USE.md) for real (AI-powered) runs and the VS Code extension.

## Repository layout

| Folder | What it is |
|---|---|
| [`docs/`](docs/README.md) | All project documentation |
| [`h2a-mvp/`](h2a-mvp/README.md) | The Python engine — parsing, the agentic core, and the CLI |
| [`h2a-vscode-extension/`](h2a-vscode-extension/README.md) | The VS Code extension (bundles the engine) |
| [`Testing/`](Testing/) | A sample Hybris project and example migration outputs |

## Status

**v0.8.0** — Phase 0 (verifiable correctness) and Phase 1 (agentic core) delivered; Phase 2 (full-surface coverage: data, schema, scheduled jobs) in progress. Deploy verification is now a one-click toggle in the VS Code extension (validate-only, self-healing, against your default org). Full detail in [docs/ROADMAP.md](docs/ROADMAP.md).
