"""
keyvault.py — per-tenant provider credentials.

Until now every tenant spent the server's own ANTHROPIC_API_KEY. With one team that is
merely untidy; with two organisations it is a billing problem and a trust problem at the
same time — nobody can tell whose run burned the quota, and everyone is implicitly
sharing one credential.

Design decisions worth stating, because storing other people's API keys deserves them:

**Encrypted at rest, with a key that is not in the database.** Fernet (AES-128-CBC +
HMAC) under a key derived from `H2A_SECRET_KEY`. If the secret lived alongside the
ciphertext the encryption would be decoration, so without that variable this feature
stays *off* rather than pretending: runs fall back to the server's shared credential and
the UI says so plainly.

**Plaintext never leaves the server.** The API returns a masked hint (`sk-…7f3a`) so
someone can confirm which key is stored, never the key itself. There is no read-back
endpoint; a key can be replaced, not retrieved.

**Optional dependency.** `cryptography` is not in the engine's requirements, and a
deployment that lacks it should degrade rather than crash on import — so the module
loads either way and reports `available()`.
"""

from __future__ import annotations

import base64
import hashlib
import os
import threading
import time

import store

try:                                            # optional; absence disables the feature
    from cryptography.fernet import Fernet, InvalidToken
    _HAVE_CRYPTO = True
except Exception:                               # pragma: no cover - environment dependent
    Fernet = None                               # type: ignore
    InvalidToken = Exception                    # type: ignore
    _HAVE_CRYPTO = False

_lock = threading.Lock()

# A fixed salt is acceptable here: the secret is high-entropy and per-deployment, and a
# rotating salt would make existing ciphertext unreadable after a restart.
_SALT = b"h2a-keyvault-v1"


def available() -> bool:
    """Can we store tenant keys at all? Both halves must be true."""
    return _HAVE_CRYPTO and bool(os.environ.get("H2A_SECRET_KEY"))


def why_unavailable() -> str:
    if not _HAVE_CRYPTO:
        return "the `cryptography` package is not installed on the server"
    if not os.environ.get("H2A_SECRET_KEY"):
        return "H2A_SECRET_KEY is not set, so keys could not be encrypted at rest"
    return ""


def _fernet():
    secret = os.environ.get("H2A_SECRET_KEY", "")
    dk = hashlib.scrypt(secret.encode("utf-8"), salt=_SALT, n=2 ** 14, r=8, p=1,
                        dklen=32, maxmem=64 * 1024 * 1024)
    return Fernet(base64.urlsafe_b64encode(dk))


def _conn():
    c = store._connect()
    if c is None:
        return None
    with _lock:
        c.execute("""CREATE TABLE IF NOT EXISTS provider_keys (
                       user_id TEXT, provider TEXT, ciphertext BLOB, hint TEXT,
                       updated REAL, PRIMARY KEY (user_id, provider))""")
        c.commit()
    return c


def mask(key: str) -> str:
    """Enough to recognise a key, not enough to use one."""
    key = (key or "").strip()
    return f"{key[:3]}…{key[-4:]}" if len(key) > 10 else "…"


def set_key(user_id: str, provider: str, key: str) -> dict:
    if not available():
        raise RuntimeError(why_unavailable())
    key = (key or "").strip()
    if len(key) < 12:
        raise ValueError("That does not look like an API key.")
    c = _conn()
    if c is None:
        raise RuntimeError("the database is not writable")
    with _lock:
        c.execute("INSERT OR REPLACE INTO provider_keys "
                  "(user_id, provider, ciphertext, hint, updated) VALUES (?,?,?,?,?)",
                  (user_id, provider, _fernet().encrypt(key.encode()), mask(key), time.time()))
        c.commit()
    return {"provider": provider, "hint": mask(key)}


def get_key(user_id: str | None, provider: str) -> str | None:
    """The tenant's key, or None to fall back to the server's own credential."""
    if not user_id or not available():
        return None
    c = _conn()
    if c is None:
        return None
    with _lock:
        row = c.execute("SELECT ciphertext FROM provider_keys WHERE user_id=? AND provider=?",
                        (user_id, provider)).fetchone()
    if not row:
        return None
    try:
        return _fernet().decrypt(row[0]).decode()
    except InvalidToken:
        # H2A_SECRET_KEY changed: the stored key is unreadable, not wrong. Falling back
        # silently is better than failing the run, and the UI still shows it as stored.
        return None


def list_keys(user_id: str) -> list[dict]:
    c = _conn()
    if c is None:
        return []
    with _lock:
        rows = c.execute("SELECT provider, hint, updated FROM provider_keys WHERE user_id=? "
                         "ORDER BY provider", (user_id,)).fetchall()
    return [{"provider": p, "hint": h, "updated": u} for p, h, u in rows]


def delete_key(user_id: str, provider: str) -> None:
    c = _conn()
    if c is None:
        return
    with _lock:
        c.execute("DELETE FROM provider_keys WHERE user_id=? AND provider=?", (user_id, provider))
        c.commit()
