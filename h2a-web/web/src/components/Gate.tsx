import { useState } from 'react';
import type { GateState } from '../useRun';
import { submitGate } from '../api';
import Discovery from './Discovery';

export function cxBadge(cx?: string) {
  if (!cx) return null;
  return <span className={`badge cx-${cx.toLowerCase()}`}>{cx} complexity</span>;
}

export default function Gate({ runId, gate, onClosed }: { runId: string; gate: GateState; onClosed: () => void }) {
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const send = async (decision: unknown) => {
    setBusy(true);
    try { await submitGate(runId, decision); onClosed(); } finally { setBusy(false); }
  };

  return (
    <div className="overlay">
      <div className={`gate-card ${gate.gate === 'discovery' ? 'wide' : ''}`}>
        <div className="gate-head">
          <div>
            <span className="gate-pill">⏸ Review gate</span>
            <h2>{gate.gate === 'discovery' ? 'Review what the AI found in your codebase'
              : gate.gate === 'plan' ? 'Approve the migration plan' : 'Review the generated code'}</h2>
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
              <p className="gate-note">Review each artifact. Approve everything, or type feedback on any file and send it back — the Builder regenerates it addressing your note, the Critic re-reviews, then you review again.</p>
              {(gate.artifacts || []).map((a: any) => {
                const kind = a.is_lwc ? 'LWC' : (a.apex_pattern || 'Apex');
                return (
                  <div className="a-card" key={a.target_name} style={{ background: 'transparent' }}>
                    <div className="a-head" style={{ cursor: 'default' }}>
                      <span className="a-name">{a.target_name} · {kind}</span>
                      <span className={`badge ${a.status === 'accepted' ? 'b-accepted' : 'b-needs'}`}>{a.status}</span>
                    </div>
                    <div style={{ padding: '0 14px 12px' }}>
                      {(a.findings || []).length > 0 && (
                        <ul className="findings">
                          {a.findings.map((f: any, i: number) => (
                            <li className={`fnd ${f.severity === 'ERROR' ? 'err' : 'warn'}`} key={i}>
                              <span className="sev">{f.severity}</span><span className="cat">{f.category}</span>{f.message}
                              {f.suggestion && <div className="fix">💡 {f.suggestion}</div>}
                            </li>
                          ))}
                        </ul>
                      )}
                      <textarea placeholder="Send back with feedback (leave empty to accept)…"
                        value={feedback[a.target_name] || ''}
                        onChange={(e) => setFeedback({ ...feedback, [a.target_name]: e.target.value })} />
                    </div>
                  </div>
                );
              })}
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
            <>
              <button className="btn" disabled={busy} onClick={() => {
                const fb: Record<string, string> = {};
                Object.entries(feedback).forEach(([k, v]) => { if (v.trim()) fb[k] = v.trim(); });
                if (!Object.keys(fb).length) send({ action: 'approve' }); else send({ action: 'rework', feedback: fb });
              }}>↺ Send back & rebuild</button>
              <button className="btn primary" disabled={busy} onClick={() => send({ action: 'approve' })}>Approve all ▶</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
