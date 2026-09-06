import { useEffect, useRef, useState } from 'react';
import { saveKey } from '../api';

/**
 * The key a run needs, asked for at the moment it is needed. [1.50]
 *
 * Before this, choosing Anthropic without a key started the run anyway on whatever
 * credential the *server* happened to hold. Two people were misled at once: the user, who
 * believed they were spending their own credit, and the operator, who was. The cockpit
 * even said "no key configured" beside the provider and started regardless — the
 * interface and the system disagreeing in front of the person using them.
 *
 * **Why a dialog and not a redirect.** Sending someone to an account page mid-task means
 * losing the upload they just made and the options they just set. The key is wanted for
 * one reason, right now, so it is asked for here — with the account page one click away
 * for anyone who would rather manage credentials in one place.
 *
 * **Why the save checkbox is off by default.** Storing a credential is a decision with
 * consequences past this run, and a box already ticked is not a decision. Unticked, the
 * key is sent with this run and never written down: it lives as a closure variable in the
 * worker thread and dies with it. Ticked, it is encrypted into the vault and reused.
 *
 * The field is `type="password"` with `autocomplete="off"` — not to hide it from its
 * owner, but to keep it out of browser credential stores and screen shares, which is
 * where a pasted key most often escapes.
 */
export default function ProviderKey({
  provider, message, storageAvailable, storageReason, onCancel, onContinue, onOpenAccount,
}: {
  provider: string;
  message: string;
  storageAvailable: boolean;
  storageReason: string;
  onCancel: () => void;
  onContinue: (key: string, saved: boolean) => void;
  onOpenAccount: () => void;
}) {
  const [key, setKey] = useState('');
  const [save, setSave] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    field.current?.focus();
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel(); };
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [onCancel]);

  const label = provider.charAt(0).toUpperCase() + provider.slice(1);
  const trimmed = key.trim();
  // The server applies the real rule; this only stops an obviously empty submission
  // turning into a round trip and a red box.
  const tooShort = trimmed.length > 0 && trimmed.length < 12;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!trimmed || tooShort || busy) return;
    setBusy(true);
    setError('');
    try {
      // Saving first, so a stored key that the server rejects is reported here rather
      // than surfacing later as a run that will not start.
      if (save) await saveKey(provider, trimmed);
      onContinue(trimmed, save);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that key.');
      setBusy(false);
    }
  }

  return (
    <div className="modal-back" role="dialog" aria-modal="true"
         aria-label={`${label} API key`}>
      <div className="modal modal-sm" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <div>
            <h2>{label} key needed</h2>
            <p className="sub">{message}</p>
          </div>
          <button className="icon-btn" onClick={onCancel} aria-label="Close">✕</button>
        </header>

        <form className="modal-body" onSubmit={submit}>
          <label className="field-label" htmlFor="provider-key">
            {label} API key
          </label>
          <input
            id="provider-key"
            ref={field}
            type="password"
            autoComplete="off"
            spellCheck={false}
            className="key-input"
            placeholder="Paste your key"
            value={key}
            onChange={(e) => { setKey(e.target.value); setError(''); }}
          />
          {tooShort && <p className="hint key-warn">That looks too short to be a key.</p>}
          {error && <p className="hint key-warn">{error}</p>}

          {storageAvailable ? (
            <label className="check-row">
              <input type="checkbox" checked={save}
                     onChange={(e) => setSave(e.target.checked)} />
              <span>
                Save to my account
                <span className="hint">
                  {save
                    ? 'Encrypted on the server and reused for your future runs.'
                    : 'Left unticked, this key is used for this run only and never stored.'}
                </span>
              </span>
            </label>
          ) : (
            <p className="hint">
              This server cannot store keys{storageReason ? ` — ${storageReason}` : ''}, so
              this key will be used for this run only.
            </p>
          )}

          <footer className="modal-foot">
            <button type="button" className="link-btn" onClick={onOpenAccount}>
              Manage keys in My Account
            </button>
            <div className="foot-actions">
              <button type="button" className="btn ghost" onClick={onCancel}>Cancel</button>
              <button type="submit" className="btn primary"
                      disabled={!trimmed || tooShort || busy}>
                {busy ? 'Saving…' : 'Start migration'}
              </button>
            </div>
          </footer>
        </form>
      </div>
    </div>
  );
}
