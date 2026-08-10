import { useState } from 'react';
import Logo from './Logo';
import type { Me } from '../api';
import { login, signup, demoLogin } from '../api';

/**
 * The gate on a hosted deployment.
 *
 * Two panels: the left says what this is and why the login exists at all (people are
 * about to upload proprietary source, so the isolation promise belongs *here*, not
 * buried in docs); the right does the one job. On narrow screens the showcase drops
 * away entirely rather than pushing the form below the fold.
 */

const MIN_PW = 10;

export default function SignIn({ me, onIn }: { me: Me; onIn: (u: NonNullable<Me['user']>) => void }) {
  // Bootstrap case: nobody has registered yet, so open on the create-account form.
  const [mode, setMode] = useState<'in' | 'up'>(me.signup_open && !me.has_users ? 'up' : 'in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const isUp = mode === 'up';
  const pwOk = !isUp || password.length >= MIN_PW;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true); setError('');
    try {
      onIn(await (isUp ? signup(email, password) : login(email, password)));
    } catch (err: any) {
      setError(err.message || 'That did not work. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const swap = () => { setMode(isUp ? 'in' : 'up'); setError(''); };

  const tryDemo = async () => {
    setBusy(true); setError('');
    try { onIn(await demoLogin()); }
    catch (err: any) { setError(err.message || 'Demo sign-in is unavailable.'); }
    finally { setBusy(false); }
  };

  return (
    <div className="auth">
      <div className="auth-card">
        {/* ── showcase ── */}
        <aside className="auth-show">
          <div>
            <div className="signin-brand">
              <Logo size={38} />
              <div>
                <h1><span className="wm grad-text">H2A</span></h1>
                <div className="sub">Migration Cockpit</div>
              </div>
            </div>
            <h2 className="auth-tag">SAP Hybris to Salesforce, with a human at every gate.</h2>
          </div>

          <ul className="auth-points">
            <li><b>Your code stays yours.</b> Migrations and uploaded source are visible only to your account.</li>
            <li><b>Review before anything is written.</b> The first gate opens before a single AI call is made.</li>
            <li><b>Evidence, not claims.</b> Every business rule is traced to the code and test that carry it.</li>
          </ul>

          <div className="auth-foot">
            <span className="auth-dot" /> Runs are private per account
          </div>
        </aside>

        {/* ── form ── */}
        <form className="auth-form" onSubmit={submit}>
          <div className="auth-form-head">
            <h2>{isUp ? (me.has_users ? 'Create your account' : 'Create the first account') : 'Welcome back'}</h2>
            <p>
              {isUp
                ? me.has_users
                  ? 'You will see only your own migrations.'
                  : 'This first account administers the instance.'
                : 'Sign in to pick up where you left off.'}
            </p>
          </div>

          <label className="fld">
            <span>Email</span>
            <input type="email" value={email} required autoFocus autoComplete="username"
              placeholder="you@company.com" disabled={busy}
              onChange={(e) => setEmail(e.target.value)} />
          </label>

          <label className="fld">
            <span>Password</span>
            <div className="fld-wrap">
              <input type={show ? 'text' : 'password'} value={password} required
                minLength={isUp ? MIN_PW : undefined} disabled={busy}
                autoComplete={isUp ? 'new-password' : 'current-password'}
                placeholder={isUp ? `at least ${MIN_PW} characters` : '••••••••'}
                onChange={(e) => setPassword(e.target.value)} />
              <button type="button" className="fld-eye" tabIndex={-1}
                aria-label={show ? 'Hide password' : 'Show password'}
                onClick={() => setShow((v) => !v)}>{show ? '🙈' : '👁'}</button>
            </div>
            {isUp && (
              <span className={`fld-hint ${password && pwOk ? 'ok' : ''}`}>
                {password && pwOk ? '✓ Long enough' : `${MIN_PW} characters or more — length beats symbols`}
              </span>
            )}
          </label>

          {error && <div className="signin-err" role="alert">{error}</div>}

          <button className="btn primary lg auth-submit" type="submit" disabled={busy || !pwOk}>
            {busy ? <span className="spin" /> : null}
            {busy ? 'One moment…' : isUp ? 'Create account' : 'Sign in'}
          </button>

          {me.demo && (
            <div className="auth-demo">
              <span className="auth-or">or</span>
              <button type="button" className="btn auth-demo-btn" disabled={busy} onClick={tryDemo}>
                ▶ Explore with the demo account
              </button>
              <p className="auth-demo-note">
                Shared and read-write — everyone using it sees the same migrations. Don't
                upload anything confidential.
              </p>
            </div>
          )}

          {me.signup_open ? (
            <p className="auth-swap">
              {isUp ? 'Already have an account?' : 'No account yet?'}{' '}
              <button type="button" onClick={swap}>{isUp ? 'Sign in' : 'Create one'}</button>
            </p>
          ) : (
            !isUp && (
              <p className="signin-note">
                Registration is closed on this instance. Ask an administrator to enable it.
              </p>
            )
          )}
        </form>
      </div>
    </div>
  );
}
