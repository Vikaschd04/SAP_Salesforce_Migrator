"""
auth.py — real accounts and sessions.

Concurrency without authentication means every user shares one surface: anyone with
the URL can read anyone else's migration, including the source code they uploaded and
whatever business logic it contains. That is fine for one person on a laptop and
disqualifying for a hosted product, so this closes it.

Design notes worth knowing:

**Passwords** are hashed with scrypt (stdlib) using a per-user random salt and
parameters chosen to be deliberately slow. Comparisons are constant-time. Plaintext is
never stored, logged, or returned.

**Sessions** are opaque random tokens. Only their SHA-256 is stored, so a leaked
database does not hand over live sessions. They expire, and logout deletes them
server-side rather than just dropping the cookie.

**Signup is closed by default.** A public deployment with open registration is an open
door to your API credits and other tenants' source. The first account can always be
created (someone has to bootstrap), and after that it takes H2A_ALLOW_SIGNUP=1.

**Auth is on where it matters, off where it doesn't.** A hosted deploy always requires
it; a laptop does not, because forcing a login on a single-user local tool would be
security theatre that makes the CLI and the dashboard behave differently for no gain.
Set H2A_AUTH=1 to require it locally too.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time

import store

_lock = threading.Lock()

# scrypt work factors. n=2**15 keeps a single hash near ~100ms on ordinary hardware —
# slow enough to make offline cracking expensive, fast enough for an interactive login.
#
# maxmem must be set explicitly: these parameters need 128*n*r = 32 MiB, which is exactly
# OpenSSL's default ceiling, so every hash raises "memory limit exceeded" without it.
_N, _R, _P, _DKLEN = 2 ** 15, 8, 1, 64
_MAXMEM = 96 * 1024 * 1024

SESSION_COOKIE = "h2a_session"
SESSION_TTL = 14 * 24 * 3600          # 14 days


def auth_required() -> bool:
    """Hosted deploys always; local only on request."""
    return os.environ.get("H2A_AUTH", "").lower() in ("1", "true", "yes") \
        or os.environ.get("H2A_HOSTED") == "1"


def _conn() -> sqlite3.Connection | None:
    c = store._connect()
    if c is None:
        return None
    with _lock:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
                       id TEXT PRIMARY KEY, email TEXT UNIQUE, name TEXT,
                       salt BLOB, pw BLOB, created REAL, role TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS sessions (
                       token_hash TEXT PRIMARY KEY, user_id TEXT,
                       created REAL, expires REAL)""")
        c.execute("CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id)")
        c.commit()
    return c


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt,
                          n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM)


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def user_count() -> int:
    c = _conn()
    if c is None:
        return 0
    with _lock:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def signup_open() -> bool:
    """Someone has to create the first account; after that it takes a deliberate flag."""
    return user_count() == 0 or os.environ.get("H2A_ALLOW_SIGNUP", "").lower() in ("1", "true", "yes")


class AuthError(Exception):
    pass


def create_user(email: str, password: str, name: str = "") -> dict:
    email = _norm(email)
    if "@" not in email or len(email) < 5:
        raise AuthError("Enter a valid email address.")
    if len(password or "") < 10:
        # Long beats clever: a short password with a symbol in it is still weak.
        raise AuthError("Use a password of at least 10 characters.")
    c = _conn()
    if c is None:
        raise AuthError("Accounts are unavailable — the database is not writable.")

    uid, salt = secrets.token_hex(12), secrets.token_bytes(16)
    # The first account owns the instance; later ones are ordinary members.
    role = "admin" if user_count() == 0 else "member"
    try:
        with _lock:
            c.execute("INSERT INTO users (id, email, name, salt, pw, created, role) "
                      "VALUES (?,?,?,?,?,?,?)",
                      (uid, email, name.strip() or email.split("@")[0],
                       salt, _hash(password, salt), time.time(), role))
            c.commit()
    except sqlite3.IntegrityError:
        raise AuthError("An account with that email already exists.")
    return {"id": uid, "email": email, "name": name or email.split("@")[0], "role": role}


def verify_user(email: str, password: str) -> dict:
    """Authenticate, without telling an attacker which half was wrong."""
    c = _conn()
    if c is None:
        raise AuthError("Accounts are unavailable — the database is not writable.")
    with _lock:
        row = c.execute("SELECT id, email, name, salt, pw, role FROM users WHERE email = ?",
                        (_norm(email),)).fetchone()
    if row is None:
        # Spend comparable time on a missing user so response timing does not disclose
        # which addresses are registered.
        _hash(password or "", b"decoy-salt-000000")
        raise AuthError("Email or password is incorrect.")
    uid, mail, name, salt, expected, role = row
    if not hmac.compare_digest(_hash(password or "", salt), expected):
        raise AuthError("Email or password is incorrect.")
    return {"id": uid, "email": mail, "name": name, "role": role}


def create_session(user_id: str) -> str:
    """Return the raw token (given to the client once); only its hash is stored."""
    c = _conn()
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        c.execute("INSERT INTO sessions (token_hash, user_id, created, expires) VALUES (?,?,?,?)",
                  (hashlib.sha256(token.encode()).hexdigest(), user_id, now, now + SESSION_TTL))
        c.execute("DELETE FROM sessions WHERE expires < ?", (now,))     # opportunistic sweep
        c.commit()
    return token


def user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    c = _conn()
    if c is None:
        return None
    with _lock:
        row = c.execute(
            "SELECT u.id, u.email, u.name, u.role, u.created FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires > ?",
            (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    return None if row is None else {"id": row[0], "email": row[1], "name": row[2],
                                     "role": row[3], "created": row[4]}


def destroy_session(token: str | None) -> None:
    """Invalidate server-side — dropping the cookie alone would leave it usable."""
    if not token:
        return
    c = _conn()
    if c is None:
        return
    with _lock:
        c.execute("DELETE FROM sessions WHERE token_hash = ?",
                  (hashlib.sha256(token.encode()).hexdigest(),))
        c.commit()
