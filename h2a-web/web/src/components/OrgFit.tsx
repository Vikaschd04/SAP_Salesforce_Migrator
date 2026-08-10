/**
 * What the destination org already contains. Reading the destination is what separates
 * "here is a package" from "here is a package that will deploy into *your* org".
 */
export interface OrgFitData {
  connected: boolean; reason: string;
  org: { username: string; api_version: string; is_scratch: boolean; namespaces: string[] } | null;
  existing_custom_objects?: number;
  findings: { kind: string; severity: string; object: string; detail: string; fix: string }[];
  summary: { total: number; collision: number; reusable: number; package: number; headroom: number };
}

export default function OrgFit({ o }: { o: OrgFitData | null }) {
  if (!o) return null;

  if (!o.connected) {
    return (
      <div className="of-none">
        <b>Target org not inspected</b> — {o.reason}. This migration is planned against the
        source alone; connect an org with <code>sf org login web</code> to reconcile against
        what it already contains.
      </div>
    );
  }

  return (
    <section className={`of ${o.summary.total ? 'has' : 'clear'}`}>
      <header className="of-head">
        <div>
          <b>{o.summary.total
            ? `${o.summary.total} target-org issue${o.summary.total === 1 ? '' : 's'}`
            : 'Target org looks clear'}</b>
          <p className="mono">{o.org?.username} · API {o.org?.api_version}
            {o.org?.is_scratch ? ' · scratch' : ''}
            {o.org?.namespaces?.length ? ` · ${o.org.namespaces.join(', ')}` : ''}</p>
        </div>
      </header>
      {o.findings.map((f, i) => (
        <details key={i} className={`of-item ${f.severity}`}>
          <summary>
            <span className={`chip of-kind ${f.kind}`}>{f.kind}</span>
            <code>{f.object}</code>
          </summary>
          <div className="of-body">
            <p>{f.detail}</p>
            <p className="of-fix"><b>Fix:</b> {f.fix}</p>
          </div>
        </details>
      ))}
      {!o.summary.total && (
        <p className="fc-note">Nothing in this org conflicts with the planned schema.</p>
      )}
    </section>
  );
}
