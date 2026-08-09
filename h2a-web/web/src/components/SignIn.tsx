import { useState } from 'react';
import Logo from './Logo';
import type { Me } from '../api';
import { login, signup } from '../api';

/**
 * The gate on a hosted deployment. Deliberately plain: this screen's only job is to get
 * a known person through it, so it carries no marketing and no decoration that could
 * distract from the one action available.
 */
export default function SignIn({ me, onIn }: { me: Me; onIn: (u: NonNullable<Me['user']>) => void }) {
  // Bootstrap case: nobody has registered yet, so open on the create-account form.
  const [mode, setMode] = useState<'in' | 'up'>(me.signup_open && !me.has_users ? 'up' : 'in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      onIn(await (mode === 'in' ? login(email, password) : signup(email, password)));
    } catch (err: any) {
      setError(err.message || 'That did not work.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="signin">
      <form className="signin-card" onSubmit={submit}>
        <div className="signin-brand">
          <Logo size={40} />
          <div>
            <h1><span className="wm grad-text">H2A</span></h1>
            <div className="sub">Migration Cockpit</div>
          </div>
        </div>

        <h2 className="signin-title">
          {mode === 'in' ? 'Sign in' : me.has_users ? 'Create an account' : 'Create the first account'}
        </h2>
        <p className="signin-sub">
          {mode === 'in'
            ? 'Your migrations, and the source you upload, are visible only to you.'
            : me.has_users
              ? 'You will see only your own migrations.'
              : 'This first account administers the instance.'}
        </p>

        <label className="fld">
          <span>Email</span>
          <input type="email" value={email} required autoFocus autoComplete="username"
            onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
        </label>

        <label className="fld">
          <span>Password</span>
          <input type="password" value={password} required minLength={mode === 'up' ? 10 : undefined}
            autoComplete={mode === 'in' ? 'current-password' : 'new-password'}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === 'up' ? 'at least 10 characters' : ''} />
        </label>

        {error && <div className="signin-err">{error}</div>}

        <button className="btn primary lg" type="submit" disabled={busy}>
          {busy ? 'One moment…' : mode === 'in' ? 'Sign in' : 'Create account'}
        </button>

        {me.signup_open && (
          <button type="button" className="signin-alt"
            onClick={() => { setMode(mode === 'in' ? 'up' : 'in'); setError(''); }}>
            {mode === 'in' ? 'Need an account? Create one' : 'Already have an account? Sign in'}
          </button>
        )}
        {!me.signup_open && mode === 'in' && (
          <p className="signin-note">
            Registration is closed on this instance. Ask an administrator to enable it.
          </p>
        )}
      </form>
    </div>
  );
}
