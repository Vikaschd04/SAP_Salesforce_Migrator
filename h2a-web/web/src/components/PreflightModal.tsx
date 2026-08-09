import { useEffect } from 'react';
import Preflight, { type PreflightReport } from './Preflight';

/**
 * Why a migration did not start.
 *
 * This was previously appended below the upload form, which is the wrong place for it:
 * a refusal is a blocking answer to "why did nothing happen", and someone who has just
 * pressed Start is looking at the button, not at the bottom of the page. It interrupts
 * instead — and says what to do next, since "this is not a Hybris project" is only half
 * an answer.
 */
export default function PreflightModal({ report, onClose }: {
  report: PreflightReport | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!report) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
  }, [report, onClose]);

  if (!report) return null;

  return (
    <div className="modal-back" onClick={onClose} role="alertdialog" aria-modal="true"
      aria-label="This upload was not migrated">
      <div className="modal pf-modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <div>
            <h2>We didn’t start this migration</h2>
            <p>Nothing was run and nothing was charged — the upload was checked first.</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="modal-body">
          <Preflight r={report} />

          <div className="pf-help">
            <span className="u-lbl">What to check</span>
            <ul>
              <li>Zip the <b>extension folder</b> itself — the one containing
                <code>extensioninfo.xml</code> — or a folder of several of them.</li>
              <li>Include <code>src/</code> and <code>resources/</code>. A zip of only
                compiled <code>.jar</code> files has no source to migrate.</li>
              <li>A Spartacus storefront works too, as long as the
                <code>*.component.ts</code> files are in the archive.</li>
            </ul>
          </div>
        </div>

        <footer className="modal-foot">
          <span className="faint">Fix the archive and upload again.</span>
          <button className="btn primary" onClick={onClose}>Try another file</button>
        </footer>
      </div>
    </div>
  );
}
