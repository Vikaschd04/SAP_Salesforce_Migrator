import { useEffect, useState } from 'react';
import { fetchKeys, saveKey, removeKey } from '../api';
import type { KeyState } from '../api';

/**
 * Your own provider credentials.
 *
 * Without one, a run spends the server's shared key — which on a shared instance means
 * nobody can tell whose migration burned the quota. Stored encrypted; the server never
 * hands a key back, so this shows a mask and offers replace-or-remove, never reveal.
 */

const PROVIDERS: { id: string; label: string; help: string }[] = [
  { id: 'anthropic', label: 'Anthropic', help: 'sk-ant-…  ·  console.anthropic.com' },
  { id: 'openrouter', label: 'OpenRouter', help: 'sk-or-…  ·  openrouter.ai/keys' },
];

export default function Keys({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [state, setState] = useState<KeyState | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');

  const load = () => fetchKeys().then(setState).catch(() => {});
  useEffect(() => { if (open) load(); }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const stored = (p: string) => state?.keys.find((k) => k.provider === p);

  const save = async (p: string) => {
    setBusy(p); setError(''); setSaved('');
    try {
      await saveKey(p, draft[p] || '');
      setDraft({ ...draft, [p]: '' });
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
    await load();
    setBusy('');
  };

  return (
    <div className="modal-back" onClick={onClose} role="dialog" aria-modal="true" aria-label="API keys">
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <div>
            <h2>Your API keys</h2>
            <p>Runs use your key when one is stored, and the server's shared key otherwise.</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="modal-body">
          {state && !state.available && (
            <div className="note-inline" style={{ color: 'var(--warn)', background: 'var(--warn-bg)' }}>
              Key storage is off on this server — {state.reason}. Migrations will use the
              server's own credential.
            </div>
          )}

          {PROVIDERS.map((p) => {
            const have = stored(p.id);
            return (
              <div className="key-row" key={p.id}>
                <div className="key-head">
                  <b>{p.label}</b>
                  {have ? <span className="chip hist-status complete">Stored</span>
                        : <span className="chip hist-status">Not set</span>}
                </div>
                <div className="key-help mono">{p.help}</div>

                {have && (
                  <div className="key-current">
                    <code>{have.hint}</code>
                    <button className="btn-mini" disabled={busy === p.id}
                      onClick={() => drop(p.id)}>Remove</button>
                  </div>
                )}

                <div className="key-entry">
                  <input type="password" autoComplete="off" placeholder={have ? 'Replace with a new key' : 'Paste your key'}
                    value={draft[p.id] || ''} disabled={!state?.available || busy === p.id}
                    onChange={(e) => setDraft({ ...draft, [p.id]: e.target.value })} />
                  <button className="btn" disabled={!state?.available || !draft[p.id] || busy === p.id}
                    onClick={() => save(p.id)}>
                    {busy === p.id ? 'Saving…' : have ? 'Replace' : 'Save'}
                  </button>
                </div>
                {saved === p.id && <div className="key-ok">✓ Saved. New runs will use it.</div>}
              </div>
            );
          })}

          {error && <div className="signin-err" role="alert">{error}</div>}
        </div>

        <p className="hist-note">
          Keys are encrypted before they are written and are never sent back to the browser —
          you can replace one, not read it. Removing a key reverts to the server's credential.
        </p>
      </div>
    </div>
  );
}
