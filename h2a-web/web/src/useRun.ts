import { useCallback, useRef, useState } from 'react';
import type { Artifact, Comprehension, Decision, Ev, LedgerRow, PlanItem, StageStatus } from './types';
import { openStream } from './api';

export const STAGES = [
  { id: 'analyze', n: 'Analyze' },
  { id: 'comprehend', n: 'Comprehend' },
  { id: 'plan', n: 'Plan' },
  { id: 'build', n: 'Build + Critic' },
  { id: 'reconcile', n: 'Reconcile' },
  { id: 'verify', n: 'Verify' },
] as const;

export interface FeedItem { id: number; ts: string; agent: string; msg: string; kind: string; }
export interface GateState { gate: 'plan' | 'build'; items?: PlanItem[]; artifacts?: any[]; }

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
  gate: GateState | null;
}

const initial = (): RunState => ({
  runId: null, status: 'idle', elapsed: '', stages: {}, feed: [], plan: [],
  comprehensions: [], artifacts: [], decisions: [], ledger: [], ledgerSummary: {}, gate: null,
});

const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

export function useRun() {
  const [state, setState] = useState<RunState>(initial);
  const esRef = useRef<EventSource | null>(null);
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
          return feed(s, 'Critic', `${a.target_name} → ${a.status}${a.reworked ? ' (reworked)' : ''}${flag} (${a.findings ?? 0} finding${a.findings === 1 ? '' : 's'})`, a.review_flags?.length ? 'flag' : 'build');
        }
        case 'critic_repair':
          return feed(s, 'Critic ⇄ Builder', `${ev.target_name}: ${ev.errors} error(s) → repaired & re-reviewed` + (ev.categories?.length ? ` [${ev.categories.join(', ')}]` : ''), 'flag');
        case 'reconcile': {
          const nf = ev.added_fields?.length ?? 0, no = ev.added_objects?.length ?? 0;
          return (nf || no) ? feed(s, 'Reconciler', `schema augmented — +${no} object(s), +${nf} field(s)`, 'flag') : s;
        }
        case 'decision':
          return { ...s, decisions: [...s.decisions, { agent: ev.agent, action: ev.action, detail: ev.detail }] };
        case 'gate_open':
          return { ...s, gate: { gate: ev.gate, items: ev.items, artifacts: ev.artifacts } };
        case 'gate_closed':
          s = { ...s, gate: null };
          return feed(s, 'Reviewer', `gate ${ev.gate} → ${ev.action}`, 'system');
        case 'run_complete':
          return { ...s, status: 'complete', ledger: ev.ledger || [], ledgerSummary: ev.ledger_summary || {}, decisions: ev.decisions || s.decisions };
        case 'cancelled':
          return feed({ ...s, status: 'idle' }, 'system', 'Run stopped', 'system');
        case 'error':
          return feed({ ...s, status: 'error' }, 'Error', ev.message || 'run failed', 'error');
        case 'stream_end':
          return s.status === 'running' ? { ...s, status: (ev.status as any) || 'complete' } : s;
        default:
          return s;
      }
    });
  }, []);

  const begin = useCallback((runId: string) => {
    esRef.current?.close();
    feedId.current = 0; tsRef.current = '';
    setState({ ...initial(), runId, status: 'running' });
    esRef.current = openStream(runId, handle);
  }, [handle]);

  const reset = useCallback(() => { esRef.current?.close(); setState(initial()); }, []);
  const closeGate = useCallback(() => setState((s) => ({ ...s, gate: null })), []);
  // Let the Copilot inject events (e.g. a rework artifact) so the feed / Artifacts /
  // Diff update exactly as they would from the live stream.
  const injectEvents = useCallback((evs: Ev[]) => { evs.forEach(handle); }, [handle]);

  return { state, begin, reset, closeGate, injectEvents };
}
