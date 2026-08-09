import { useEffect, useState } from 'react';
import { fetchKeys, saveKey, removeKey } from '../api';
import type { KeyState } from '../api';

/**
 * Your own provider credentials.
 *
 * A stored key shows as dots rather than as nothing, because "no key set" and "a key is
 * set, you just cannot read it" are very different states and the UI has to distinguish
 * them. The dots are decorative — the server never sends the key back — so the masked
 * hint sits beside them as the one piece of real evidence about *which* key is stored.
 *
 * Editing is explicit: you click Change, and only then does the field accept input. That
 * avoids the trap where a pre-filled password box gets half-overwritten and saved.
 */

const PROVIDERS: { id: string; label: string; help: string }[] = [
  { id: 'anthropic', label: 'Anthropic', help: 'sk-ant-…  ·  console.anthropic.com' },
  { id: 'openrouter', label: 'OpenRouter', help: 'sk-or-…  ·  openrouter.ai/keys' },
];

const DOTS = '••••••••••••••••••••';

export default function Keys({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [state, setState] = useState<KeyState | null>(null);
  const [editing, setEditing] = useState<Record<string, boolean>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');

  const load = () => fetchKeys().then(setState).catch(() => {});

  useEffect(() => {
    if (!open) return;
    load();
    setEditing({}); setDraft({}); setError(''); setSaved('');
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const stored = (p: string) => state?.keys.find((k) => k.provider === p);
  const serverHas = (p: string) => !!state?.server?.[p];

  const save = async (p: string) => {
    setBusy(p); setError(''); setSaved('');
    try {
      await saveKey(p, draft[p] || '');
      setDraft({ ...draft, [p]: '' });
      setEditing({ ...editing, [p]: false });
      setSaved(p);
      await load();
    } catch (e: any) {
      setError(e.message || 'Could not save that key.');
    } finally {
      setBusy('');
    }
  };

  const drop = async (p: string) => {
    setBusy(p); setError('');
    await removeKey(p);
    setEditing({ ...editing, [p]: false });
    await load();
    setBusy('');
  };

  return (
    <div className="modal-back" onClick={onClose} role="dialog" aria-modal="true" aria-label="API keys">
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <div>
            <h2>API keys</h2>
            <p>A run uses your key when you have one stored, and the server's otherwise.</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="modal-body">
          {state && !state.available && (
            <div className="note-inline warn">
              Key storage is off on this server — {state.reason}. Migrations will use the
              server's own credential.
            </div>
          )}

          {PROVIDERS.map((p) => {
            const have = stored(p.id);
            const isEditing = editing[p.id] || (!have && state?.available);
            return (
              <div className="key-row" key={p.id}>
                <div className="key-head">
                  <b>{p.label}</b>
                  {have
                    ? <span className="chip hist-status complete">Your key</span>
                    : serverHas(p.id)
                      ? <span className="chip hist-status">Using server key</span>
                      : <span className="chip hist-status error">No key</span>}
                </div>
                <div className="key-help mono">{p.help}</div>

                {have && !isEditing && (
                  <div className="key-set">
                    <input type="text" readOnly value={DOTS} aria-label={`${p.label} key, hidden`} />
                    <code className="key-hint" title="the only part of your key we can show">{have.hint}</code>
                    <button className="btn-mini" disabled={busy === p.id}
                      onClick={() => setEditing({ ...editing, [p.id]: true })}>Change</button>
                    <button className="btn-mini danger" disabled={busy === p.id}
                      onClick={() => drop(p.id)}>Remove</button>
                  </div>
                )}

                {isEditing && (
                  <div className="key-entry">
                    <input type="password" autoComplete="off" autoFocus={!!have}
                      placeholder={have ? 'Paste the new key' : 'Paste your key'}
                      value={draft[p.id] || ''} disabled={!state?.available || busy === p.id}
                      onChange={(e) => setDraft({ ...draft, [p.id]: e.target.value })}
                      onKeyDown={(e) => { if (e.key === 'Enter' && draft[p.id]) save(p.id); }} />
                    <button className="btn" disabled={!state?.available || !draft[p.id] || busy === p.id}
                      onClick={() => save(p.id)}>
                      {busy === p.id ? 'Saving…' : have ? 'Replace' : 'Save'}
                    </button>
                    {have && (
                      <button className="btn ghost" disabled={busy === p.id}
                        onClick={() => { setEditing({ ...editing, [p.id]: false }); setDraft({ ...draft, [p.id]: '' }); }}>
                        Cancel
                      </button>
                    )}
                  </div>
                )}

                {saved === p.id && <div className="key-ok">✓ Saved. Your next run will use it.</div>}
                {!have && !serverHas(p.id) && (
                  <div className="key-warn">
                    Neither you nor the server has a {p.label} key — a run on this provider
                    would fail. Mock runs are unaffected.
                  </div>
                )}
              </div>
            );
          })}

          {error && <div className="signin-err" role="alert">{error}</div>}
        </div>

        <p className="hist-note">
          Keys are encrypted before they are written and are never sent back to the browser —
          you can replace one, not read it. Removing yours reverts to the server's credential.
        </p>
      </div>
    </div>
  );
}
