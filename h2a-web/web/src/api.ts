import type { RunSummary, Ev } from './types';

/** Thrown when preflight refuses the upload — carries the report so the UI can explain. */
export class PreflightError extends Error {
  report: any;
  constructor(message: string, report: any) { super(message); this.report = report; }
}

export async function startRun(form: FormData): Promise<string> {
  const res = await fetch('/api/runs', { method: 'POST', body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const d = body?.detail;
    if (res.status === 422 && d?.preflight) throw new PreflightError(d.message, d.preflight);
    throw new Error(typeof d === 'string' ? d : JSON.stringify(d ?? 'Could not start the migration.'));
  }
  return (await res.json()).run_id as string;
}

/**
 * Live run updates via short-poll — NOT EventSource/SSE.
 *
 * SSE needs one long-lived HTTP connection held open for the whole run. On a locked-
 * down corporate network, proxies/security gateways routinely kill an idle OR simply
 * long-running streaming connection outright (some cap total duration regardless of
 * activity; some fully buffer text/event-stream and never flush mid-response) — and a
 * supervised run can sit quiet at a review gate for minutes waiting on a human, which
 * is exactly when this breaks. Polling only ever makes short, ordinary GET requests —
 * indistinguishable from any other API call — so it keeps working on networks where a
 * persistent stream doesn't survive. The cost (one small GET every ~1.2s) is a good
 * trade for reliability on the enterprise networks this tool actually runs on.
 *
 * Returns a stop() function — call it to cancel polling (mirrors EventSource.close()).
 */
export function openStream(runId: string, onEvent: (ev: Ev) => void, intervalMs = 1200): () => void {
  let stopped = false;
  let seen = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const tick = async () => {
    if (stopped) return;
    try {
      const res = await fetch(`/api/runs/${runId}`);
      if (res.ok) {
        const data = await res.json();
        const events: Ev[] = data.events || [];
        for (; seen < events.length; seen++) onEvent(events[seen]);
        const status = data.status;
        if (status && status !== 'queued' && status !== 'running') {
          onEvent({ type: 'stream_end', status });
          stopped = true;
          return;
        }
      }
      // non-OK response (e.g. a transient proxy hiccup) — just retry next tick
    } catch {
      // network hiccup — retry next tick rather than giving up
    }
    if (!stopped) timer = setTimeout(tick, intervalMs);
  };
  tick();

  return () => { stopped = true; if (timer) clearTimeout(timer); };
}

export async function cancelRun(runId: string): Promise<void> {
  try { await fetch(`/api/runs/${runId}/cancel`, { method: 'POST' }); } catch { /* ignore */ }
}

export async function submitGate(runId: string, decision: unknown): Promise<void> {
  await fetch(`/api/runs/${runId}/gate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(decision),
  });
}

export interface DiffPayload {
  target: string; is_lwc: boolean; source: string; generated: string;
  left_lang: string; right_lang: string; targets: string[];
}
/** Original source + generated output for one target. Works mid-run (including while
 *  paused at a review gate), so code is fetched only when a reviewer opens a file. */
export async function fetchDiff(runId: string, target: string): Promise<DiffPayload> {
  const res = await fetch(`/api/runs/${runId}/diff?target=${encodeURIComponent(target)}`);
  if (!res.ok) throw new Error((await res.text()) || 'could not load code');
  return res.json();
}

/** Re-run Builder + Critic on a single file, without re-running the migration. */
export async function regenerateArtifact(runId: string, target: string, instruction: string): Promise<any> {
  const res = await fetch(`/api/runs/${runId}/regenerate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target, instruction }),
  });
  if (!res.ok) throw new Error((await res.text()) || 'regenerate failed');
  return (await res.json()).artifact;
}

export async function fetchFiles(runId: string): Promise<{ files: string[]; reports: string[] }> {
  return (await fetch(`/api/runs/${runId}/files`)).json();
}
export async function fetchFile(runId: string, path: string): Promise<string> {
  return (await fetch(`/api/runs/${runId}/file?path=${encodeURIComponent(path)}`)).text();
}
export async function fetchReport(runId: string, name: string): Promise<{ html: string; raw: string }> {
  return (await fetch(`/api/runs/${runId}/report?name=${encodeURIComponent(name)}`)).json();
}
export async function askCopilot(runId: string, message: string): Promise<{ answer: string; events?: Ev[] }> {
  const res = await fetch(`/api/runs/${runId}/copilot`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function health(): Promise<boolean> {
  try { return (await (await fetch('/api/health')).json()).ok === true; } catch { return false; }
}

export interface ClientConfig { hosted: boolean; default_provider: string; }
export async function getConfig(): Promise<ClientConfig> {
  try { return await (await fetch('/api/config')).json(); } catch { return { hosted: false, default_provider: 'mock' }; }
}
export function packageUrl(runId: string): string { return `/api/runs/${runId}/package`; }

/** Past runs, newest first — live ones plus history recovered from disk. */
export interface QueueState { active: number; waiting: number; capacity: number; }

export async function listRuns(): Promise<{ runs: RunSummary[]; queue: QueueState | null }> {
  const r = await fetch('/api/runs');
  if (!r.ok) return { runs: [], queue: null };
  const d = await r.json();
  return { runs: d.runs || [], queue: d.queue || null };
}


// ── accounts ──────────────────────────────────────────────────────────────────

export interface Me {
  required: boolean;
  signup_open: boolean;
  has_users: boolean;
  demo: boolean;          // this instance offers one-click demo sign-in
  user: { id: string; email: string; name: string; role: string; created?: number } | null;
}

async function post(path: string, body: unknown) {
  const r = await fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

export async function me(): Promise<Me> {
  const r = await fetch('/api/auth/me');
  if (!r.ok) return { required: false, signup_open: false, has_users: false, demo: false, user: null };
  return r.json();
}

export const login = (email: string, password: string) =>
  post('/api/auth/login', { email, password }).then((d) => d.user);

export const signup = (email: string, password: string) =>
  post('/api/auth/signup', { email, password }).then((d) => d.user);

export const logout = () => post('/api/auth/logout', {});

/** One-click sign-in to the shared demo account, where a deployment enables it. */
export const demoLogin = () => post('/api/auth/demo', {}).then((d) => d.user);

// ── provider credentials ──────────────────────────────────────────────────────

export interface StoredKey { provider: string; hint: string; updated: number; }
export interface KeyState {
  available: boolean; reason: string;
  server: Record<string, boolean>;   // providers the server itself can fall back to
  keys: StoredKey[];
}

export async function fetchKeys(): Promise<KeyState> {
  const r = await fetch('/api/keys');
  if (!r.ok) return { available: false, reason: '', server: {}, keys: [] };
  return r.json();
}

export async function saveKey(provider: string, key: string) {
  const r = await fetch(`/api/keys/${provider}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || 'Could not save that key.');
  return d;
}

export const removeKey = (provider: string) =>
  fetch(`/api/keys/${provider}`, { method: 'DELETE' });
