import { useState } from 'react';
import { fetchDiff, regenerateArtifact, type DiffPayload } from '../api';
import BlastRadius, { type BlastData } from './BlastRadius';

type Pane = 'generated' | 'compare' | 'findings' | 'details';

/**
 * Full review of ONE generated file: the code, a side-by-side comparison against the
 * original SAP source, every Critic finding with its suggested fix, and what the Builder
 * mapped — plus the ability to regenerate just this file (no full re-run).
 */
export default function ArtifactReview({ runId, art, onUpdated , blast }:
  { runId: string; art: any; blast?: BlastData | null; onUpdated?: (a: any) => void }) {
  const [open, setOpen] = useState(false);
  const [pane, setPane] = useState<Pane>('generated');
  const [diff, setDiff] = useState<DiffPayload | null>(null);
  const [loadErr, setLoadErr] = useState('');
  const [instruction, setInstruction] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const failed = art.failed || art.status === 'error';
  // Gate payloads carry `findings` as an array; live artifact events carry a count in
  // `findings` plus the array in `findings_detail`. Accept either shape.
  const findings: any[] = Array.isArray(art.findings_detail) ? art.findings_detail
    : Array.isArray(art.findings) ? art.findings : [];
  const errCount = findings.filter((f) => f.severity === 'ERROR').length;

  const load = async () => {
    if (diff || loadErr) return;
    try { setDiff(await fetchDiff(runId, art.target_name)); }
    catch (e: any) { setLoadErr(e.message || 'could not load code'); }
  };
  const expand = () => { const n = !open; setOpen(n); if (n) load(); };

  const regenerate = async () => {
    setBusy(true); setMsg('');
    try {
      const updated = await regenerateArtifact(runId, art.target_name, instruction);
      setDiff(null); setLoadErr(''); setInstruction('');
      onUpdated?.(updated);
      setMsg(`Regenerated — now ${updated.status} with ${updated.findings ?? 0} finding(s).`);
      await load();
    } catch (e: any) { setMsg('⚠ ' + (e.message || 'regenerate failed')); }
    finally { setBusy(false); }
  };

  const kind = art.is_lwc ? 'LWC' : (art.apex_pattern || 'Apex');
  const PANES: [Pane, string][] = [
    ['generated', 'Generated code'], ['compare', 'Compare with source'],
    ['findings', `Findings (${findings.length})`], ['details', 'What was mapped'],
  ];

  return (
    <div className={`a-card ${failed ? 'failed' : ''}`}>
      <div className="a-head" onClick={expand}>
        <span className="tw">{open ? '▾' : '▸'}</span>
        <span className="a-name">{art.target_name}</span>
        <span className={`badge ${art.is_lwc ? 'b-lwc' : 'b-skip'}`}>{kind}</span>
        <span className={`badge ${failed ? 'b-err' : art.status === 'accepted' ? 'b-accepted' : 'b-needs'}`}>
          {failed ? 'failed' : art.status}
        </span>
        {art.cached && <span className="badge b-cached" title="Unchanged since the last run — reused, no AI call">↻ reused</span>}
        {errCount > 0 && <span className="badge b-err">{errCount} error{errCount === 1 ? '' : 's'}</span>}
        {(art.review_flags || []).length > 0 && !failed && <span className="badge b-flag">flagged</span>}
        <span className="a-count">{findings.length} finding{findings.length === 1 ? '' : 's'}</span>
      </div>

      {failed && (
        <div className="err-banner">
          <b>This file could not be generated automatically.</b>{' '}
          {(art.review_flags || [])[0] || 'The Builder failed on this target.'}
          {' '}Add an instruction below and regenerate, or approve to keep the TODO stub for manual migration.
        </div>
      )}

      {open && (
        <div className="a-body">
          <div className="pane-tabs">
            {PANES.map(([id, label]) => (
              <button key={id} className={`btn-mini ${pane === id ? 'sel' : ''}`}
                onClick={() => setPane(id)}>{label}</button>
            ))}
          </div>

          {pane === 'generated' && (
            loadErr ? <p className="empty">{loadErr}</p>
              : !diff ? <p className="empty">Loading code…</p>
                : <pre className="code-view sm">{diff.generated || '(empty)'}</pre>
          )}

          {pane === 'compare' && (
            loadErr ? <p className="empty">{loadErr}</p>
              : !diff ? <p className="empty">Loading code…</p>
                : (
                  <div className="cmp">
                    <div>
                      <div className="cmp-h">◄ Original {diff.is_lwc ? 'Angular / Spartacus' : 'SAP Hybris (Java)'}</div>
                      <pre className="code-view sm">{diff.source || '(no source captured)'}</pre>
                    </div>
                    <div>
                      <div className="cmp-h">Generated {diff.is_lwc ? 'LWC' : 'Salesforce Apex'} ►</div>
                      <pre className="code-view sm">{diff.generated || '(empty)'}</pre>
                    </div>
                  </div>
                )
          )}

          {pane === 'findings' && (
            <ul className="findings">
              {findings.length === 0 ? <li className="fnd ok">Critic clean — no findings on this file</li>
                : findings.map((f, i) => (
                  <li className={`fnd ${f.severity === 'ERROR' ? 'err' : 'warn'}`} key={i}>
                    <span className="sev">{f.severity}</span><span className="cat">{f.category}</span>{f.message}
                    {f.suggestion && <div className="fix">💡 <b>Suggested fix:</b> {f.suggestion}</div>}
                  </li>
                ))}
            </ul>
          )}

          {pane === 'details' && (
            <>
              {art.mapping_notes && <div className="a-sec"><span className="u-lbl">What the Builder mapped</span>
                <p className="dim" style={{ margin: 0 }}>{art.mapping_notes}</p></div>}
              {!!(art.sources || []).length && <div className="a-sec"><span className="u-lbl">Converted from</span>
                {art.sources.map((s: string, i: number) => <code key={i}>{s}</code>)}</div>}
              {!!(art.sobject_refs || []).length && <div className="a-sec"><span className="u-lbl">Salesforce objects used</span>
                {art.sobject_refs.map((s: string, i: number) => <code key={i}>{s}</code>)}</div>}
              {!!(art.business_rules || []).length && <div className="a-sec"><span className="u-lbl">Business rules preserved</span>
                <ul>{art.business_rules.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></div>}
              {art.is_lwc && !!(art.lwc_parts || []).length && <div className="a-sec"><span className="u-lbl">LWC bundle files</span>
                {art.lwc_parts.map((x: string, i: number) => <code key={i}>{x}</code>)}
                {art.has_controller && <code>+ Apex controller</code>}</div>}
              {!!(art.review_flags || []).length && <div className="a-sec"><span className="u-lbl">Review flags</span>
                <ul>{art.review_flags.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></div>}
            </>
          )}

          <BlastRadius b={blast} />
            <div className="regen">
            <input className="inp" placeholder="Optional: tell the Builder what to change (e.g. “use an fflib Selector and add FLS checks”)…"
              value={instruction} disabled={busy}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') regenerate(); }} />
            <button className="btn" disabled={busy} onClick={regenerate}>
              {busy ? 'Regenerating…' : '↻ Regenerate this file'}
            </button>
          </div>
          {msg && <div className={`regen-msg ${msg.startsWith('⚠') ? 'bad' : 'good'}`}>{msg}</div>}
        </div>
      )}
    </div>
  );
}
