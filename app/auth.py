"""Authentication and authorisation for Bayaan.

Everything here is deliberately small and dependency-free: PBKDF2 from the
standard library for passwords, `secrets` for session tokens, and the
`roles` / `permissions` / `permission_paths` / `role_permissions` tables for
the rules. No JWT, no framework, nothing to keep in sync with a package
version.

Two things are read from the database on every request rather than being
compiled in or cached:

  * which URL is protected (`permission_paths`, 20 rows)
  * which capabilities the signed-in user's role holds (`role_permissions`)

Both are tiny tables, so the cost is a couple of indexed lookups, and the
payoff is that an INSERT or DELETE takes effect on the *next request* — not
after a restart. That is the whole point of the design: access is data.

Passwords are stored as one self-describing string:

    pbkdf2_sha256$<iterations>$<salt-b64>$<hash-b64>

so the algorithm and its cost live with the value. Raising PBKDF2_ITERATIONS
later re-hashes a user on their next successful sign-in (`needs_rehash`)
instead of locking them out.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

import mysql.connector

from .config import DATABASE_CONFIG

# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

PBKDF2_ALGORITHM = "pbkdf2_sha256"
# OWASP's 2023 floor for PBKDF2-HMAC-SHA256. Stored per user, so this constant
# can be raised without a migration — existing hashes keep their own cost.
PBKDF2_ITERATIONS = 600_000

SESSION_COOKIE = "bayaan_session"
# Idle expiry: the deadline is pushed forward while the person is using the
# app, so this is "time since last activity", not "time since sign-in".
IDLE_SECONDS = 12 * 60 * 60
# "Remember me" only lengthens the window; it is still refreshed on use.
REMEMBER_SECONDS = 30 * 24 * 60 * 60
# Don't write to the sessions table on every request just to bump the clock.
TOUCH_AFTER_SECONDS = 5 * 60

# Methods a browser uses for a plain link or a form. A protected URL hit with
# one of these gets a redirect to /login instead of a JSON 401.
NAVIGATION_METHODS = {"GET", "HEAD"}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def connect():
    """A fresh connection. Callers own it and must close it."""
    return mysql.connector.connect(**DATABASE_CONFIG)


def _query_one(sql: str, params: tuple = ()) -> dict | None:
    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


def _query_all(sql: str, params: tuple = ()) -> list[dict]:
    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def _execute(sql: str, params: tuple = ()) -> int:
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Return the storable verifier for a new or changed password."""
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return "$".join(
        (
            PBKDF2_ALGORITHM,
            str(iterations),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored verifier.

    Never raises on a malformed stored value — a corrupt row must read as
    "wrong password", not as a 500 that tells an attacker the row is odd.
    """
    try:
        algorithm, iterations, salt_b64, hash_b64 = stored.split("$")
        if algorithm != PBKDF2_ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, TypeError):
        return False
    # Constant-time: a length or prefix difference must not be observable.
    return hmac.compare_digest(digest, expected)


def needs_rehash(stored: str) -> bool:
    """True when the hash was made with an older (cheaper) cost."""
    try:
        algorithm, iterations, _, _ = stored.split("$")
    except (ValueError, TypeError):
        return True
    return algorithm != PBKDF2_ALGORITHM or int(iterations) < PBKDF2_ITERATIONS


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_user_by_username(username: str) -> dict | None:
    return _query_one(
        """
        SELECT u.id, u.username, u.display_name, u.password_hash, u.role_id,
               u.is_active, r.name AS role
          FROM users u
          JOIN roles r ON r.id = u.role_id
         WHERE u.username = %s
        """,
        (username,),
    )


def get_user(user_id: int) -> dict | None:
    return _query_one(
        """
        SELECT u.id, u.username, u.display_name, u.is_active, u.role_id,
               r.name AS role
          FROM users u
          JOIN roles r ON r.id = u.role_id
         WHERE u.id = %s
        """,
        (user_id,),
    )


def authenticate(username: str, password: str) -> dict | None:
    """Return the user when the credentials are right, else None.

    A disabled account is indistinguishable from a wrong password here on
    purpose: the caller shows one message either way, so this function cannot
    be used to discover which usernames exist.
    """
    user = get_user_by_username(username)
    if not user or not user["is_active"]:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    if needs_rehash(user["password_hash"]):
        # The password just proved correct, so this is the safe moment to
        # upgrade the stored cost.
        _execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (hash_password(password), user["id"]),
        )
    _execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (user["id"],))
    return get_user(user["id"])


def create_user(
    username: str,
    password: str,
    role: str = "viewer",
    display_name: str | None = None,
) -> int:
    role_row = _query_one("SELECT id FROM roles WHERE name = %s", (role,))
    if not role_row:
        raise ValueError(f"unknown role: {role}")
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (username, display_name, password_hash, role_id)
            VALUES (%s, %s, %s, %s)
            """,
            (username, display_name, hash_password(password), role_row["id"]),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def set_password(user_id: int, password: str) -> None:
    _execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (hash_password(password), user_id),
    )


def set_active(user_id: int, active: bool) -> None:
    _execute(
        "UPDATE users SET is_active = %s WHERE id = %s", (1 if active else 0, user_id)
    )
    if not active:
        # A disabled account must not keep working through sessions it already
        # holds; the sign-in check alone would leave them valid until expiry.
        delete_user_sessions(user_id)


def list_users() -> list[dict]:
    return _query_all(
        """
        SELECT u.id, u.username, u.display_name, u.is_active, u.created_at,
               u.last_login_at, r.name AS role
          FROM users u
          JOIN roles r ON r.id = u.role_id
         ORDER BY u.id
        """
    )


def list_roles() -> list[dict]:
    return _query_all("SELECT id, name, description FROM roles ORDER BY id")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(
    user_id: int,
    remember: bool = False,
    ip: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Create a session row and return the cookie token.

    The token itself is never stored — only its SHA-256 — so the sessions
    table is useless to anyone who reads a copy of it.
    """
    token = secrets.token_urlsafe(32)
    seconds = REMEMBER_SECONDS if remember else IDLE_SECONDS
    _execute(
        """
        INSERT INTO sessions (token_hash, user_id, expires_at, remember_me, ip, user_agent)
        VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL %s SECOND), %s, %s, %s)
        """,
        (
            _token_hash(token),
            user_id,
            seconds,
            1 if remember else 0,
            ip,
            (user_agent or "")[:255] or None,
        ),
    )
    return token


def get_session(token: str | None) -> dict | None:
    """Resolve a cookie token to its user, or None if it is not usable.

    Expiry and `is_active` are part of the lookup, so a revoked account or a
    stale session is rejected here rather than by every caller.
    """
    if not token:
        return None
    row = _query_one(
        """
        SELECT s.id AS session_id, s.remember_me, s.expires_at,
               u.id, u.username, u.display_name, u.role_id, u.is_active,
               r.name AS role
          FROM sessions s
          JOIN users u ON u.id = s.user_id
          JOIN roles r ON r.id = u.role_id
         WHERE s.token_hash = %s
           AND s.expires_at > NOW()
           AND u.is_active = 1
        """,
        (_token_hash(token),),
    )
    if not row:
        return None
    # Refresh the idle deadline, but not on every single request.
    _execute(
        """
        UPDATE sessions
           SET last_seen_at = NOW(),
               expires_at = DATE_ADD(NOW(), INTERVAL %s SECOND)
         WHERE id = %s
           AND last_seen_at < DATE_SUB(NOW(), INTERVAL %s SECOND)
        """,
        (
            REMEMBER_SECONDS if row["remember_me"] else IDLE_SECONDS,
            row["session_id"],
            TOUCH_AFTER_SECONDS,
        ),
    )
    return row


def delete_session(token: str | None) -> None:
    if not token:
        return
    _execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))


def delete_user_sessions(user_id: int) -> None:
    _execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))


def purge_expired_sessions() -> int:
    return _execute("DELETE FROM sessions WHERE expires_at <= NOW()")


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

def _method_matches(http_methods: str, method: str) -> bool:
    if http_methods == "*":
        return True
    return method.upper() in {
        m.strip().upper() for m in http_methods.split(",") if m.strip()
    }


def _prefix_matches(path_prefix: str, path: str) -> bool:
    """A prefix matches the path itself, or anything below it on a boundary.

    `/reader` must not match `/reader-mushaf`, and `/` must not match the
    whole site — hence the explicit `/` boundary rather than startswith.
    The root is special-cased: stripping its slash would leave an empty
    prefix, and `"".rstrip("/") + "/"` is `"/"`, which matches everything.
    """
    if path_prefix in ("", "/"):
        return path == "/"
    if path == path_prefix:
        return True
    return path.startswith(path_prefix.rstrip("/") + "/")


def resolve_rule(path: str, method: str) -> dict | None:
    """The permission_paths row that governs this request, if any.

    The longest matching prefix wins, so a narrower row can override a wider
    one. Reading the table per request is what makes a new grant take effect
    immediately (see the module docstring).
    """
    rows = _query_all(
        """
        SELECT pp.path_prefix, pp.http_methods, pp.is_public, p.perm_key
          FROM permission_paths pp
          JOIN permissions p ON p.id = pp.permission_id
        """
    )
    best = None
    for row in rows:
        if not _method_matches(row["http_methods"], method):
            continue
        if not _prefix_matches(row["path_prefix"], path):
            continue
        if best is None or len(row["path_prefix"]) > len(best["path_prefix"]):
            best = row
    return best


def role_permissions(role_id: int) -> set[str]:
    """Capabilities held by a role, read fresh so grants apply immediately."""
    rows = _query_all(
        """
        SELECT p.perm_key
          FROM role_permissions rp
          JOIN permissions p ON p.id = rp.permission_id
         WHERE rp.role_id = %s
        """,
        (role_id,),
    )
    return {row["perm_key"] for row in rows}


def user_can(user: dict | None, perm_key: str) -> bool:
    if not user or not user.get("is_active"):
        return False
    return perm_key in role_permissions(user["role_id"])


def list_permission_paths() -> list[dict]:
    """Every URL the guard knows about — used by the management CLI."""
    return _query_all(
        """
        SELECT pp.path_prefix, pp.http_methods, pp.is_public, p.perm_key
          FROM permission_paths pp
          JOIN permissions p ON p.id = pp.permission_id
         ORDER BY pp.path_prefix, pp.http_methods
        """
    )


# ---------------------------------------------------------------------------
# Small helpers used by the routes
# ---------------------------------------------------------------------------

def safe_next(target: str | None, fallback: str = "/") -> str:
    """Only ever redirect to a path on this site.

    Without this, `?next=https://example.com` would turn the sign-in page into
    an open redirect. A leading `//` is rejected too: browsers read it as a
    protocol-relative URL to another host.
    """
    if not target:
        return fallback
    if not target.startswith("/") or target.startswith("//"):
        return fallback
    return target


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
