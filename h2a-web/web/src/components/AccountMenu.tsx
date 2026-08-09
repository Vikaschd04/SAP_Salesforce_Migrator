import { useEffect, useRef, useState } from 'react';
import type { Me } from '../api';

/**
 * The account menu.
 *
 * Keys and Sign out were loose buttons in the topbar, which put a destructive action
 * (sign out) one stray click from a routine one. Collecting them behind the avatar also
 * gives identity somewhere to live: who you are signed in as is worth being able to
 * check without hunting for it.
 */

export default function AccountMenu({ user, onKeys, onSignOut }: {
  user: NonNullable<Me['user']> & { created?: number };
  onKeys: () => void;
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on an outside click or Escape — a menu that traps you is worse than no menu.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const initial = (user.name || user.email).slice(0, 1).toUpperCase();
  const since = user.created
    ? new Date(user.created * 1000).toLocaleDateString(undefined,
        { year: 'numeric', month: 'short', day: 'numeric' })
    : null;

  return (
    <div className="acct" ref={ref}>
      <button className={`acct-btn ${open ? 'open' : ''}`} onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu" aria-expanded={open} title={user.email}>
        <span className="acct-badge">{initial}</span>
        <span className="acct-chev">▾</span>
      </button>

      {open && (
        <div className="acct-menu" role="menu">
          <div className="acct-id">
            <span className="acct-badge lg">{initial}</span>
            <div className="acct-id-txt">
              <b>{user.name}</b>
              <span title={user.email}>{user.email}</span>
            </div>
          </div>

          <dl className="acct-facts">
            <div><dt>Role</dt><dd>{user.role === 'admin' ? 'Administrator' : 'Member'}</dd></div>
            {since && <div><dt>Member since</dt><dd>{since}</dd></div>}
            <div><dt>Account ID</dt><dd className="mono">{user.id.slice(0, 12)}</dd></div>
          </dl>

          <div className="acct-sep" />

          <button className="acct-item" role="menuitem"
            onClick={() => { setOpen(false); onKeys(); }}>
            <span>🔑</span> API keys
            <span className="acct-item-sub">Use your own provider credentials</span>
          </button>

          <button className="acct-item danger" role="menuitem"
            onClick={() => { setOpen(false); onSignOut(); }}>
            <span>⤴</span> Sign out
          </button>
        </div>
      )}
    </div>
  );
}
