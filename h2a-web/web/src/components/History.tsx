import { useEffect, useState } from 'react';
import { listRuns } from '../api';
import type { RunSummary } from '../types';

/**
 * Past migrations, recovered from the durable store.
 *
 * Before this, a restart or a free-tier sleep erased every run anyone had done — a
 * migration is a multi-hour artifact with an audit trail attached, so losing it because
 * a container recycled was disqualifying for real work. This is where it comes back.
 */

const LABEL: Record<string, string> = {
  complete: 'Complete', running: 'Running', queued: 'Queued',
  error: 'Failed', cancelled: 'Stopped', interrupted: 'Interrupted',
};

const ago = (started?: number) => {
  if (!started) return '';
  const s = Math.max(0, Date.now() / 1000 - started);
  if (s < 90) return 'just now';
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 172800) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
};

const dur = (s: number) => (s < 90 ? `${s.toFixed(0)}s` : `${(s / 60).toFixed(1)}m`);

export default function History({ onOpen }: { onOpen: (runId: string) => void }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = () => listRuns().then((r) => { if (alive) setRuns(r); }).catch(() => {});
    tick();
    const t = setInterval(tick, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (runs === null) return null;
  if (runs.length === 0) {
    return <p className="empty" style={{ textAlign: 'center' }}>No migrations yet — start one above.</p>;
  }

  return (
    <section className="hist">
      <div className="hist-head">
        <span className="u-lbl" style={{ margin: 0 }}>Recent migrations</span>
        <span className="faint" style={{ fontSize: 11.5 }}>{runs.length} kept on disk</span>
      </div>
      <div className="hist-list">
        {runs.map((r) => (
          <button key={r.id} className="hist-row" onClick={() => onOpen(r.id)}
            title={r.error || r.input_dir}>
            <span className={`hist-dot ${r.status}`} />
            <span className="hist-name">{r.input_dir.split('/').filter(Boolean).pop()}</span>
            <span className={`chip hist-status ${r.status}`}>{LABEL[r.status] || r.status}</span>
            <span className="hist-meta mono">{r.provider}</span>
            {r.supervised && <span className="hist-meta mono">supervised</span>}
            <span className="hist-meta num">{dur(r.elapsed)}</span>
            <span className="hist-meta faint">{ago(r.started)}</span>
          </button>
        ))}
      </div>
      <p className="hist-note">
        History survives a restart. A run marked <b>Interrupted</b> was in flight when the
        server stopped — its output up to that point is still on disk.
      </p>
    </section>
  );
}
