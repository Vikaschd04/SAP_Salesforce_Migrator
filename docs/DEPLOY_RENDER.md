# Deploy the H2A Cockpit to Render

The whole app (React SPA + FastAPI + migration engine) ships as **one Docker web service**.
A [`render.yaml`](../render.yaml) Blueprint + [`Dockerfile`](../Dockerfile) make it one-click.

## One-click (Blueprint)

1. Create a free account at **https://render.com** and connect your GitHub.
2. In Render: **New +  →  Blueprint**.
3. Pick the repo **`Vikaschd04/SAP_Salesforce_Migrator`** → **Apply**.
   Render reads `render.yaml`, builds the `Dockerfile`, and deploys a service named **`h2a-cockpit`**.
4. First build takes ~4–8 min (it builds the React app, then installs the Python deps).
   When the health check at `/api/health` passes, you get a URL like
   **`https://h2a-cockpit.onrender.com`** — open it.

Keep **Provider = Mock** and hit **Start migration** (default sample `Testing/acme-commerce-hybris`).
It runs free, keyless, and deterministic.

## Manual (without the Blueprint)

**New +  →  Web Service** → connect the repo → Render auto-detects the `Dockerfile` →
set **Health Check Path** `/api/health`, add env vars `H2A_PROVIDER=mock` and `H2A_HOSTED=1` →
**Create Web Service**.

## What the deploy is configured to do

- **Mock by default** (`H2A_PROVIDER=mock`) — no API key, no cost, safe for a public URL.
- **`H2A_HOSTED=1`** — input paths are restricted to the bundled samples or an uploaded `.zip`
  (a public URL can't point the ingester at arbitrary server paths).
- **Auto-deploy** on every push to the connected branch.
- Serves the built cockpit and all `/api` routes from the same origin (no CORS needed).

## Enabling real AI (optional — read the warning)

Mock is the safe default. To get real Apex/LWC quality + full Copilot answers on the hosted app,
in the Render dashboard **Environment** tab add a key and switch the provider:

- `ANTHROPIC_API_KEY = sk-ant-…`  (then set `H2A_PROVIDER = anthropic`), **or**
- `OPENROUTER_API_KEY = sk-or-…`  (then set `H2A_PROVIDER = openrouter`; pick the model in
  `h2a-mvp/config.yaml`, e.g. `anthropic/claude-sonnet-5`).

> ⚠️ **Anyone with the public URL would then spend your credits.** For a shared demo, prefer
> keeping it on **mock**, or put the service behind access control before enabling a real key.

## Notes & limits

- **Free tier sleeps** after ~15 min idle; the next request cold-starts in ~30–60 s. Upgrade to a
  paid instance for always-on.
- **Concurrency** is bounded by `H2A_MAX_CONCURRENT_RUNS` (default 3); further runs queue FIFO with a
  visible position. Accounts and run history persist in SQLite at `H2A_DB_PATH` — **point that at a
  mounted disk**, or a redeploy resets it. Uploaded source and generated output still live under the
  container's temp dir and do not survive a restart.
- **Set `H2A_SECRET_KEY`** if you want per-user API keys; without it every run uses the server's own
  credential. Keep it stable — changing it makes stored keys unreadable.
- **"Verify vs org"** needs the Salesforce CLI, which isn't in the container — leave it unchecked on
  the hosted app.
- **Uploads / outputs** live in the container's temp dir (ephemeral).

## Other hosts
The same `Dockerfile` runs anywhere that takes a container and injects `$PORT`
(Railway, Fly.io, Cloud Run, a VPS). Only `render.yaml` is Render-specific.
