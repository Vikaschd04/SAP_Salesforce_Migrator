import type { Ev } from './types';

export async function startRun(form: FormData): Promise<string> {
  const res = await fetch('/api/runs', { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()).run_id as string;
}

export function openStream(runId: string, onEvent: (ev: Ev) => void): EventSource {
  const es = new EventSource(`/api/runs/${runId}/stream`);
  es.onmessage = (m) => { try { onEvent(JSON.parse(m.data)); } catch { /* ignore */ } };
  return es;
}

export async function submitGate(runId: string, decision: unknown): Promise<void> {
  await fetch(`/api/runs/${runId}/gate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(decision),
  });
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
export function packageUrl(runId: string): string { return `/api/runs/${runId}/package`; }
