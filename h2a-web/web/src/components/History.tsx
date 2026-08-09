import { useEffect, useMemo, useState } from 'react';
import { listRuns } from '../api';
import type { RunSummary } from '../types';

/**
 * Past migrations, recovered from the durable store.
 *
 * A modal rather than a permanent panel: history is something you go looking for, and
 * on the landing screen it would compete with the one action that matters. Paginated
 * because a working team produces hundreds of these and an unbounded list stops being
 * readable long before it stops loading.
 */

const PER_PAGE = 7;

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

export default function History({ open, onClose, onOpen }: {
  open: boolean; onClose: () => void; onOpen: (runId: string) => void;
}) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [page, setPage] = useState(0);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    const tick = () => listRuns().then((r) => { if (alive) setRuns(r); }).catch(() => {});
    tick();
    const t = setInterval(tick, 5000);
    return () => { alive = false; clearInterval(t); };
  }, [open]);

  // Escape closes, and the page scroll locks — otherwise the list behind keeps moving.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
  }, [open, onClose]);

  // Newest first, always — the server returns live runs ahead of history, which is not
  // the same thing as most-recent when an older run is still going.
  const sorted = useMemo(
    () => [...(runs || [])].sort((a, b) => (b.started || 0) - (a.started || 0)),
    [runs],
  );
  const pages = Math.max(1, Math.ceil(sorted.length / PER_PAGE));
  const p = Math.min(page, pages - 1);
  const slice = sorted.slice(p * PER_PAGE, p * PER_PAGE + PER_PAGE);

  if (!open) return null;

  return (
    <div className="modal-back" onClick={onClose} role="dialog" aria-modal="true"
      aria-label="Recent migrations">
      <div className="modal hist-modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <div>
            <h2>Recent migrations</h2>
            <p>Newest first. History survives a restart.</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="modal-body">
          {runs === null ? (
            <p className="empty">Loading…</p>
          ) : sorted.length === 0 ? (
            <p className="empty">No migrations yet — start one from the home screen.</p>
          ) : (
            <div className="hist-list">
              {slice.map((r) => (
                <button key={r.id} className="hist-row"
                  onClick={() => { onOpen(r.id); onClose(); }}
                  title={r.error || r.input_dir}>
                  <span className={`hist-dot ${r.status}`} />
                  <span className="hist-name">
                    {r.input_dir.split('/').filter(Boolean).pop()}
                    <span className="hist-id mono">{r.id}</span>
                  </span>
                  <span className={`chip hist-status ${r.status}`}>{LABEL[r.status] || r.status}</span>
                  <span className="hist-meta mono">{r.provider}</span>
                  {r.supervised && <span className="hist-meta mono">supervised</span>}
                  <span className="hist-meta num">{dur(r.elapsed)}</span>
                  <span className="hist-meta faint">{ago(r.started)}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <footer className="modal-foot">
          <span className="faint">
            {sorted.length === 0 ? '' :
              `${p * PER_PAGE + 1}–${Math.min((p + 1) * PER_PAGE, sorted.length)} of ${sorted.length}`}
          </span>
          {pages > 1 && (
            <div className="pager">
              <button className="btn-mini" disabled={p === 0} onClick={() => setPage(p - 1)}>‹ Newer</button>
              <span className="pager-n num">{p + 1} / {pages}</span>
              <button className="btn-mini" disabled={p >= pages - 1} onClick={() => setPage(p + 1)}>Older ›</button>
            </div>
          )}
        </footer>

        <p className="hist-note">
          A run marked <b>Interrupted</b> was in flight when the server stopped — its output
          up to that point is still on disk.
        </p>
      </div>
    </div>
  );
}
