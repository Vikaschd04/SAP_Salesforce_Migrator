import { useMemo, useState } from 'react';

/**
 * Hybris patterns that become hazards on Salesforce.
 *
 * Shown at the Discovery gate, beside the preflight report — before a plan is approved
 * and before anything is generated. That placement is the point: fixing a
 * FlexibleSearch-in-loop in the Java is one change, while fixing the SOQL-in-loop it
 * becomes is two.
 */

export interface RadarFinding {
  id: string; rule: string; severity: 'critical' | 'high' | 'medium' | 'info';
  file: string; line: number; source_class: string;
  hazard: string; fix: string; snippet: string;
}
export interface RadarData {
  findings: RadarFinding[];
  summary: {
    total: number; critical: number; high: number; medium: number; info: number;
    files_affected: number; by_rule: Record<string, number>;
  };
}

const TITLES: Record<string, string> = {
  SOQL_IN_LOOP: 'FlexibleSearch inside a loop',
  DML_IN_LOOP: 'Save inside a loop',
  DAO_CALL_IN_LOOP: 'DAO call inside a loop',
  QUERY_NO_LIMIT: 'Unbounded query',
  TRANSACTIONAL: '@Transactional boundary',
  THREADING: 'Threads or async execution',
  STATIC_MUTABLE_STATE: 'Mutable static state',
  INTERCEPTOR: 'Interceptor chain',
  SESSION_SCOPED_BEAN: 'Session-scoped bean',
  IMPEX_VOLUME: 'Large ImpEx load',
  CRONJOB_CONCURRENCY: 'Cronjob concurrency',
};
const title = (r: string) => TITLES[r] || r.replace(/_/g, ' ').toLowerCase();
const LEVELS = ['critical', 'high', 'medium', 'info'] as const;

export default function Radar({ r }: { r: RadarData | null }) {
  const [only, setOnly] = useState<string>('all');
  const s = r?.summary;
  const rows = useMemo(
    () => (r?.findings || []).filter((f) => only === 'all' || f.severity === only),
    [r, only],
  );

  if (!r || !s || s.total === 0) {
    return (
      <div className="rd-clean">
        ✓ No Hybris-specific migration hazards found — no queries or saves inside loops,
        no <code>@Transactional</code> boundaries, no session-scoped state.
      </div>
    );
  }

  return (
    <section className="rd">
      <header className="rd-head">
        <div>
          <b>{s.total} migration hazard{s.total === 1 ? '' : 's'}</b> across {s.files_affected} file
          {s.files_affected === 1 ? '' : 's'}
          <p>Found in your source by static analysis — no AI, no org, nothing sent anywhere.</p>
        </div>
        <div className="rd-counts">
          {LEVELS.map((l) => s[l] ? (
            <button key={l} className={`rd-pill ${l} ${only === l ? 'sel' : ''}`}
              onClick={() => setOnly(only === l ? 'all' : l)}>
              <b className="num">{s[l]}</b> {l}
            </button>
          ) : null)}
        </div>
      </header>

      {s.critical > 0 && (
        <div className="rd-warn">
          <strong>{s.critical} will fail at realistic volume</strong> — not in a test with three
          records. Cheaper to fix in the Hybris source now than in the Apex afterwards.
        </div>
      )}

      <div className="rd-list">
        {rows.map((f) => (
          <details key={f.id} className={`rd-item ${f.severity}`}>
            <summary>
              <span className={`chip rd-sev ${f.severity}`}>{f.severity}</span>
              <span className="rd-title">{title(f.rule)}</span>
              <code className="rd-loc">{f.file.split('/').slice(-1)[0]}:{f.line}</code>
            </summary>
            <div className="rd-body">
              {f.snippet && <pre className="rd-snippet">{f.snippet}</pre>}
              <p><b>On Salesforce:</b> {f.hazard}</p>
              <p className="rd-fix"><b>Fix:</b> {f.fix}</p>
              <p className="rd-path faint mono">{f.file}</p>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}
