import { useEffect, useRef, useState } from 'react';
import { useRun, STAGES } from './useRun';
import { health, startRun, cancelRun, getConfig } from './api';
import Detail from './components/Detail';
import Gate from './components/Gate';
import Copilot from './components/Copilot';
import Landing from './components/Landing';
import Logo from './components/Logo';

export default function App() {
  const { state, begin, reset, closeGate, injectEvents } = useRun();
  const [engineUp, setEngineUp] = useState<boolean | null>(null);
  const [theme, setTheme] = useState(localStorage.getItem('h2a-theme') || 'dark');
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const [cpOpen, setCpOpen] = useState(false);
  const [hosted, setHosted] = useState(false);
  const [defaultProvider, setDefaultProvider] = useState('mock');
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    health().then(setEngineUp);
    getConfig().then((c) => { setHosted(c.hosted); setDefaultProvider(c.default_provider); });
  }, []);
  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); localStorage.setItem('h2a-theme', theme); }, [theme]);
  useEffect(() => { if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight; }, [state.feed]);

  const running = state.status === 'running';
  const showLanding = state.status === 'idle';

  const start = async (fd: FormData) => {
    setStarting(true); setError('');
    try { begin(await startRun(fd)); }
    catch (e: any) { setError(e.message || 'failed to start'); }
    finally { setStarting(false); }
  };
  const stop = async () => { if (state.runId) await cancelRun(state.runId); reset(); };

  const statusText = running ? `running · ${state.elapsed}` : state.status === 'complete' ? 'complete'
    : state.status === 'error' ? 'error' : (engineUp === null ? 'connecting…' : engineUp ? 'ready' : 'offline');

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <Logo size={36} />
          <div className="brand-txt">
            <h1><span className="wm grad-text">H2A</span> <span className="tag">AI</span></h1>
            <div className="sub">Migration Cockpit · Hybris → Salesforce</div>
          </div>
        </div>
        <div className="topbar-right">
          <span className="pill-status"><span className={`dotpulse ${running ? 'live' : engineUp ? '' : 'off'}`} />{statusText}</span>
          {running && <button className="btn stop" onClick={stop}>■ Stop</button>}
          {!showLanding && !running && <button className="btn ghost" onClick={reset}>+ New migration</button>}
          {state.runId && <button className={`btn ghost ${cpOpen ? 'primary' : ''}`} onClick={() => setCpOpen((v) => !v)}>✦ Copilot</button>}
          <button className="icon-btn" title="Toggle theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? '☀' : '☾'}</button>
        </div>
      </header>

      {showLanding ? (
        <Landing hosted={hosted} defaultProvider={defaultProvider} starting={starting} error={error} onStart={start} />
      ) : (
        <>
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
              <div className="panel-head"><h2>Agent activity</h2><span className="mono faint num">{state.elapsed}</span></div>
              <div className="feed" ref={feedRef}>
                {state.feed.length === 0 ? <p className="empty">Waiting for the agents…</p> :
                  state.feed.map((f) => (
                    <div className={`ev ${f.kind}`} key={f.id}>
                      <span className="t">{f.ts}</span>
                      <span><span className="agent">{f.agent}</span> <span className="body-txt">{f.msg}</span></span>
                    </div>
                  ))}
              </div>
            </section>

            <Detail runId={state.runId} status={state.status} stages={state.stages} plan={state.plan}
              comprehensions={state.comprehensions} artifacts={state.artifacts} decisions={state.decisions}
              ledger={state.ledger} ledgerSummary={state.ledgerSummary} />
          </main>
        </>
      )}

      {state.gate && state.runId && <Gate runId={state.runId} gate={state.gate} onClosed={closeGate} />}
      <Copilot runId={state.runId} open={cpOpen} onClose={() => setCpOpen(false)} onEvents={injectEvents} />
    </div>
  );
}
