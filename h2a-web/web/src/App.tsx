import { useEffect, useRef, useState } from 'react';
import { useRun, STAGES } from './useRun';
import { health, startRun, cancelRun } from './api';
import Detail from './components/Detail';
import Gate from './components/Gate';
import Copilot from './components/Copilot';

export default function App() {
  const { state, begin, reset, closeGate, injectEvents } = useRun();
  const [engineUp, setEngineUp] = useState<boolean | null>(null);
  const [theme, setTheme] = useState(localStorage.getItem('h2a-theme') || 'dark');
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const [cpOpen, setCpOpen] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  // form
  const [path, setPath] = useState('Testing/demo-commerce-suite');
  const [provider, setProvider] = useState('mock');
  const [engine, setEngine] = useState('agentic');
  const [supervised, setSupervised] = useState(true);
  const [verify, setVerify] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { health().then(setEngineUp); }, []);
  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); localStorage.setItem('h2a-theme', theme); }, [theme]);
  useEffect(() => { if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight; }, [state.feed]);

  const running = state.status === 'running';

  const start = async () => {
    setStarting(true); setError('');
    try {
      const fd = new FormData();
      fd.append('provider', provider); fd.append('engine', engine);
      fd.append('supervised', String(supervised)); fd.append('verify', String(verify));
      const f = fileRef.current?.files?.[0];
      if (f) fd.append('upload', f); else fd.append('input_path', path.trim());
      const runId = await startRun(fd);
      begin(runId);
    } catch (e: any) { setError(e.message || 'failed to start'); }
    finally { setStarting(false); }
  };

  const stop = async () => {
    if (state.runId) await cancelRun(state.runId);
    reset();   // return the UI to idle so a new migration can be started immediately
  };

  const statusText = state.status === 'running' ? `running · ${state.elapsed}` : state.status === 'complete' ? 'complete' : state.status === 'error' ? 'error' : (engineUp === null ? 'connecting…' : engineUp ? 'engine ready' : 'backend offline');

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">H2A</div>
          <div>
            <h1>Migration Cockpit</h1>
            <div className="sub">SAP Hybris &amp; Spartacus → Salesforce Apex + LWC · supervised AI agents</div>
          </div>
        </div>
        <div className="topbar-right">
          <span className="pill-status"><span className={`dotpulse ${running ? 'live' : engineUp ? '' : 'off'}`} />{statusText}</span>
          <button className={`btn ghost ${cpOpen ? 'primary' : ''}`} onClick={() => setCpOpen((v) => !v)}>✦ Copilot</button>
          <button className="icon-btn" title="Toggle theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? '☀' : '☾'}</button>
        </div>
      </header>

      <section className="startbar">
        <div className="field grow">
          <label>Codebase path <span className="faint">(server path or relative to repo)</span></label>
          <input type="text" value={path} spellCheck={false} onChange={(e) => setPath(e.target.value)} />
        </div>
        <div className="field">
          <label>Or upload .zip</label>
          <input ref={fileRef} type="file" accept=".zip" />
        </div>
        <div className="field">
          <label>Provider</label>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="mock">Mock (free)</option>
            <option value="anthropic">Anthropic</option>
            <option value="openrouter">OpenRouter</option>
          </select>
        </div>
        <div className="field">
          <label>Engine</label>
          <select value={engine} onChange={(e) => setEngine(e.target.value)}>
            <option value="agentic">Agentic</option>
            <option value="linear">Linear</option>
          </select>
        </div>
        <div className="toggles">
          <label className="toggle"><input type="checkbox" checked={supervised} onChange={(e) => setSupervised(e.target.checked)} /> Supervised</label>
          <label className="toggle"><input type="checkbox" checked={verify} onChange={(e) => setVerify(e.target.checked)} /> Verify vs org</label>
        </div>
        <button className="btn primary" disabled={starting || running} onClick={start}>{running ? 'Running…' : '▶ Start migration'}</button>
        {running && <button className="btn stop" onClick={stop}>■ Stop</button>}
        {error && <span style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</span>}
      </section>

      <section className="stepper">
        {STAGES.map((s, i) => {
          const st = state.stages[s.id]?.status || 'pending';
          const icon = st === 'done' ? '✓' : st === 'error' ? '!' : st === 'active' ? '◐' : i + 1;
          return (
            <div key={s.id} className={`step ${st}`}>
              <div className="st-k">{String(i + 1).padStart(2, '0')}</div>
              <div className="st-n"><span className="st-ico">{icon}</span>{s.n}</div>
              <div className="st-d">{state.stages[s.id]?.detail || ''}</div>
            </div>
          );
        })}
      </section>

      <main className="body">
        <section className="panel">
          <div className="panel-head"><h2>Agent activity</h2><span className="mono faint">{state.elapsed}</span></div>
          <div className="feed" ref={feedRef}>
            {state.feed.length === 0 ? <p className="empty">Start a migration to watch the agents work.</p> :
              state.feed.map((f) => (
                <div className={`ev ${f.kind}`} key={f.id}>
                  <span className="t">{f.ts}</span>
                  <span><span className="agent">{f.agent}</span> <span className="body-txt">{f.msg}</span></span>
                </div>
              ))}
          </div>
        </section>

        <Detail runId={state.runId} status={state.status} stages={state.stages} plan={state.plan} comprehensions={state.comprehensions}
          artifacts={state.artifacts} decisions={state.decisions} ledger={state.ledger} ledgerSummary={state.ledgerSummary} />
      </main>

      {state.gate && state.runId && <Gate runId={state.runId} gate={state.gate} onClosed={closeGate} />}
      <Copilot runId={state.runId} open={cpOpen} onClose={() => setCpOpen(false)} onEvents={injectEvents} />
    </div>
  );
}
