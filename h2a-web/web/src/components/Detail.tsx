import { lazy, Suspense, useEffect, useState } from 'react';
import type { Artifact, Comprehension, Decision, LedgerRow, PlanItem } from '../types';
import { fetchFile, fetchFiles, fetchReport, packageUrl } from '../api';
import { cxBadge } from './Gate';
import PipelineFlow from './PipelineFlow';
import Discovery from './Discovery';
import ArtifactReview from './ArtifactReview';
import type { StageStatus } from '../types';

const Diff = lazy(() => import('./Diff'));

type Tab = 'flow' | 'discovery' | 'plan' | 'understanding' | 'artifacts' | 'diff' | 'files' | 'reports' | 'audit';

interface Props {
  runId: string | null; status: string;
  stages: Record<string, { status: StageStatus; detail?: string }>;
  plan: PlanItem[]; comprehensions: Comprehension[]; artifacts: Artifact[];
  decisions: Decision[]; ledger: LedgerRow[]; ledgerSummary: Record<string, number>;
  discovery: any | null;
}

export default function Detail(p: Props) {
  const [tab, setTab] = useState<Tab>('flow');
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [files, setFiles] = useState<string[]>([]);
  const [reports, setReports] = useState<string[]>([]);
  const [sel, setSel] = useState<string>('');
  const [code, setCode] = useState<string>('');
  const [reportHtml, setReportHtml] = useState<string>('');

  useEffect(() => {
    if (p.status === 'complete' && p.runId) {
      fetchFiles(p.runId).then((r) => { setFiles(r.files || []); setReports(r.reports || []); });
    }
  }, [p.status, p.runId]);

  const openReport = async (name: string) => {
    if (!p.runId) return;
    setSel(name);
    try { setReportHtml((await fetchReport(p.runId, name)).html); } catch { setReportHtml('<p class="empty">(unavailable)</p>'); }
  };
  const openFile = async (path: string) => {
    if (!p.runId) return;
    setSel(path);
    try { setCode(await fetchFile(p.runId, path)); } catch { setCode('// could not load'); }
  };
  const toggle = (name: string) => setOpen((s) => { const n = new Set(s); n.has(name) ? n.delete(name) : n.add(name); return n; });

  const TABS: [Tab, string][] = [['flow', 'Flow'], ['discovery', 'Discovery'], ['plan', 'Plan'], ['understanding', 'Understanding'], ['artifacts', 'Artifacts'], ['diff', 'Diff'], ['files', 'Files'], ['reports', 'Reports'], ['audit', 'Audit']];

  return (
    <section className="panel">
      <div className="tabs">
        {TABS.map(([id, label]) => (
          <button key={id} className={`tab ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {tab === 'flow' && <PipelineFlow stages={p.stages} artifacts={p.artifacts} status={p.status} />}

      {tab === 'discovery' && (
        <div className="tabpanel">
          {p.discovery ? <Discovery d={p.discovery} />
            : <p className="empty">The repository scan — file tree, architecture, every class and the data model — appears here as soon as analysis completes.</p>}
        </div>
      )}

      {tab === 'plan' && (
        <div className="tabpanel">
          {p.plan.length === 0 ? <p className="empty">The Planner will list every target here — converted, skipped, or flagged, and why.</p> : (
            <table><thead><tr><th>Target</th><th>Type</th><th>Decision</th><th>Review flag</th><th>Why</th><th>From</th></tr></thead>
              <tbody>{p.plan.map((it) => (
                <tr key={it.target_name}>
                  <td><code>{it.target_name}</code></td><td>{it.layer}</td>
                  <td><span className={`badge ${it.decision === 'Skip' ? 'b-skip' : 'b-convert'}`}>{it.decision}</span></td>
                  <td>{it.native_recommendation && <span className="badge b-flag">consider {it.native_recommendation}</span>}</td>
                  <td className="dim">{it.rationale}</td>
                  <td className="dim">{(it.sources || []).join(', ')}</td>
                </tr>
              ))}</tbody></table>
          )}
        </div>
      )}

      {tab === 'understanding' && (
        <div className="tabpanel">
          {p.comprehensions.length === 0 ? <p className="empty">As the Comprehender reads each class, its purpose, business rules, risks, and complexity appear here.</p> :
            p.comprehensions.map((c) => (
              <div className="u-card" key={c.cls}>
                <div className="u-head"><span className="u-name">{c.cls}</span><span className="badge b-skip">{c.layer}</span>{cxBadge(c.complexity)}</div>
                {c.purpose && <p className="u-purpose">{c.purpose}</p>}
                {sec('Business rules to preserve', c.business_rules)}
                {sec('⚠ Migration risks', c.migration_risks, 'u-risks')}
                {sec('Data it queries', c.queries)}
                {sec('Depends on', c.dependencies)}
              </div>
            ))}
        </div>
      )}

      {tab === 'artifacts' && (
        <div className="tabpanel">
          {p.artifacts.length === 0
            ? <p className="empty">Generated Apex + LWC appear here. Open any file to see the code, compare it with the SAP source, read the Critic findings — and regenerate it if it looks wrong.</p>
            : p.artifacts.map((a) => (
              <ArtifactReview key={a.target_name} runId={p.runId!} art={a} />
            ))}
        </div>
      )}

      {tab === 'diff' && (
        <div className="tabpanel">
          {p.status !== 'complete' || p.artifacts.length === 0
            ? <p className="empty">The source ↔ generated side-by-side diff is available once the run completes.</p>
            : <Suspense fallback={<p className="empty">Loading editor…</p>}>
                <Diff runId={p.runId!} targets={p.artifacts.map((a) => a.target_name)} />
              </Suspense>}
        </div>
      )}

      {tab === 'files' && (
        <div className="tabpanel">
          <div className="files-layout">
            <ul className="filelist">
              {files.length === 0 ? <li className="empty">Generated files appear after the run.</li> :
                files.map((f) => <li key={f} className={`${sel === f ? 'sel' : ''} ${f.includes('/lwc/') ? 'lwc' : ''}`} onClick={() => openFile(f)}>{f}</li>)}
            </ul>
            <pre className="code-view">{code || 'Select a file to view it.'}</pre>
          </div>
        </div>
      )}

      {tab === 'reports' && (
        <div className="tabpanel">
          {Object.keys(p.ledgerSummary).length > 0 && (
            <div className="chips-row">
              {Object.entries(p.ledgerSummary).map(([k, v]) => <span key={k} className={`chip ${k}`}>{v} {k}</span>)}
            </div>
          )}
          <div className="chips-row">
            {reports.map((r) => <button key={r} className={`btn-mini ${sel === r ? 'sel' : ''}`} onClick={() => openReport(r)}>{r.replace('.md', '').replace(/_/g, ' ')}</button>)}
            {p.runId && <a className="btn-mini" href={packageUrl(p.runId)}>⬇ Download SFDX package</a>}
          </div>
          {reportHtml ? <div className="md" dangerouslySetInnerHTML={{ __html: reportHtml }} /> : <p className="empty">Reports appear when the run completes. Pick one above.</p>}
        </div>
      )}

      {tab === 'audit' && (
        <div className="tabpanel">
          {p.decisions.length === 0 ? <p className="empty">Every agent decision streams here in order — the live audit trail.</p> :
            <ol className="audit">{p.decisions.map((d, i) => (
              <li className="au-row" key={i}><span className="au-agent">{d.agent}</span> <span className="au-act">{d.action}</span> <span>{d.detail}</span></li>
            ))}</ol>}
        </div>
      )}
    </section>
  );
}

function sec(label: string, arr?: string[], cls = '') {
  if (!arr || arr.length === 0) return null;
  return <div className="u-sec"><span className="u-lbl">{label}</span><ul className={cls}>{arr.map((x, i) => <li key={i}>{x}</li>)}</ul></div>;
}
