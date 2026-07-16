# How to Use It

**Version:** 0.8.0
**Audience:** Anyone setting up and running a migration, extension or CLI

---

## Option A — VS Code extension (recommended)

### 1. Install
```bash
code --install-extension h2a-vscode-extension-0.8.0.vsix
```
Or: VS Code → Extensions → **···** menu → **Install from VSIX...**

### 2. Configure
Open **Settings → H2A Migrator** and set:

| Setting | What to set it to |
|---|---|
| `h2aMigrator.provider` | `anthropic` (best quality) · `openrouter` (free/cheap, for dev) · `mock` (free, keyless, for testing the pipeline) |
| `h2aMigrator.anthropicApiKey` | Your key from [console.anthropic.com](https://console.anthropic.com/) — only if provider = `anthropic` |
| `h2aMigrator.openrouterApiKey` | Your key from [openrouter.ai](https://openrouter.ai/keys) — only if provider = `openrouter` |
| `h2aMigrator.engine` | `agentic` (recommended — Planner + Critic + RAG) or `linear` (fewer LLM calls, lower cost) |
| `h2aMigrator.incrementalMode` | `true` (default) — skip re-translating domains that haven't changed |

### 3. Run it
Right-click any folder containing your Hybris source in the VS Code Explorer → **H2A: Migrate to Apex**. First run provisions a local Python environment automatically (no manual setup). Watch the progress dashboard.

### 4. Get the output
A new folder appears next to your source: `salesforce_<YourFolderName>/` — a complete, deployable Salesforce DX project. Open `FEASIBILITY_REPORT.md` first — it's the executive summary of the run.

---

## Option B — Command line

### 1. Set up the environment (one time)
```bash
cd h2a-mvp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```
Edit `.env` and add your key:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 2. Run a migration
```bash
# Recommended: the full agentic run (Planner + Builder + Critic + Verifier + RAG)
python -m src.main agent-migrate --input <path-to-hybris-code> --output <output-dir>

# Or the simpler linear pipeline (fewer LLM calls)
python -m src.main repo-migrate --input <path-to-hybris-code> --output <output-dir>
```

### 3. Try it for free first (no API key needed)
```bash
H2A_PROVIDER=mock python -m src.main agent-migrate --input <path-to-hybris-code> --output <output-dir>
```
This exercises the entire pipeline — parsing, planning, schema derivation, metadata, data, scheduling, reporting — with clearly-labeled placeholder Apex instead of real AI-written code. Use this to sanity-check your source is being read correctly before spending API credits.

### 4. Add real-org verification (optional)
Requires the [Salesforce CLI](https://developer.salesforce.com/tools/salesforcecli) and an authorized org or scratch org:
```bash
sf org login web         # one-time
python -m src.main agent-migrate --input <dir> --output <out> --verify
```
This dry-run deploys the output and self-heals any real compiler errors or low test coverage before finishing.

### 5. Just the data or just the scheduled jobs
```bash
python -m src.main impex   --input <hybris_dir> --output <out_dir>   # ImpEx → CSVs + upsert runbook
python -m src.main cronjob --input <hybris_dir> --output <out_dir>   # cron triggers → Scheduled Apex runbook
```

### 6. Run the test suite
```bash
python -m pytest tests/ -q
```

---

## Reading the output

| File | What it tells you |
|---|---|
| `FEASIBILITY_REPORT.md` | **Start here.** Inventory, validation results, confidence score per class, deploy status, cost. |
| `MIGRATION_PLAN.md` | *(agentic runs only)* What the Planner decided for each class, the Critic's findings, and the full decision log. |
| `PARITY.md` | Which of the original business rules are actually asserted by the generated tests. |
| `MAPPING.md` | Field-by-field and layer-by-layer mapping reference. |
| `DATA_MIGRATION.md` | Ready-to-run `sf data upsert` commands for your data. |
| `CRON_JOBS.md` | Ready-to-run `System.schedule(...)` commands for your scheduled jobs. |
| `force-app/main/default/` | The actual deployable Salesforce project — deploy with `sf project deploy start --source-dir force-app`. |

---

## Choosing a provider

| Provider | When to use it | Cost |
|---|---|---|
| `mock` | Testing the pipeline itself, CI, sanity-checking your source parses correctly | Free, no key |
| `openrouter` | Development/iteration, cheap experimentation | Free–cheap (rate-limited free tier) |
| `anthropic` | Final/production-quality migrations | Paid, best quality |

All three run the **identical pipeline and prompts** — only the model changes. Switch anytime without touching your code or settings beyond the provider dropdown.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ANTHROPIC_API_KEY not found` | No key set for the chosen provider | Add it to `.env` or the extension's Settings |
| `401 invalid x-api-key` | Key is wrong, revoked, or the workspace has no credit | Generate a fresh key at console.anthropic.com and confirm billing is active |
| `429` rate limit (OpenRouter free models) | Free-tier throttling upstream | Try a different free model, or add your own OpenRouter key to raise limits |
| Deploy verification says "not run" | No `sf` CLI or no authorized org | `sf org login web`, or skip `--verify` — the rest of the pipeline works without it |
| A class shows Low confidence | Offline validation errors, or a failed org deploy | Open the class and the report's confidence basis column — it names the specific issue |
