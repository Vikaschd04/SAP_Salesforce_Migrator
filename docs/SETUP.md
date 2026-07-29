# Running the H2A Migration Cockpit on another machine

After `git clone` / `git pull`, follow these steps. Git intentionally does **not** carry the
Python venv, `node_modules`, the built SPA (`dist/`), or your API keys (`.env`) — you recreate
those locally (they're `.gitignore`d). Nothing sensitive is in the repo.

## Prerequisites
- **Python 3.11+**  (`python3 --version`)
- **Node.js 18+ and npm**  (`node --version`) — needed to build the web cockpit
- **git**

## One-time setup

```bash
# 0. get the code
git clone https://github.com/Vikaschd04/SAP_Salesforce_Migrator.git
cd SAP_Salesforce_Migrator

# 1. create the engine's Python venv + install deps (engine + web backend)
python3 -m venv h2a-mvp/.venv
h2a-mvp/.venv/bin/python -m pip install --upgrade pip
h2a-mvp/.venv/bin/python -m pip install -r h2a-mvp/requirements.txt
h2a-mvp/.venv/bin/python -m pip install -r h2a-web/backend/requirements.txt

# 2. build the React cockpit (produces h2a-web/web/dist that the backend serves)
cd h2a-web/web
npm install
npm run build
cd ../..
```

## Run it

```bash
cd h2a-web/backend
../../h2a-mvp/.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8733
```

Open **http://127.0.0.1:8733**. Keep **Provider = Mock** for a free, keyless run — it works
immediately with no API key. Default input path `Testing/demo-commerce-suite` ships with the repo.

## Using real AI (optional)

Mock is deterministic and free. For real Apex/LWC quality and full Copilot answers, add keys to
`h2a-mvp/.env` (this file is git-ignored — never commit it):

```bash
# h2a-mvp/.env
ANTHROPIC_API_KEY=sk-ant-...
# or, for OpenRouter:
OPENROUTER_API_KEY=sk-or-v1-...
```

Then pick **Provider = Anthropic** (uses `claude-opus-4-8` by default) or **OpenRouter** in the UI.
For OpenRouter's model, set `openrouter.model` in `h2a-mvp/config.yaml` (e.g. `anthropic/claude-sonnet-5`).

## After later `git pull`s
- If Python deps changed: re-run the two `pip install -r …` commands.
- If the web UI changed: `cd h2a-web/web && npm run build` again (rebuilds `dist/`).
- Then restart uvicorn.

## Dev mode (hot-reload UI, optional)
```bash
cd h2a-web/web && npm run dev      # Vite on http://127.0.0.1:5173, proxies /api to :8733
# (run the uvicorn backend in another terminal)
```

## The VS Code extension (separate front door)
The extension lives in `h2a-vscode-extension/`. To use it on the other machine, install the
pre-built VSIX if present, or build one:
```bash
cd h2a-vscode-extension
npm install && npm run compile
npx @vscode/vsce package        # produces h2a-vscode-extension-<version>.vsix
```
Install via the IDE: Extensions → ⋯ → *Install from VSIX…*. Set provider/keys in the IDE's
**User** settings (search `h2aMigrator`) — not in a workspace `.vscode/settings.json`, which
would override your choice.

## Troubleshooting
- **Blank page / old dashboard** → `dist/` wasn't built; run `npm run build` in `h2a-web/web`.
- **"backend offline"** in the top bar → the uvicorn server isn't running (or wrong port).
- **Copilot/real run errors on Anthropic** → missing/invalid key in `h2a-mvp/.env`, or use Mock.
- **Port already in use** → `lsof -ti :8733 | xargs kill`, then restart.
