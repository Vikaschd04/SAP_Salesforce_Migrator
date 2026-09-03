import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react';
import Logo from './Logo';
import { identify, type Identification, type PipelineOption } from '../api';

interface Props {
  hosted: boolean;
  defaultProvider: string;
  starting: boolean;
  error: string;
  onStart: (fd: FormData) => void;
  stoppedAt?: string | null;
  onRunAgain?: () => void;
  onDismissStopped?: () => void;
}

const GATE_LABEL: Record<string, string> = {
  discovery: 'the Discovery gate', plan: 'the Plan gate', build: 'the Build gate',
};

/** Platform names as a person says them, keyed by the engine's own identifiers. */
const PLATFORM: Record<string, string> = {
  hybris: 'SAP Hybris',
  salesforce: 'Salesforce',
  'adobe-commerce': 'Adobe Commerce',
};

const name = (p: string) => PLATFORM[p] || p;

/**
 * Choose a source, then choose what it becomes.
 *
 * The screen used to assume the answer: one hard-coded pair, a sample path pointing at a
 * Hybris corpus, and a headline promising Salesforce. With two migrations that assumption
 * is wrong twice over — it hides the second pipeline and it mislabels the first.
 *
 * So the flow is now identify-then-choose. The source is inspected before anything is
 * committed, and what comes back decides what is offered: a codebase with one valid
 * destination is pre-selected (there is nothing to ask), one that is recognised but not
 * yet migratable says so plainly, and one nothing recognises says what was actually
 * wrong rather than naming a platform it failed to be.
 */
export default function Landing({ hosted, defaultProvider, starting, error, onStart,
                                  stoppedAt, onRunAgain, onDismissStopped }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [path, setPath] = useState('Testing/acme-commerce-hybris');
  const [provider, setProvider] = useState(defaultProvider || 'mock');
  const [engine, setEngine] = useState('agentic');
  const [supervised, setSupervised] = useState(true);
  const [verify, setVerify] = useState(false);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [ident, setIdent] = useState<Identification | null>(null);
  const [looking, setLooking] = useState(false);
  const [chosen, setChosen] = useState<string>('');

  // A .zip cannot be inspected until it is uploaded, so identification runs on a server
  // path only. That is not a gap to paper over: the dropzone says what it can and cannot
  // tell you yet, rather than showing an empty panel that looks like a failure.
  const inspect = useCallback(async (p: string) => {
    if (!p.trim()) { setIdent(null); return; }
    setLooking(true);
    try {
      const got = await identify(p.trim());
      setIdent(got);
      const runnable = got.pipelines.filter((x) => x.implemented);
      setChosen(runnable.length === 1 ? runnable[0].id : '');
    } catch {
      setIdent(null);
    } finally {
      setLooking(false);
    }
  }, []);

  useEffect(() => {
    if (hosted || file) return;
    const t = setTimeout(() => inspect(path), 450);
    return () => clearTimeout(t);
  }, [path, hosted, file, inspect]);

  const build = (samplePath?: string) => {
    const fd = new FormData();
    fd.append('provider', provider); fd.append('engine', engine);
    fd.append('supervised', String(supervised)); fd.append('verify', String(verify));
    if (chosen) fd.append('pipeline', chosen);
    if (samplePath) fd.append('input_path', samplePath);
    else if (file) fd.append('upload', file);
    else if (!hosted && path.trim()) fd.append('input_path', path.trim());
    return fd;
  };

  const runnable = (ident?.pipelines || []).filter((p) => p.implemented);
  const blocked = ident?.status === 'recognised';
  const canStart = (!!file || (!hosted && !!path.trim())) && !blocked && !starting;

  const onDrop = (e: DragEvent) => {
    e.preventDefault(); setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.name.toLowerCase().endsWith('.zip')) { setFile(f); setIdent(null); }
  };

  return (
    <div className="landing">
      {stoppedAt && (
        <div className="resume">
          <div>
            <b>Run stopped at {GATE_LABEL[stoppedAt] || stoppedAt}.</b>
            <p>
              Nothing was approved, and nothing finished so far was thrown away. Edit your
              source, then run again — files you did not change are reused rather than
              converted a second time, so you pay for the difference.
            </p>
          </div>
          <div className="resume-actions">
            {onRunAgain && (
              <button className="btn primary" disabled={starting} onClick={onRunAgain}>
                {starting ? 'Starting…' : '▶ Run again'}
              </button>
            )}
            <button className="link-btn" onClick={onDismissStopped}>Start something else</button>
          </div>
        </div>
      )}

      <div className="hero">
        <Logo size={70} glow />
        <span className="hero-badge">◆ <b>Agentic</b> · commerce platform migration</span>
        <h1>Carry your commerce platform <span className="grad-text">across</span>, supervised by AI agents.</h1>
        <p>
          Point Portage at an SAP Hybris or Adobe Commerce codebase. It works out what it is,
          shows you what it can become, then plans, converts, reviews and accounts for every
          file — with you in control at each gate.
        </p>
      </div>

      <div className="start-card">
        <div className="step">
          <span className="step-n">1</span>
          <span className="step-t">Where is your codebase?</span>
        </div>

        <div className={`dropzone ${drag ? 'drag' : ''}`}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)} onDrop={onDrop}>
          <input ref={fileRef} type="file" accept=".zip" hidden
            onChange={(e) => { setFile(e.target.files?.[0] || null); setIdent(null); }} />
          <div className="dz-ico">⤒</div>
          <div className="dz-t">{file ? 'Ready to migrate' : 'Drop your codebase .zip here'}</div>
          <div className="dz-s">
            {file ? 'Click to choose a different file'
                  : 'or click to browse — SAP Hybris, Spartacus, or Adobe Commerce'}
          </div>
          {file && <div className="dz-file">📦 {file.name} · {(file.size / 1024).toFixed(0)} KB</div>}
        </div>

        {!hosted && (
          <div className="field full">
            <label>…or a server path</label>
            <input className="inp" type="text" value={path} spellCheck={false}
              onChange={(e) => { setPath(e.target.value); setFile(null); }} />
          </div>
        )}

        {/* ── what it is, and what it can become ───────────────────────────── */}
        {file && (
          <div className="ident ident-pending">
            <div className="ident-head">
              <span className="ident-dot pending" />
              <b>Uploaded archives are identified on the server</b>
            </div>
            <p>
              Portage will work out what this is when the run starts, and refuse before
              anything is charged if it is not a codebase it can migrate.
            </p>
          </div>
        )}

        {!file && looking && (
          <div className="ident ident-pending">
            <div className="ident-head"><span className="ident-dot pending" /> Inspecting…</div>
          </div>
        )}

        {!file && !looking && ident && (
          <>
            <div className={`ident ident-${ident.status}`}>
              <div className="ident-head">
                <span className={`ident-dot ${ident.status}`} />
                <b>
                  {ident.status === 'unrecognised'
                    ? 'Not a codebase Portage recognises'
                    : `${name(ident.platform)} detected`}
                </b>
              </div>
              <p>{ident.summary}</p>
            </div>

            {ident.pipelines.length > 0 && (
              <>
                <div className="step">
                  <span className="step-n">2</span>
                  <span className="step-t">
                    {runnable.length > 1 ? 'Choose a destination' : 'What it becomes'}
                  </span>
                </div>
                <div className="pipe-grid">
                  {ident.pipelines.map((p) => (
                    <PipelineCard key={p.id} p={p} chosen={chosen === p.id}
                      onPick={() => p.implemented && setChosen(p.id)} />
                  ))}
                </div>
              </>
            )}
          </>
        )}

        <div className="step">
          <span className="step-n">{ident && ident.pipelines.length ? 3 : 2}</span>
          <span className="step-t">How should it run?</span>
        </div>

        <div className="opt-grid">
          <div className="field">
            <label>AI Provider</label>
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="mock">Mock — free &amp; keyless</option>
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="openrouter">OpenRouter</option>
            </select>
          </div>
          <div className="field">
            <label>Engine</label>
            <div className="seg">
              <button className={engine === 'agentic' ? 'on' : ''} onClick={() => setEngine('agentic')}>Agentic</button>
              <button className={engine === 'linear' ? 'on' : ''} onClick={() => setEngine('linear')}>Linear</button>
            </div>
          </div>
        </div>

        <div className="switch-row">
          <label className="switch"><input type="checkbox" checked={supervised}
            onChange={(e) => setSupervised(e.target.checked)} /> Supervised (review gates)</label>
          <label className="switch"><input type="checkbox" checked={verify}
            onChange={(e) => setVerify(e.target.checked)} /> Verify vs org</label>
        </div>

        <div className="start-actions">
          <button className="link-btn" disabled={starting}
            onClick={() => onStart(build('Testing/acme-commerce-hybris'))}>
            ▷ Try a sample project
          </button>
          <button className="btn primary lg" disabled={!canStart} onClick={() => onStart(build())}>
            {starting ? 'Starting…'
              : blocked ? 'Not migratable yet'
              : chosen ? `▶ Migrate to ${name(chosen.split('->')[1] || '')}`
              : '▶ Start migration'}
          </button>
        </div>
        {error && <div style={{ color: 'var(--danger)', fontSize: 12.5 }}>{error}</div>}
      </div>

      <div className="feature-row">
        <span className="feature"><i className="fdot" /> Convert-everything + completeness ledger</span>
        <span className="feature"><i className="fdot" /> Source ↔ target diff</span>
        <span className="feature"><i className="fdot" /> ✦ Migration Copilot</span>
      </div>
    </div>
  );
}

/**
 * One destination, and what a run to it could honestly claim.
 *
 * `has_oracle` is on the card rather than in the sign-off afterwards because it is the
 * difference between "the target platform compiled this" and "we checked it as far as we
 * can without a compiler" — and that is worth knowing before starting, not after.
 */
function PipelineCard({ p, chosen, onPick }: {
  p: PipelineOption; chosen: boolean; onPick: () => void;
}) {
  return (
    <button type="button" onClick={onPick} disabled={!p.implemented}
      className={`pipe-card ${chosen ? 'on' : ''} ${p.implemented ? '' : 'off'}`}
      aria-pressed={chosen}>
      <div className="pipe-route">
        <span>{name(p.source)}</span>
        <i className="pipe-arrow">→</i>
        <b>{name(p.target)}</b>
      </div>
      <div className="pipe-claim">
        {p.has_oracle
          ? <><i className="fdot good" /> Compile-verified against a real org</>
          : <><i className="fdot warn" /> Statically checked — no compiler for this target</>}
      </div>
      {!p.implemented && (
        <div className="pipe-soon">
          In build. The source is read end to end; the target does not yet emit
          finished code.
        </div>
      )}
      {p.shipped && <span className="pipe-tag">Shipped</span>}
    </button>
  );
}
