import { useState } from 'react';

/**
 * Where each generated method came from — the first question any reviewer asks.
 *
 * Line numbers here are computed from the text, never reported by a model, which is why
 * they can be shown as facts. The two residues are half the value: Apex with no origin
 * (scaffolding, or invention) and Java with no counterpart (logic that may not have been
 * carried over).
 */
export interface ProvenanceData {
  artifacts: {
    target: string; coverage: number | null;
    links: { apex: string; apex_lines: number[]; java: string; java_lines: number[];
             source_class: string; basis: string; confidence: string }[];
    apex_without_origin: { apex: string; apex_lines: number[] }[];
    java_without_apex: { java: string; source_class: string; java_lines: number[] }[];
  }[];
  summary: { artifacts: number; linked: number; methods: number; coverage: number | null;
             apex_without_origin: number; java_without_apex: number };
}

export default function Provenance({ p }: { p: ProvenanceData | null }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!p || !p.summary.methods) {
    return <div className="tabpanel"><p className="empty">
      Every generated method traced to the Java that produced it, with real line ranges.{' '}
      <em>Nothing yet — the mock provider emits placeholder code with no real origin.</em></p></div>;
  }
  return (
    <div className="tabpanel">
      <div className="rule-hero">
        <div className="rule-score">
          <span className="rule-num num">{p.summary.linked}<span className="rule-den">/{p.summary.methods}</span></span>
          <span className="u-lbl" style={{ margin: 0 }}>generated methods traced to their origin</span>
        </div>
      </div>

      {p.summary.java_without_apex > 0 && (
        <div className="rule-warn">
          <strong>{p.summary.java_without_apex} Java method(s) have no Apex counterpart.</strong>{' '}
          Some are private helpers that were inlined; some are logic that did not make it.
          This is the list to check first.
        </div>
      )}

      {p.artifacts.map((m) => (
        <div key={m.target} className="pv-art">
          <button className="pv-head" onClick={() => setOpen(open === m.target ? null : m.target)}>
            <span className="tw">{open === m.target ? '▾' : '▸'}</span>
            <b>{m.target}</b>
            {m.coverage !== null && <span className="pv-cov num">{m.coverage}% traced</span>}
            <span className="faint">{m.links.length} linked</span>
            {m.java_without_apex.length > 0 &&
              <span className="pv-lost">{m.java_without_apex.length} unmatched</span>}
          </button>
          {open === m.target && (
            <div className="pv-body">
              {m.links.length > 0 && (
                <table className="rule-tbl">
                  <thead><tr><th>Generated</th><th>←</th><th>From</th><th>Basis</th></tr></thead>
                  <tbody>
                    {m.links.map((l, i) => (
                      <tr key={i}>
                        <td><code>{l.apex}</code><span className="rule-id">lines {l.apex_lines[0]}–{l.apex_lines[1]}</span></td>
                        <td className="faint">←</td>
                        <td><code>{l.source_class}.{l.java}</code><span className="rule-id">lines {l.java_lines[0]}–{l.java_lines[1]}</span></td>
                        <td><span className={`chip rule ${l.confidence === 'high' ? 'ch-direct' : 'ch-adapter'}`}>{l.basis}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {m.apex_without_origin.length > 0 && (
                <div className="pv-resid">
                  <span className="u-lbl">Generated with no traceable origin</span>
                  <p className="faint">Scaffolding, or invented — worth a glance either way.</p>
                  {m.apex_without_origin.map((o) => (
                    <code key={o.apex} className="pv-chip">{o.apex}</code>
                  ))}
                </div>
              )}
              {m.java_without_apex.length > 0 && (
                <div className="pv-resid bad">
                  <span className="u-lbl">Java with no Apex counterpart</span>
                  <p className="faint">Check these were meant to disappear.</p>
                  {m.java_without_apex.map((u) => (
                    <code key={u.java} className="pv-chip">{u.source_class}.{u.java}</code>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      <p className="rule-caveat">
        <strong>Line numbers here are facts.</strong> They are computed by locating methods in
        both texts, not reported by a model — asking one to do arithmetic on text it is not
        looking at returns numbers that are plausible and wrong, and a provenance map that is
        confidently wrong is worse than none.
      </p>
    </div>
  );
}
