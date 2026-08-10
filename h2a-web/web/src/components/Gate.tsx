import { useEffect, useState } from 'react';
import type { GateState } from '../useRun';
import { submitGate } from '../api';
import Discovery from './Discovery';
import ArtifactReview from './ArtifactReview';

export function cxBadge(cx?: string) {
  if (!cx) return null;
  return <span className={`badge cx-${cx.toLowerCase()}`}>{cx} complexity</span>;
}

export default function Gate({ runId, gate, onClosed }: { runId: string; gate: GateState; onClosed: () => void }) {
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  // Local copy so a per-file regenerate updates this screen immediately.
  const [arts, setArts] = useState<any[]>(gate.artifacts || []);
  useEffect(() => { setArts(gate.artifacts || []); }, [gate.artifacts]);

  const send = async (decision: unknown) => {
    setBusy(true);
    try { await submitGate(runId, decision); onClosed(); } finally { setBusy(false); }
  };

  const onUpdated = (updated: any) =>
    setArts((prev) => prev.map((a) => (a.target_name === updated.target_name ? { ...a, ...updated } : a)));

  const failedCount = arts.filter((a) => a.failed || a.status === 'error').length;
  const needsCount = arts.filter((a) => a.status === 'needs_review').length;

  return (
    <div className="overlay">
      <div className={`gate-card ${gate.gate === 'discovery' || gate.gate === 'build' ? 'wide' : ''}`}>
        <div className="gate-head">
          <div>
            <span className="gate-pill">⏸ Review gate</span>
            <h2>{gate.gate === 'discovery' ? 'Review what the AI found in your codebase'
              : gate.gate === 'plan' ? 'Approve the migration plan' : 'Review the generated Salesforce code'}</h2>
          </div>
          <span className="mono faint">run {runId}</span>
        </div>

        <div className="gate-body">
          {gate.gate === 'discovery' ? (
            <>
              <p className="gate-note">This is the AI's complete understanding of your repository — every file it
                scanned, the architecture and dependencies it inferred, each class with its methods, and the data
                model it derived. <b>Nothing has been sent to an LLM yet.</b> Review it, then approve to begin.</p>
              <Discovery d={gate.discovery} />
            </>
          ) : gate.gate === 'plan' ? (
            <>
              <p className="gate-note">Review what each target does and its migration risk, then choose <b>Convert</b> or <b>Skip</b>. Flagged items (e.g. “consider CPQ”) are still converted — the flag is just a review note.</p>
              {(gate.items || []).map((p) => {
                const c = p.comprehension || {};
                const val = overrides[p.target_name] ?? (p.decision === 'Skip' ? 'Skip' : 'Convert');
                return (
                  <div className="g-item" key={p.target_name}>
                    <div className="g-item-head">
                      <span className="a-name">{p.target_name}</span>
                      <span className="badge b-skip">{p.layer}</span>
                      {cxBadge(c.complexity)}
                      {p.native_recommendation && <span className="badge b-flag">consider {p.native_recommendation}</span>}
                      <select value={val} onChange={(e) => setOverrides({ ...overrides, [p.target_name]: e.target.value })}>
                        <option value="Convert">Convert</option>
                        <option value="Skip">Skip</option>
                      </select>
                    </div>
                    {c.purpose && <p className="g-purpose">{c.purpose}</p>}
                    {!!c.business_rules?.length && (
                      <div className="g-meta"><span className="u-lbl">Rules to preserve ({c.business_rules.length})</span>
                        <ul>{c.business_rules.map((r, i) => <li key={i}>{r}</li>)}</ul></div>
                    )}
                    {!!c.migration_risks?.length && (
                      <div className="g-meta g-risk"><span className="u-lbl">⚠ Migration risks</span>
                        <ul>{c.migration_risks.map((r, i) => <li key={i}>{r}</li>)}</ul></div>
                    )}
                    <div className="g-from">from {(p.sources || []).join(', ') || '—'}</div>
                  </div>
                );
              })}
            </>
          ) : (
            <>
              <p className="gate-note">Open any file to see the generated Salesforce code, compare it side-by-side with
                the original SAP source, read every Critic finding, and see exactly what was mapped. If something looks
                wrong, <b>regenerate just that file</b> — you never need to re-run the whole migration.</p>

              {(failedCount > 0 || needsCount > 0) && (
                <div className={`gate-alert ${failedCount ? 'bad' : 'warn'}`}>
                  {failedCount > 0 && <><b>{failedCount} file{failedCount === 1 ? '' : 's'} failed to generate.</b>{' '}</>}
                  {needsCount > 0 && <>{needsCount} file{needsCount === 1 ? '' : 's'} still {needsCount === 1 ? 'has' : 'have'} unresolved Critic errors.{' '}</>}
                  Review {failedCount ? 'them' : 'those'} below and regenerate before approving.
                </div>
              )}

              {arts.map((a) => (
                <ArtifactReview key={a.target_name} runId={runId} art={a} onUpdated={onUpdated}
                  blast={(gate.blast || {})[a.target_name]} />
              ))}
            </>
          )}
        </div>

        <div className="gate-actions">
          {gate.gate === 'discovery' ? (
            <button className="btn primary" disabled={busy} onClick={() => send({ action: 'approve' })}>
              Looks right — continue ▶
            </button>
          ) : gate.gate === 'plan' ? (
            <button className="btn primary" disabled={busy} onClick={() => {
              const ov: Record<string, { decision: string }> = {};
              (gate.items || []).forEach((p) => {
                const cur = overrides[p.target_name]; const orig = p.decision === 'Skip' ? 'Skip' : 'Convert';
                if (cur && cur !== orig) ov[p.target_name] = { decision: cur };
              });
              send({ action: 'approve', overrides: ov });
            }}>Approve plan ▶</button>
          ) : (
            <button className="btn primary" disabled={busy} onClick={() => send({ action: 'approve' })}>
              Approve {arts.length} file{arts.length === 1 ? '' : 's'} &amp; continue ▶
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
