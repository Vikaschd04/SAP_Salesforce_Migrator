import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react';
import Logo from './Logo';
import { fetchKeys, identify, PLATFORM_LABEL, type Identification, type PipelineOption } from '../api';

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

const PLATFORM: Record<string, string> = {
  hybris: 'SAP Hybris', salesforce: 'Salesforce', 'adobe-commerce': 'Adobe Commerce',
};
const name = (p: string) => PLATFORM[p] || p;

/**
 * Sample projects — one per migration, so the tool can be tried without a codebase.
 *
 * Two rather than one on purpose: a single sample makes whichever pipeline it happens to
 * exercise look like the product and the other like a footnote. Each names what it
 * actually contains, because "try the sample" tells someone nothing about what they are
 * about to watch.
 */
const SAMPLES = [
  {
    path: 'Testing/acme-commerce-hybris',
    from: 'hybris', to: 'salesforce',
    title: 'Acme Commerce',
    detail: '20 Java files, 2 Angular components, a JUnit suite',
  },
  {
    path: 'Testing/acme-commerce-magento',
    from: 'adobe-commerce', to: 'hybris',
    title: 'Acme Loyalty',
    detail: '11 PHP files, an around plugin, EAV attributes, cluster cron',
  },
];

type SourceMode = 'sample' | 'upload' | 'path';

/**
 * Choose a source, then choose what it becomes.
 *
 * The screen used to assume both answers: one hard-coded pair and a headline promising
 * Salesforce. With two migrations that is wrong twice — it hides the second pipeline and
 * mislabels the first.
 *
 * The three ways in are now a segmented control rather than a dropzone with a path field
 * beneath it and the sample hidden in a text link. They are alternatives, and a layout
 * that stacks alternatives reads as a form to fill in rather than a choice to make.
 */
export default function Landing({ hosted, defaultProvider, starting, error, onStart,
                                  stoppedAt, onRunAgain, onDismissStopped }: Props) {
  const [mode, setMode] = useState<SourceMode>('upload');
  const [sample, setSample] = useState(SAMPLES[0].path);
  const [file, setFile] = useState<File | null>(null);
  const [path, setPath] = useState('');
  const [provider, setProvider] = useState(defaultProvider || 'mock');
  const [engine, setEngine] = useState('agentic');
  const [supervised, setSupervised] = useState(true);
  const [verify, setVerify] = useState(false);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Which providers this deployment can actually call — the server's own credential, or
  // one this user stored. Picking `unorouter` with neither configured started a run that
  // fell back to stub output, and the only way to find out was to read the result and
  // notice it was not real. A dry run that silently is not one is worse than no dry
  // run. [1.48]
  const [providerReady, setProviderReady] = useState<Record<string, boolean>>({});
  useEffect(() => {
    fetchKeys()
      .then((k) => {
        const own: Record<string, boolean> = {};
        for (const key of k.keys || []) own[key.provider] = true;
        setProviderReady({ ...(k.server || {}), ...own, mock: true });
      })
      .catch(() => setProviderReady({ mock: true }));
  }, []);

  const [ident, setIdent] = useState<Identification | null>(null);
  const [looking, setLooking] = useState(false);
  const [chosen, setChosen] = useState('');

  // The path being inspected, whichever way it was chosen. An upload cannot be inspected
  // until it reaches the server, which the panel says rather than showing an empty box.
  const probePath = mode === 'sample' ? sample : mode === 'path' ? path : '';

  const inspect = useCallback(async (p: string) => {
    if (!p.trim()) { setIdent(null); setChosen(''); return; }
    setLooking(true);
    try {
      const got = await identify(p.trim());
      setIdent(got);
      const runnable = got.pipelines.filter((x) => x.implemented);
      setChosen(runnable.length === 1 ? runnable[0].id : '');
    } catch {
      setIdent(null);
    } finally { setLooking(false); }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => inspect(probePath), probePath === sample ? 0 : 450);
    return () => clearTimeout(t);
  }, [probePath, sample, inspect]);

  const build = () => {
    const fd = new FormData();
    fd.append('provider', provider); fd.append('engine', engine);
    fd.append('supervised', String(supervised)); fd.append('verify', String(verify));
    if (chosen) fd.append('pipeline', chosen);
    if (mode === 'upload' && file) fd.append('upload', file);
    else if (probePath.trim()) fd.append('input_path', probePath.trim());
    return fd;
  };

  const runnable = (ident?.pipelines || []).filter((p) => p.implemented);
  const blocked = ident?.status === 'recognised';
  const haveSource = mode === 'upload' ? !!file : !!probePath.trim();
  const canStart = haveSource && !blocked && !starting;

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
        <Logo size={72} glow />
        <span className="hero-badge">◆ <b>Agentic</b> · commerce platform migration</span>
        <h1>Carry your commerce platform <span className="grad-text">across</span>, supervised by AI agents.</h1>
        <p>
          Point Portage at an SAP Hybris or Adobe Commerce codebase. It works out what it
          is, shows you what it can become, then plans, converts, reviews and accounts for
          every file — with you in control at each gate.
        </p>
      </div>

      <div className="start-card">
        {/* ── source ───────────────────────────────────────────────────────
            One question — where is your code — asked once. It used to be asked through
            a heading, a segmented control, a tall dropzone, an aside paragraph and
            four-block cards: five pieces of chrome for one answer. The primary way in
            is the only thing at full weight now, and the alternatives are a line of
            text beneath it. */}
        <div className="sec">
          {mode === 'upload' && (
            <div className={`dropzone ${drag ? 'drag' : ''}`}
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)} onDrop={onDrop}>
              <input ref={fileRef} type="file" accept=".zip" hidden
                onChange={(e) => { setFile(e.target.files?.[0] || null); setIdent(null); }} />
              <div className="dz-ico">⤒</div>
              {file
                ? <>
                    <div className="dz-t">{file.name}</div>
                    <div className="dz-s">{(file.size / 1024).toFixed(0)} KB · click to replace</div>
                  </>
                : <>
                    <div className="dz-t">Drop your codebase .zip</div>
                    <div className="dz-s">or click to browse</div>
                  </>}
            </div>
          )}

          {mode === 'sample' && (
            <div className="sample-list">
              {SAMPLES.map((s) => (
                <button key={s.path} type="button" onClick={() => setSample(s.path)}
                  className={`sample-row ${sample === s.path ? 'on' : ''}`}
                  aria-pressed={sample === s.path}>
                  <span className="sample-tick" aria-hidden />
                  <span className="sample-body">
                    <span className="sample-route">
                      <b>{name(s.from)}</b><i className="pipe-arrow">→</i><b>{name(s.to)}</b>
                    </span>
                    <span className="sample-detail">{s.title} · {s.detail}</span>
                  </span>
                </button>
              ))}
            </div>
          )}

          {mode === 'path' && (
            <input className="inp inp-lg" type="text" value={path} spellCheck={false} autoFocus
              placeholder="/srv/projects/my-storefront"
              onChange={(e) => setPath(e.target.value)} />
          )}

          <div className="src-alt">
            {mode !== 'upload' && (
              <button type="button" className="link-btn inline" onClick={() => setMode('upload')}>
                Upload a .zip
              </button>
            )}
            {mode !== 'sample' && (
              <button type="button" className="link-btn inline" onClick={() => setMode('sample')}>
                Try a sample project
              </button>
            )}
            {!hosted && mode !== 'path' && (
              <button type="button" className="link-btn inline" onClick={() => setMode('path')}>
                Use a server path
              </button>
            )}
          </div>
        </div>

        {/* ── what it is, and what it becomes ──────────────────────────────── */}
        {mode === 'upload' && file && (
          <div className="sec"><div className="ident ident-pending">
            <div className="ident-head"><span className="ident-dot pending" />
              <b>Identified on the server when the run starts</b></div>
            <p>An archive cannot be inspected until it is uploaded. Portage will refuse
              before anything is charged if it is not a codebase it can migrate.</p>
          </div></div>
        )}

        {mode !== 'upload' && looking && (
          <div className="sec"><div className="ident ident-pending">
            <div className="ident-head"><span className="ident-dot pending" /> Inspecting…</div>
          </div></div>
        )}

        {mode !== 'upload' && !looking && ident && (
          <div className="sec">
            <div className={`ident ident-${ident.status}`}>
              <div className="ident-head">
                <span className={`ident-dot ${ident.status}`} />
                <b>{ident.status === 'unrecognised'
                  ? 'Not a codebase Portage recognises'
                  : `${name(ident.platform)} detected`}</b>
              </div>
              <p>{ident.summary}</p>
            </div>

            {ident.pipelines.length > 0 && (
              <>
                <div className="sec-h sec-h-plain">
                  <h3>{runnable.length > 1 ? 'Choose a destination' : 'What it becomes'}</h3>
                </div>
                <div className="pipe-grid">
                  {ident.pipelines.map((p) => (
                    <PipelineCard key={p.id} p={p} chosen={chosen === p.id}
                      onPick={() => p.implemented && setChosen(p.id)} />
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* ── how it runs ──────────────────────────────────────────────────── */}
        <div className="sec">
          <div className="sec-h sec-h-plain"><h3>How it runs</h3></div>

          <div className="opt-grid">
            <div className="field">
              <label>AI provider</label>
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="mock">Mock — free &amp; keyless</option>
                <option value="anthropic">
                  Anthropic (Claude){providerReady.anthropic === false ? ' — no key configured' : ''}
                </option>
                <option value="unorouter">
                  Unorouter{providerReady.unorouter === false ? ' — no key configured' : ''}
                </option>
              </select>
              <span className="hint">
                {provider === 'mock'
                  ? 'Walks the whole pipeline with stub responses. Nothing is charged.'
                  : providerReady[provider] === false
                    ? 'No key for this provider — add one under Keys, or ask whoever '
                      + 'runs this deployment to set it. Starting now would produce stub '
                      + 'output that reads like a real migration.'
                    : 'Real model calls. The Discovery gate shows the cost before any spend.'}
              </span>
            </div>
            <div className="field">
              <label>Engine</label>
              <div className="seg">
                <button className={engine === 'agentic' ? 'on' : ''} onClick={() => setEngine('agentic')}>Agentic</button>
                <button className={engine === 'linear' ? 'on' : ''} onClick={() => setEngine('linear')}>Linear</button>
              </div>
              <span className="hint">
                {engine === 'agentic'
                  ? 'Planner, Builder, Critic and Verifier, with review gates.'
                  : 'A single deterministic pass. Faster, and nothing reviews it.'}
              </span>
            </div>
          </div>

          <div className="opt-toggles">
            <Toggle on={supervised} set={setSupervised} label="Supervised"
              hint="Pause at Discovery, Plan and Build so you approve before it continues." />
            <Toggle on={verify} set={setVerify} label="Verify against an org"
              hint="Dry-run deploy the result. Needs the Salesforce CLI and an authorised org." />
          </div>
        </div>

        <div className="start-actions">
          <span className="start-note">
            {blocked ? 'This source is recognised, and no migration from it can run yet.'
              : chosen ? `Ready — ${name(chosen.split('->')[0])} → ${name(chosen.split('->')[1])}`
              : haveSource ? 'Ready' : 'Choose a codebase to begin'}
          </span>
          <button className="btn primary lg" disabled={!canStart} onClick={() => onStart(build())}>
            {starting ? 'Starting…' : blocked ? 'Not migratable yet' : '▶ Start migration'}
          </button>
        </div>
        {error && <div className="start-error" role="alert">{error}</div>}
      </div>

      <div className="feature-row">
        <span className="feature"><i className="fdot" /> Convert-everything + completeness ledger</span>
        <span className="feature"><i className="fdot" /> Source ↔ target diff</span>
        <span className="feature"><i className="fdot" /> ✦ Migration Copilot</span>
      </div>
    </div>
  );
}

function Toggle({ on, set, label, hint }: {
  on: boolean; set: (v: boolean) => void; label: string; hint: string;
}) {
  return (
    <label className={`opt-toggle ${on ? 'on' : ''}`}>
      <input type="checkbox" checked={on} onChange={(e) => set(e.target.checked)} />
      <span className="opt-toggle-box" aria-hidden />
      <span>
        <b>{label}</b>
        <i>{hint}</i>
      </span>
    </label>
  );
}

/**
 * One destination, and what a run to it could honestly claim.
 *
 * `has_oracle` is on the card rather than in the sign-off afterwards because it is the
 * difference between "the target platform compiled this" and "we checked it as far as we
 * can without a compiler" — worth knowing before starting, not after.
 */
function PipelineCard({ p, chosen, onPick }: {
  p: PipelineOption; chosen: boolean; onPick: () => void;
}) {
  return (
    <button type="button" onClick={onPick} disabled={!p.implemented}
      className={`pipe-card ${chosen ? 'on' : ''} ${p.implemented ? '' : 'off'}`}
      aria-pressed={chosen}>
      <div className="pipe-route">
        <span>{name(p.source)}</span><i className="pipe-arrow">→</i><b>{name(p.target)}</b>
      </div>
      <div className="pipe-claim">
        {p.has_oracle
          ? <><i className="fdot good" /> Compile-verified against a real org</>
          : <><i className="fdot warn" /> Statically checked — no compiler for this target</>}
      </div>
      {!p.implemented && (
        <div className="pipe-soon">
          In build. The source is read end to end; the target does not yet emit finished code.
        </div>
      )}
      {p.shipped && <span className="pipe-tag">Shipped</span>}
    </button>
  );
}
