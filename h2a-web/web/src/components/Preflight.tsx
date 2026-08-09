/**
 * What we established about the codebase before spending anything on it.
 *
 * Shown two ways: as a rejection on the landing screen (the upload never became a run),
 * and inside the Discovery gate as the first thing a reviewer sees. Both use this, so a
 * refusal and an acceptance are described in the same terms.
 */

export interface PreflightReport {
  verdict: 'ok' | 'warn' | 'reject';
  is_hybris: boolean;
  confidence: number;
  summary: string;
  project: {
    version: string | null; version_source: string | null; extensions: string[];
    java_files: number; xml_files: number; impex_files: number;
    components: number; total_files: number;
  };
  signals: { file: string; why: string }[];
  blockers: string[];
  warnings: string[];
  secrets: { file: string; what: string; line: number }[];
}

export default function Preflight({ r, compact }: { r: PreflightReport; compact?: boolean }) {
  const p = r.project;
  const tone = r.verdict === 'reject' ? 'bad' : r.verdict === 'warn' ? 'warn' : 'good';

  return (
    <section className={`pf ${tone}`}>
      <header className="pf-head">
        <span className="pf-icon">{r.verdict === 'reject' ? '✕' : r.verdict === 'warn' ? '!' : '✓'}</span>
        <div>
          <b>{r.summary}</b>
          {r.is_hybris && (
            <div className="pf-bar" title={`${r.confidence}% confidence`}>
              <span style={{ width: `${r.confidence}%` }} />
            </div>
          )}
        </div>
      </header>

      {r.blockers.length > 0 && (
        <ul className="pf-list bad">
          {r.blockers.map((b, i) => <li key={i}>{b}</li>)}
        </ul>
      )}

      {r.secrets.length > 0 && (
        <div className="pf-block">
          <span className="u-lbl">Credentials found in the upload</span>
          <ul className="pf-list warn">
            {r.secrets.map((s, i) => (
              <li key={i}>
                <code>{s.file}</code> line {s.line} — looks like {s.what}
              </li>
            ))}
          </ul>
          <p className="pf-note">
            These were detected, never read back or stored. Rotate anything real, and
            consider removing them from the archive before uploading again.
          </p>
        </div>
      )}

      {r.warnings.length > 0 && (
        <ul className="pf-list warn">{r.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
      )}

      {!compact && r.is_hybris && (
        <>
          <div className="pf-facts">
            {p.version && <Fact k="Version" v={p.version} />}
            {p.extensions.length > 0 && <Fact k="Extensions" v={p.extensions.join(', ')} />}
            <Fact k="Java" v={String(p.java_files)} />
            {p.components > 0 && <Fact k="Components" v={String(p.components)} />}
            <Fact k="XML" v={String(p.xml_files)} />
            {p.impex_files > 0 && <Fact k="ImpEx" v={String(p.impex_files)} />}
            <Fact k="Files" v={String(p.total_files)} />
          </div>
          {r.signals.length > 0 && (
            <div className="pf-block">
              <span className="u-lbl">How we recognised it</span>
              <ul className="pf-sig">
                {r.signals.map((s, i) => (
                  <li key={i}><span>{s.why}</span><code>{s.file}</code></li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}

const Fact = ({ k, v }: { k: string; v: string }) => (
  <div className="pf-fact"><span>{k}</span><b>{v}</b></div>
);
