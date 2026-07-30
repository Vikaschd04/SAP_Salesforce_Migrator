import { useRef, useState, type DragEvent } from 'react';
import Logo from './Logo';

interface Props {
  hosted: boolean;
  defaultProvider: string;
  starting: boolean;
  error: string;
  onStart: (fd: FormData) => void;
}

export default function Landing({ hosted, defaultProvider, starting, error, onStart }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [path, setPath] = useState('Testing/demo-commerce-suite');
  const [provider, setProvider] = useState(defaultProvider || 'mock');
  const [engine, setEngine] = useState('agentic');
  const [supervised, setSupervised] = useState(true);
  const [verify, setVerify] = useState(false);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const build = (sample = false) => {
    const fd = new FormData();
    fd.append('provider', provider); fd.append('engine', engine);
    fd.append('supervised', String(supervised)); fd.append('verify', String(verify));
    if (sample) fd.append('input_path', 'Testing/demo-commerce-suite');
    else if (file) fd.append('upload', file);
    else if (!hosted && path.trim()) fd.append('input_path', path.trim());
    return fd;
  };

  const canStart = !!file || (!hosted && !!path.trim());

  const onDrop = (e: DragEvent) => {
    e.preventDefault(); setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.name.toLowerCase().endsWith('.zip')) setFile(f);
  };

  return (
    <div className="landing">
      <div className="hero">
        <Logo size={70} glow />
        <span className="hero-badge">◆ <b>Agentic</b> · SAP Hybris &amp; Spartacus → Salesforce</span>
        <h1>Migrate your commerce platform to <span className="grad-text">Salesforce</span>, supervised by AI agents.</h1>
        <p>Upload your SAP Hybris (Java) or Spartacus (Angular) codebase and watch a team of AI agents
          plan, convert, review, and verify it into Apex + LWC — with you in control at every step.</p>
      </div>

      <div className="start-card">
        <div className={`dropzone ${drag ? 'drag' : ''}`}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)} onDrop={onDrop}>
          <input ref={fileRef} type="file" accept=".zip" hidden
            onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <div className="dz-ico">⤒</div>
          <div className="dz-t">{file ? 'Ready to migrate' : 'Drop your codebase .zip here'}</div>
          <div className="dz-s">{file ? 'Click to choose a different file' : 'or click to browse — a Hybris backend and/or Spartacus storefront'}</div>
          {file && <div className="dz-file">📦 {file.name} · {(file.size / 1024).toFixed(0)} KB</div>}
        </div>

        {!hosted && (
          <div className="field full">
            <label>…or a server path</label>
            <input className="inp" type="text" value={path} spellCheck={false}
              onChange={(e) => setPath(e.target.value)} />
          </div>
        )}

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
          <button className="link-btn" disabled={starting} onClick={() => onStart(build(true))}>▷ Try the sample storefront</button>
          <button className="btn primary lg" disabled={starting || !canStart} onClick={() => onStart(build())}>
            {starting ? 'Starting…' : '▶ Start migration'}
          </button>
        </div>
        {error && <div style={{ color: 'var(--danger)', fontSize: 12.5 }}>{error}</div>}
      </div>

      <div className="feature-row">
        <span className="feature"><i className="fdot" /> Convert-everything + completeness ledger</span>
        <span className="feature"><i className="fdot" /> Source ↔ Apex diff</span>
        <span className="feature"><i className="fdot" /> ✦ Migration Copilot</span>
      </div>
    </div>
  );
}
