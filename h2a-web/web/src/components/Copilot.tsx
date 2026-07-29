import { useEffect, useRef, useState } from 'react';
import { askCopilot } from '../api';

interface Msg { role: 'user' | 'bot'; text: string; }

const SUGGESTIONS = [
  'Give me an overview',
  'What migration risks did you find?',
  'What was skipped and why?',
  'Any Critic findings to review?',
  'Which classes were flagged for CPQ?',
];

export default function Copilot({ runId, open, onClose }: { runId: string | null; open: boolean; onClose: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight; }, [msgs, busy]);

  const send = async (text: string) => {
    if (!text.trim() || !runId || busy) return;
    setMsgs((m) => [...m, { role: 'user', text }]);
    setInput(''); setBusy(true);
    try { const a = await askCopilot(runId, text); setMsgs((m) => [...m, { role: 'bot', text: a }]); }
    catch (e: any) { setMsgs((m) => [...m, { role: 'bot', text: '⚠ ' + (e.message || 'error') }]); }
    finally { setBusy(false); }
  };

  if (!open) return null;
  return (
    <aside className="copilot">
      <div className="cp-head">
        <div className="cp-title"><span className="cp-mark">✦</span> Migration Copilot</div>
        <button className="icon-btn" onClick={onClose}>✕</button>
      </div>
      <div className="cp-body" ref={bodyRef}>
        {msgs.length === 0 && (
          <div className="cp-intro">
            <p>Ask about this migration — risks, decisions, Critic findings, or a specific class.</p>
            {!runId && <p className="empty">Start a run first, then ask me anything.</p>}
          </div>
        )}
        {msgs.map((m, i) => <div key={i} className={`cp-msg ${m.role}`}>{m.text}</div>)}
        {busy && <div className="cp-msg bot cp-typing">thinking…</div>}
      </div>
      <div className="cp-suggest">
        {SUGGESTIONS.map((s) => <button key={s} className="btn-mini" disabled={!runId || busy} onClick={() => send(s)}>{s}</button>)}
      </div>
      <div className="cp-input">
        <input value={input} placeholder="Ask the Copilot…" disabled={!runId || busy}
          onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') send(input); }} />
        <button className="btn primary" disabled={!runId || busy} onClick={() => send(input)}>Send</button>
      </div>
    </aside>
  );
}
