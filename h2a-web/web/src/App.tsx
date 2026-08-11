import { useEffect, useRef, useState } from 'react';
import { useRun, STAGES } from './useRun';
import { health, startRun, cancelRun, getConfig, me as fetchMe, logout, PreflightError } from './api';
import type { Me } from './api';
import Detail from './components/Detail';
import Gate from './components/Gate';
import Copilot from './components/Copilot';
import Landing from './components/Landing';
import PreflightModal from './components/PreflightModal';
import History from './components/History';
import Logo from './components/Logo';
import SignIn from './components/SignIn';
import Keys from './components/Keys';
import AccountMenu from './components/AccountMenu';

export default function App() {
  const { state, begin, reset, rejoin, closeGate, injectEvents } = useRun();
  const [engineUp, setEngineUp] = useState<boolean | null>(null);
  const [theme, setTheme] = useState(localStorage.getItem('h2a-theme') || 'dark');
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const [rejected, setRejected] = useState<any>(null);
  const [cpOpen, setCpOpen] = useState(false);
  const [errDismissed, setErrDismissed] = useState(false);
  const [hosted, setHosted] = useState(false);
  const [defaultProvider, setDefaultProvider] = useState('mock');
  const [me, setMe] = useState<Me | null>(null);
  const [histOpen, setHistOpen] = useState(false);
  const [keysOpen, setKeysOpen] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    health().then(setEngineUp);
    getConfig().then((c) => { setHosted(c.hosted); setDefaultProvider(c.default_provider); });
    fetchMe().then((m) => {
      setMe(m);
      // Only after we know who we are: rejoining before auth resolves would 401 and
      // wrongly discard a run that is still going.
      if (!m.required || m.user) rejoin();
    });
  }, [rejoin]);
  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); localStorage.setItem('h2a-theme', theme); }, [theme]);
  useEffect(() => { if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight; }, [state.feed]);

  const running = state.status === 'running';
  const showLanding = state.status === 'idle';

  // Kept so a run stopped at a gate can be restarted with identical settings after the
  // user edits their source. The engine's incremental reuse then does the rest — only
  // what actually changed is re-billed.
  const [lastForm, setLastForm] = useState<FormData | null>(null);
  const [stoppedAt, setStoppedAt] = useState<string | null>(null);

  const start = async (fd: FormData) => {
    setStarting(true); setError(''); setRejected(null); setErrDismissed(false);
    setLastForm(fd); setStoppedAt(null);
    try { begin(await startRun(fd)); }
    catch (e: any) {
      // A refused upload is not an error to apologise for — it is a finding, and the
      // report explains it far better than a message can.
      if (e instanceof PreflightError) { setRejected(e.report); setError(''); }
      else setError(e.message || 'failed to start');
    }
    finally { setStarting(false); }
  };
  const stop = async () => { if (state.runId) await cancelRun(state.runId); reset(); };

  // Stopping from a review gate is a different intent from abandoning the run: the user
  // wants to change something and come back, so we remember where they were.
  const stopFromGate = async (gateName: string) => {
    if (state.runId) await cancelRun(state.runId);
    closeGate(); reset(); setStoppedAt(gateName);
  };
  const runAgain = () => { if (lastForm) start(lastForm); };

  const statusText = running ? `running · ${state.elapsed}` : state.status === 'complete' ? 'complete'
    : state.status === 'error' ? 'error' : (engineUp === null ? 'connecting…' : engineUp ? 'ready' : 'offline');

  if (me === null) return null;                       // avoid flashing the app pre-auth
  if (me.required && !me.user) {
    return <SignIn me={me} onIn={(user) => setMe({ ...me, user, has_users: true })} />;
  }

  const signOut = async () => { await logout(); reset(); setMe({ ...me, user: null }); };

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
          <button className="btn ghost" onClick={() => setHistOpen(true)}>⟲ History</button>
          <button className="icon-btn" title="Toggle theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? '☀' : '☾'}</button>
          {me.user && (
            <AccountMenu user={me.user} onKeys={() => setKeysOpen(true)} onSignOut={signOut} />
          )}
        </div>
      </header>

      {showLanding ? (
        <Landing hosted={hosted} defaultProvider={defaultProvider} starting={starting}
          error={error} onStart={start}
          stoppedAt={stoppedAt} onRunAgain={lastForm ? runAgain : undefined}
          onDismissStopped={() => setStoppedAt(null)} />
      ) : (
        <>
          {state.errorMsg && !errDismissed && (
            <div className="run-error">
              <span>⚠</span>
              <div>
                <b>The migration hit an error.</b> {state.errorMsg}
                <div style={{ marginTop: 4, opacity: 0.85 }}>
                  Everything produced before the failure is still available in the tabs below — you can
                  regenerate individual files without re-running the whole migration.
                </div>
              </div>
              <button className="re-x" onClick={() => setErrDismissed(true)}>✕</button>
            </div>
          )}

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
              ledger={state.ledger} ledgerSummary={state.ledgerSummary} discovery={state.discovery}
              ruleLedger={state.ruleLedger} signoff={state.signoff} characterization={state.characterization}
              triage={state.triage} alignment={state.alignment} provenance={state.provenance}
              blast={state.blast} replay={state.replay}
              cost={state.cost} tokens={state.tokens} />
          </main>
        </>
      )}

      <PreflightModal report={rejected} onClose={() => setRejected(null)} />
      <Keys open={keysOpen} onClose={() => setKeysOpen(false)} />
      <History open={histOpen} onClose={() => setHistOpen(false)} onOpen={begin} />
      {state.gate && state.runId && <Gate runId={state.runId} gate={state.gate} onClosed={closeGate} onStop={stopFromGate} />}
      <Copilot runId={state.runId} open={cpOpen} onClose={() => setCpOpen(false)} onEvents={injectEvents} />
    </div>
  );
}
