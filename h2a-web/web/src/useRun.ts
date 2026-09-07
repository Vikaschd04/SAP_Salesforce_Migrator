import { useCallback, useRef, useState } from 'react';
import type { Artifact, Comprehension, Decision, Ev, LedgerRow, PlanItem, RuleLedger, Characterization, StageStatus } from './types';
import type { SignOffData } from './components/SignOff';
import { openStream } from './api';

export const STAGES = [
  { id: 'analyze', n: 'Analyze' },
  { id: 'comprehend', n: 'Comprehend' },
  { id: 'plan', n: 'Plan' },
  { id: 'build', n: 'Build + Critic' },
  { id: 'reconcile', n: 'Reconcile' },
  { id: 'verify', n: 'Verify' },
] as const;

const LAST_RUN = 'h2a-last-run';

export interface FeedItem { id: number; ts: string; agent: string; msg: string; kind: string; }
export interface GateState { gate: 'discovery' | 'plan' | 'build'; items?: PlanItem[];
  artifacts?: any[]; blast?: any; discovery?: any; }

export interface RunState {
  runId: string | null;
  status: 'idle' | 'running' | 'complete' | 'error';
  elapsed: string;
  stages: Record<string, { status: StageStatus; detail?: string }>;
  feed: FeedItem[];
  plan: PlanItem[];
  comprehensions: Comprehension[];
  artifacts: Artifact[];
  decisions: Decision[];
  ledger: LedgerRow[];
  ledgerSummary: Record<string, number>;
  ruleLedger: RuleLedger | null;
  signoff: SignOffData | null;
  characterization: Characterization | null;
  radar: any | null;
  triage: any | null;
  provenance: any | null;
  /** Which migration this run is. Named by the engine, not assumed here. */
  pipeline: { id: string; source: string; target: string; language?: string } | null;
  alignment: any | null;
  forecast: any | null;
  orgfit: any | null;
  blast: any | null;
  replay: any | null;
  gate: GateState | null;
  discovery: any | null;
  errorMsg: string;
  cost: any | null;
  tokens: { input: number; output: number; cache_read: number } | null;
}


/**
 * Runs recorded before the `apex_` and `java_` keys became `target_` and `source_`.
 *
 * A completed migration's report outlives the process that produced it — the API serves
 * finished runs back from disk, and those stored events still carry the old key names.
 * Without this, the Provenance and Alignment panels would go blank for every run that
 * predates the rename, which is precisely the history a customer is most likely to open.
 *
 * Deliberately conservative: a key is only rewritten when the new name is absent, so this
 * is a strict no-op on anything the current engine emits. The bare `apex`/`java` fields
 * are rewritten only alongside their `_lines` sibling, so an unrelated field that happens
 * to be called `java` somewhere else in the payload is left alone.
 */
const LEGACY_KEYS: Record<string, string> = {
  apex_without_origin: 'target_without_origin',
  java_without_apex: 'source_without_target',
  apex_lines: 'target_lines',
  java_lines: 'source_lines',
  apex_method: 'target_method',
  java_method: 'source_method',
};

function upgradeKeys(node: any): any {
  if (Array.isArray(node)) return node.map(upgradeKeys);
  if (!node || typeof node !== 'object') return node;

  // `apex` and `java` on their own are too generic to rename blindly, so they count as
  // legacy only when the `_lines` sibling identifies the row as a provenance link.
  const rename: Record<string, string> = { ...LEGACY_KEYS };
  if ('apex' in node && 'apex_lines' in node) rename.apex = 'target';
  if ('java' in node && 'java_lines' in node) rename.java = 'source';

  const out: any = {};
  for (const [k, v] of Object.entries(node)) {
    const to = rename[k];
    out[to && !(to in node) ? to : k] = upgradeKeys(v);
  }
  return out;
}


const initial = (): RunState => ({
  runId: null, status: 'idle', elapsed: '', stages: {}, feed: [], plan: [],
  comprehensions: [], artifacts: [], decisions: [], ledger: [], ledgerSummary: {}, ruleLedger: null, signoff: null, characterization: null, radar: null, triage: null, provenance: null, pipeline: null,
  alignment: null, forecast: null, orgfit: null, blast: null, replay: null, gate: null,
  discovery: null, errorMsg: '', cost: null, tokens: null,
});

const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

export function useRun() {
  const [state, setState] = useState<RunState>(initial);
  const stopRef = useRef<(() => void) | null>(null);   // cancels the poller (see openStream)
  const feedId = useRef(0);
  const tsRef = useRef('');

  const push = (set: (s: RunState) => RunState) => setState((s) => set(s));
  const feed = (s: RunState, agent: string, msg: string, kind = 'system'): RunState => ({
    ...s, feed: [...s.feed, { id: feedId.current++, ts: tsRef.current, agent, msg, kind }],
  });

  const handle = useCallback((ev: Ev) => {
    if (ev.ts != null) tsRef.current = `${ev.ts}s`;
    setState((s) => {
      s = { ...s, elapsed: tsRef.current };
      switch (ev.type) {
        case 'stage': {
          const st: StageStatus = ev.status === 'done' ? 'done' : 'active';
          s = { ...s, stages: { ...s.stages, [ev.name]: { status: st, detail: ev.detail } } };
          return feed(s, cap(ev.name), (ev.status === 'done' ? '✓ ' : '▶ ') + cap(ev.name) + (ev.detail ? ' — ' + ev.detail : ''), 'system');
        }
        case 'analyzed':
          return feed(s, 'Analyzer', `${ev.backend_classes} backend classes · ${ev.frontend_components} components · ${ev.objects} objects · ${ev.domains?.length ?? 0} domains`, 'plan');
        case 'comprehend': {
          const c = ev as unknown as Comprehension;
          const n = c.business_rules?.length ?? 0;
          s = { ...s, comprehensions: [...s.comprehensions, c] };
          return feed(s, 'Comprehender', `${c.cls} (${c.layer})` + (c.purpose ? ' — ' + c.purpose : '') + (n ? ` · ${n} rule${n === 1 ? '' : 's'}` : ''), 'plan');
        }
        case 'plan':
          s = { ...s, plan: ev.items as PlanItem[] };
          return feed(s, 'Planner', `${(ev.items as PlanItem[]).length} target(s) planned`, 'plan');
        case 'artifact': {
          if (ev.status === 'building') {
            const why = ev.native_recommendation ? ` · flag: consider ${ev.native_recommendation}` : '';
            return feed(s, 'Builder', `building ${ev.target_name} as ${ev.apex_pattern || 'Apex'}` + (ev.sources?.length ? ` from ${ev.sources.join(', ')}` : '') + why, 'build');
          }
          const a = ev as unknown as Artifact;
          const others = s.artifacts.filter((x) => x.target_name !== a.target_name);
          s = { ...s, artifacts: [...others, a] };
          const flag = a.review_flags?.length ? ' · flagged' : '';
          if ((a as any).cached) {
            return feed(s, 'Builder', `${a.target_name} — unchanged, reused from the last run`, 'system');
          }
          return feed(s, 'Critic', `${a.target_name} → ${a.status}${a.reworked ? ' (reworked)' : ''}${flag} (${a.findings ?? 0} finding${a.findings === 1 ? '' : 's'})`, a.review_flags?.length ? 'flag' : 'build');
        }
        case 'incremental':
          if (ev.enabled && (ev.comprehensions || ev.artifacts)) {
            return feed(s, 'Incremental',
              `reused ${ev.comprehensions} comprehension(s) and ${ev.artifacts} artifact(s) unchanged `
              + `since the last run — that AI work was skipped entirely`, 'plan');
          }
          return s;
        case 'critic_repair':
          return feed(s, 'Critic ⇄ Builder', `${ev.target_name}: ${ev.errors} error(s) → repaired & re-reviewed` + (ev.categories?.length ? ` [${ev.categories.join(', ')}]` : ''), 'flag');
        case 'reconcile': {
          const nf = ev.added_fields?.length ?? 0, no = ev.added_objects?.length ?? 0;
          return (nf || no) ? feed(s, 'Reconciler', `schema augmented — +${no} object(s), +${nf} field(s)`, 'flag') : s;
        }
        case 'decision':
          return { ...s, decisions: [...s.decisions, { agent: ev.agent, action: ev.action, detail: ev.detail }] };
        // Which migration this run is, sent before the first gate. Without this the
        // event arrived and was dropped by the switch, `pipeline` stayed null, and every
        // screen fell back to naming Salesforce — including a review gate on an
        // Adobe→Hybris run. Emitting it was only half the fix. [1.62]
        case 'pipeline':
          return { ...s, pipeline: { id: ev.id, source: ev.source, target: ev.target,
                                     language: ev.language } };
        case 'radar':
          return { ...s, radar: ev };
        case 'discovery_meta':
          return s;
        case 'discovery': {
          const sum = ev.summary || {};
          s = { ...s, discovery: ev };
          return feed(s, 'Scanner', `mapped ${sum.files_scanned ?? 0} files · ${sum.classes ?? 0} classes · `
            + `${sum.components ?? 0} components · ${sum.objects ?? 0} data objects across ${sum.domains ?? 0} domains`, 'plan');
        }
        case 'gate_open':
          return { ...s, gate: { gate: ev.gate, items: ev.items, artifacts: ev.artifacts,
                                blast: ev.blast || s.blast, discovery: ev } };
        case 'gate_closed':
          s = { ...s, gate: null };
          return feed(s, 'Reviewer', `gate ${ev.gate} → ${ev.action}`, 'system');
        case 'run_complete':
          return { ...s, status: 'complete', ledger: ev.ledger || [], ledgerSummary: ev.ledger_summary || {},
            decisions: ev.decisions || s.decisions, cost: ev.cost || null, tokens: ev.tokens || null,
            ruleLedger: ev.rule_ledger || null,
            signoff: ev.signoff || null,
            characterization: ev.characterization || null,
            radar: ev.radar || s.radar, triage: ev.triage || null,
            pipeline: ev.pipeline || s.pipeline,
            provenance: upgradeKeys(ev.provenance) || null,
            alignment: upgradeKeys(ev.alignment) || null,
            forecast: ev.forecast || s.forecast, orgfit: ev.orgfit || s.orgfit,
            blast: ev.blast || null, replay: ev.replay || null };
        case 'cancelled':
          return feed({ ...s, status: 'idle' }, 'system', 'Run stopped', 'system');
        case 'error':
          return feed({ ...s, status: 'error', errorMsg: ev.message || 'The migration failed.' },
            'Error', ev.message || 'run failed', 'error');
        case 'stream_end':
          return s.status === 'running' ? { ...s, status: (ev.status as any) || 'complete' } : s;
        default:
          return s;
      }
    });
  }, []);

  const begin = useCallback((runId: string) => {
    stopRef.current?.();
    feedId.current = 0; tsRef.current = '';
    // Remembered so a refresh, a dropped connection, or a closed tab can rejoin. The
    // backend already retains every event and replays from any index; the client simply
    // never kept the id, so a reload orphaned a migration the server was still running.
    try { localStorage.setItem(LAST_RUN, runId); } catch { /* private mode */ }
    setState({ ...initial(), runId, status: 'running' });
    stopRef.current = openStream(runId, handle);
  }, [handle]);

  const reset = useCallback(() => {
    stopRef.current?.();
    try { localStorage.removeItem(LAST_RUN); } catch { /* private mode */ }
    setState(initial());
  }, []);

  /** Rejoin the last run on mount, if the server still knows about it. */
  const rejoin = useCallback(async () => {
    let id: string | null = null;
    try { id = localStorage.getItem(LAST_RUN); } catch { return; }
    if (!id) return;
    const r = await fetch(`/api/runs/${id}`).catch(() => null);
    if (!r || !r.ok) {                       // gone, or belongs to someone else now
      try { localStorage.removeItem(LAST_RUN); } catch { /* ignore */ }
      return;
    }
    begin(id);
  }, [begin]);
  const closeGate = useCallback(() => setState((s) => ({ ...s, gate: null })), []);
  // Let the Copilot inject events (e.g. a rework artifact) so the feed / Artifacts /
  // Diff update exactly as they would from the live stream.
  const injectEvents = useCallback((evs: Ev[]) => { evs.forEach(handle); }, [handle]);

  return { state, begin, reset, rejoin, closeGate, injectEvents };
}
