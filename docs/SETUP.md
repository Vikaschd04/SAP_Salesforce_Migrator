# Running the H2A Migration Cockpit on another machine

After `git clone` / `git pull`, follow these steps. Git intentionally does **not** carry the
Python venv, `node_modules`, the built SPA (`dist/`), or your API keys (`.env`) — you recreate
those locally (they're `.gitignore`d). Nothing sensitive is in the repo.

## Prerequisites
- **Python 3.11+**  (`python3 --version`)
- **Node.js 18+ and npm**  (`node --version`) — needed to build the web cockpit
- **git**

---

## Windows (VS Code + PowerShell)

Open the folder in VS Code (**File → Open Folder**), then open the integrated terminal
(**Terminal → New Terminal** — defaults to PowerShell) and run:

```powershell
# 0. get the code (skip if already cloned)
git clone https://github.com/Vikaschd04/SAP_Salesforce_Migrator.git
cd SAP_Salesforce_Migrator

# 1. Python venv + deps (engine + web backend). On Windows the venv python is
#    .venv\Scripts\python.exe (not bin/python). Use `py -3` if `python` isn't found.
python -m venv h2a-mvp\.venv
h2a-mvp\.venv\Scripts\python.exe -m pip install --upgrade pip
h2a-mvp\.venv\Scripts\python.exe -m pip install -r h2a-mvp\requirements.txt
h2a-mvp\.venv\Scripts\python.exe -m pip install -r h2a-web\backend\requirements.txt

# 2. build the React cockpit (produces h2a-web\web\dist)
cd h2a-web\web
npm install
npm run build
cd ..\..

# 3. run the server
cd h2a-web\backend
..\..\h2a-mvp\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8733
```

Then open **http://127.0.0.1:8733** (Ctrl+click the link in the terminal). Keep **Provider = Mock**
for a free, keyless run.

**Windows notes**
- Optional: **Ctrl+Shift+P → “Python: Select Interpreter” → `h2a-mvp\.venv`** so VS Code uses it.
- Free a stuck port: `netstat -ano | findstr :8733` then `taskkill /PID <pid> /F`.
- Real AI: create `h2a-mvp\.env` with your key (see “Using real AI” below) — same file, Windows path.
- You don't need to `activate` the venv — the commands call `…\Scripts\python.exe` directly, which
  avoids PowerShell execution-policy prompts.

---

## One-time setup (macOS / Linux)

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

## Run it (macOS / Linux)

```bash
cd h2a-web/backend
../../h2a-mvp/.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8733
```

Open **http://127.0.0.1:8733**. Keep **Provider = Mock** for a free, keyless run — it works
immediately with no API key. Default input path `Testing/acme-commerce-hybris` ships with the repo.

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

## Server settings (environment variables)

All optional. Set none of them and the cockpit runs exactly as it always has: single
user, no login, shared credentials — the right shape for one person on a laptop.

| Variable | Default | What it does |
|---|---|---|
| `H2A_AUTH` | off | Require sign-in. Always on when `H2A_HOSTED=1`. |
| `H2A_ALLOW_SIGNUP` | off | Allow registration *after* the first account exists. The first account can always be created — someone has to bootstrap. Leave this off on a public URL. |
| `H2A_SECRET_KEY` | unset | Encrypts per-user API keys. **Without it, per-user keys are disabled** and every run uses the server's own credential. |
| `H2A_DB_PATH` | `.h2a/runs.db` | Where accounts and run history live. Point it at a mounted disk on a PaaS, or they reset on redeploy. |
| `H2A_MAX_CONCURRENT_RUNS` | `3` | How many migrations run at once. Further ones queue, FIFO, with a visible position. Each run holds a codebase in memory and fans out to parallel model calls, so this is a real resource dial. |
| `H2A_HOSTED` | off | Public-deploy mode: restricts inputs to uploads/bundled samples, and turns auth on. |
| `H2A_DEMO_LOGIN` | off | Offers a one-click **shared** demo account on the sign-in screen, provisioned on first use. It is an unauthenticated way in, so leave it off anywhere that is not a public demo. |
| `H2A_COST_CAP` | `25.0` (from `config.yaml`) | Hard spend ceiling **per run**, in USD. `0` = uncapped. Checked before every model call, so a run overshoots by at most the one call in flight. Work completed before the cap is kept and reused on a re-run rather than paid for twice. |
| `H2A_CONCURRENCY` | `8` (from `config.yaml`) | Model calls in flight *within* one run. Compresses wall-clock, not spend. |
| `H2A_INCREMENTAL` | on | Reuse results for source that provably has not changed since the last run of the same codebase. |

> **On the spend cap.** The Discovery gate forecasts a *range*, and a range is not a limit
> — a repair loop that will not converge spends until it finishes. The cap is what makes
> the forecast binding. If the forecast already exceeds the cap, the Discovery gate says so
> there, while raising it is still a cheap decision rather than a half-finished run.

Generate a secret key with:

```bash
python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Keep it stable. If it changes, stored keys become unreadable — runs fall back to the
server credential rather than failing, but they have to be re-entered.

Per-user keys also need the `cryptography` package:

```bash
../../h2a-mvp/.venv/bin/pip install cryptography
```

Example — a shared instance for a small team:

```bash
cd h2a-web/backend
H2A_AUTH=1 H2A_SECRET_KEY='<your secret>' H2A_MAX_CONCURRENT_RUNS=3 \
  ../../h2a-mvp/.venv/bin/python -m uvicorn app:app --port 8733
```

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
- **"We didn't start this migration"** → preflight decided the upload isn't a SAP Commerce
  project. Zip the extension folder itself (the one holding `extensioninfo.xml`), and
  include `src/` and `resources/` — a zip of only `.jar` files has no source to migrate.
- **"Key storage is off on this server"** → `H2A_SECRET_KEY` isn't set, or `cryptography`
  isn't installed in the venv you started uvicorn with. Both are listed above. Runs still
  work; they just use the server's shared credential.
- **A migration says "Queued · #2"** → it's waiting for a slot. Raise
  `H2A_MAX_CONCURRENT_RUNS` if the machine can take it.
- **History is empty after a redeploy** → `H2A_DB_PATH` is on ephemeral storage. Point it
  at a persistent disk.
