"""Multi-user authentication, sessions, roles, and usage quotas.

The legacy private release stored one password and raw session tokens in
``data/user_data/auth.json``. The first multi-user startup imports that owner
credential and its live sessions into SQLite without moving or rewriting the
owner's existing user data. New users receive isolated tenant directories.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets as _secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PBKDF2_ITER = 200_000
_SALT_LEN = 16
_TOKEN_BYTES = 32
MIN_PASSWORD_LENGTH = 6
SESSION_TTL = 30 * 24 * 3600
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")
_init_lock = threading.Lock()
_initialized_path: Path | None = None


def _db_path() -> Path:
    from app.config import settings

    path = settings.data_dir / "control" / "identity.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _legacy_path() -> Path:
    from app.config import settings

    return settings.data_dir / "user_data" / "auth.json"


def _connect() -> sqlite3.Connection:
    _ensure_schema()
    conn = sqlite3.connect(_db_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_schema() -> None:
    global _initialized_path
    path = _db_path()
    if _initialized_path == path and path.exists():
        return
    with _init_lock:
        if _initialized_path == path and path.exists():
            return
        conn = sqlite3.connect(path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_norm TEXT NOT NULL UNIQUE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                    status TEXT NOT NULL DEFAULT 'active',
                    legacy_home INTEGER NOT NULL DEFAULT 0,
                    ai_daily_limit INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS usage_daily (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    metric TEXT NOT NULL,
                    day TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, metric, day)
                );
                CREATE TABLE IF NOT EXISTS registration_daily (
                    source_hash TEXT NOT NULL,
                    day TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (source_hash, day)
                );
                CREATE TABLE IF NOT EXISTS hermes_profiles (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    profile_name TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'ready', 'error')),
                    last_error TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                DROP TABLE IF EXISTS admin_audit_events;
                """
            )
            _migrate_legacy_owner(conn)
            conn.commit()
        finally:
            conn.close()
        _initialized_path = path


def _migrate_legacy_owner(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None:
        return
    path = _legacy_path()
    if not path.exists():
        return
    try:
        legacy = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("legacy auth.json migration skipped: %s", exc)
        return
    password_hash = str(legacy.get("password_hash") or "")
    password_salt = str(legacy.get("password_salt") or "")
    if not password_hash or not password_salt:
        return
    from app.config import settings

    username = _normalize_username(settings.auth_owner_username or "admin")
    now = int(time.time())
    conn.execute(
        """INSERT INTO users
           (id, username, username_norm, password_salt, password_hash, role, status,
            legacy_home, ai_daily_limit, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'admin', 'active', 1, NULL, ?, ?)""",
        ("owner", username, username.casefold(), password_salt, password_hash, now, now),
    )
    for raw_token, expires_at in (legacy.get("sessions") or {}).items():
        if isinstance(raw_token, str) and isinstance(expires_at, (int, float)) and expires_at > now:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?, 'owner', ?, ?)",
                (_token_hash(raw_token), now, int(expires_at)),
            )
    logger.info("legacy single-user authentication imported as owner account")


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or _secrets.token_bytes(_SALT_LEN)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
    return salt.hex(), digest.hex()


def _verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
    return _secrets.compare_digest(actual, expected)


def _normalize_username(username: str) -> str:
    value = str(username or "").strip()
    if not _USERNAME_RE.fullmatch(value):
        raise ValueError("用户名需为 3-32 位字母、数字、点、横线或下划线")
    return value


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "status": row["status"],
        "legacy_home": bool(row["legacy_home"]),
        "ai_daily_limit": row["ai_daily_limit"],
    }


def public_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {key: user[key] for key in ("id", "username", "role")}


def user_by_id(user_id: str) -> dict[str, Any] | None:
    """Return one active principal without exposing credential columns."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id=? AND status='active'",
            (str(user_id),),
        ).fetchone()
        return _row_to_user(row)


def _default_hermes_profile_name(user_id: str) -> str:
    from app.config import settings

    if user_id == "owner":
        return settings.hermes_owner_profile.strip().lower() or "one-trading"
    safe_user_id = re.sub(r"[^a-z0-9_-]", "-", user_id.lower())
    return f"ot-{safe_user_id}"[:64]


def _local_owner_principal() -> dict[str, Any]:
    """Return the passwordless local-development owner identity.

    Before access authentication is configured, the HTTP middleware only
    permits loopback/private-network requests and ``user_context`` exposes the
    legacy owner identity.  Hermes still needs a stable Profile mapping at
    that stage, but creating a ``users`` row would incorrectly make login look
    configured and would require inventing a password.  Keep that compatibility
    identity virtual until the user explicitly sets a password.
    """
    from app.config import settings

    return {
        "id": "owner",
        "username": settings.auth_owner_username or "admin",
        "role": "admin",
        "status": "active",
        "legacy_home": True,
        "ai_daily_limit": None,
    }


def _virtual_owner_profile_record() -> dict[str, Any]:
    return {
        "user_id": "owner",
        "profile_name": _default_hermes_profile_name("owner"),
        "status": "pending",
        "last_error": None,
        "created_at": 0,
        "updated_at": 0,
    }


def ensure_hermes_profile(user: dict[str, Any]) -> dict[str, Any]:
    """Return the stable one-account-to-one-profile assignment.

    This only changes the identity control plane. Physical Hermes files are
    provisioned lazily by the Hermes tenant Module so account creation does not
    depend on gateway availability.
    """
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise ValueError("用户身份缺少 id")
    now = int(time.time())
    profile_name = _default_hermes_profile_name(user_id)
    with _db() as conn:
        identity_exists = conn.execute(
            "SELECT 1 FROM users WHERE id=? AND status='active'",
            (user_id,),
        ).fetchone()
        if identity_exists is None:
            identity_is_empty = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None
            if (
                identity_is_empty
                and user_id == "owner"
                and user.get("role") == "admin"
                and user.get("legacy_home") is True
            ):
                return _virtual_owner_profile_record()
            raise ValueError("Hermes Profile 用户身份不存在或已停用")
        conn.execute(
            """INSERT OR IGNORE INTO hermes_profiles
               (user_id, profile_name, status, last_error, created_at, updated_at)
               VALUES (?, ?, 'pending', NULL, ?, ?)""",
            (user_id, profile_name, now, now),
        )
        row = conn.execute(
            "SELECT * FROM hermes_profiles WHERE user_id=?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("无法建立 Hermes Profile 映射")
    return dict(row)


def user_for_hermes_profile(profile_name: str) -> dict[str, Any] | None:
    with _db() as conn:
        row = conn.execute(
            """SELECT u.* FROM hermes_profiles hp
               JOIN users u ON u.id=hp.user_id
               WHERE hp.profile_name=? AND u.status='active'""",
            (str(profile_name).strip().lower(),),
        ).fetchone()
        user = _row_to_user(row)
        if user is not None:
            return user
        identity_is_empty = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None
        if (
            identity_is_empty
            and str(profile_name).strip().lower() == _default_hermes_profile_name("owner")
        ):
            return _local_owner_principal()
        return None


def hermes_profile_for_user(user_id: str) -> dict[str, Any] | None:
    """Read an existing account/Profile mapping without creating or updating it."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM hermes_profiles WHERE user_id=?",
            (str(user_id),),
        ).fetchone()
        if row is not None:
            return dict(row)
        identity_is_empty = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None
        if identity_is_empty and str(user_id) == "owner":
            return _virtual_owner_profile_record()
        return None


def set_hermes_profile_status(
    user_id: str,
    status: str,
    last_error: str | None = None,
) -> None:
    if status not in {"pending", "ready", "error"}:
        raise ValueError("invalid Hermes profile status")
    with _db() as conn:
        conn.execute(
            """UPDATE hermes_profiles
               SET status=?, last_error=?, updated_at=?
               WHERE user_id=?""",
            (status, (last_error or "")[:500] or None, int(time.time()), user_id),
        )


def is_configured() -> bool:
    with _db() as conn:
        return (
            conn.execute(
                "SELECT 1 FROM users WHERE role='admin' AND status='active' LIMIT 1"
            ).fetchone()
            is not None
        )


def _owner_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM users WHERE role='admin' AND status='active' ORDER BY legacy_home DESC, created_at LIMIT 1"
    ).fetchone()


def set_password(password: str) -> None:
    """Backward-compatible owner setup/change operation."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码至少 {MIN_PASSWORD_LENGTH} 位")
    salt, password_hash = _hash_password(password)
    from app.config import settings

    with _db() as conn:
        owner = _owner_row(conn)
        now = int(time.time())
        if owner is None:
            username = _normalize_username(settings.auth_owner_username or "admin")
            conn.execute(
                """INSERT INTO users
                   (id, username, username_norm, password_salt, password_hash, role, status,
                    legacy_home, ai_daily_limit, created_at, updated_at)
                   VALUES ('owner', ?, ?, ?, ?, 'admin', 'active', 1, NULL, ?, ?)""",
                (username, username.casefold(), salt, password_hash, now, now),
            )
            user_id = "owner"
        else:
            user_id = owner["id"]
            conn.execute(
                "UPDATE users SET password_salt=?, password_hash=?, updated_at=? WHERE id=?",
                (salt, password_hash, now, user_id),
            )
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


def bootstrap_from_env() -> bool:
    from app.config import settings

    password = (settings.auth_password or "").strip()
    if not password or is_configured():
        return False
    set_password(password)
    logger.info("owner account bootstrapped from AUTH_PASSWORD")
    return True


def _find_user_for_login(conn: sqlite3.Connection, username: str | None) -> sqlite3.Row | None:
    if username:
        return conn.execute(
            "SELECT * FROM users WHERE username_norm=? AND status='active'",
            (username.strip().casefold(),),
        ).fetchone()
    return _owner_row(conn)


def verify_credentials(password: str, username: str | None = None) -> dict[str, Any] | None:
    with _db() as conn:
        row = _find_user_for_login(conn, username)
        if row is None or not _verify_password(
            password, row["password_salt"], row["password_hash"]
        ):
            return None
        return _row_to_user(row)


def _create_session(conn: sqlite3.Connection, user_id: str) -> str:
    from app.config import settings

    token = _secrets.token_urlsafe(_TOKEN_BYTES)
    now = int(time.time())
    ttl = max(1, int(settings.user_session_ttl_days)) * 24 * 3600
    conn.execute(
        "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (_token_hash(token), user_id, now, now + ttl),
    )
    return token


def verify_and_create_session(password: str, username: str | None = None) -> str | None:
    with _db() as conn:
        row = _find_user_for_login(conn, username)
        if row is None or not _verify_password(
            password, row["password_salt"], row["password_hash"]
        ):
            return None
        return _create_session(conn, row["id"])


def register_user(
    username: str,
    password: str,
    invite_code: str = "",
    registration_source: str = "unknown",
) -> tuple[dict[str, Any], str]:
    from app.config import settings

    if not settings.public_registration_enabled:
        raise PermissionError("公开注册尚未开启")
    expected_invite = (settings.public_registration_invite_code or "").strip()
    if expected_invite and not _secrets.compare_digest(invite_code.strip(), expected_invite):
        raise PermissionError("邀请码无效")
    username = _normalize_username(username)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码至少 {MIN_PASSWORD_LENGTH} 位")
    salt, password_hash = _hash_password(password)
    now = int(time.time())
    user_id = f"usr_{_secrets.token_hex(8)}"
    day = datetime.now(UTC).date().isoformat()
    source_hash = hashlib.sha256(registration_source.encode("utf-8")).hexdigest()
    try:
        with _db() as conn:
            user_count = conn.execute(
                "SELECT COUNT(*) AS n FROM users WHERE role='user'"
            ).fetchone()["n"]
            if int(settings.public_max_users) >= 0 and int(user_count) >= int(
                settings.public_max_users
            ):
                raise PermissionError("公开用户数量已达服务器上限")
            daily_limit = max(0, int(settings.public_registration_daily_per_ip))
            source_row = conn.execute(
                "SELECT count FROM registration_daily WHERE source_hash=? AND day=?",
                (source_hash, day),
            ).fetchone()
            if daily_limit == 0 or (source_row and int(source_row["count"]) >= daily_limit):
                raise PermissionError("今日注册次数已达上限")
            conn.execute(
                """INSERT INTO users
                   (id, username, username_norm, password_salt, password_hash, role, status,
                    legacy_home, ai_daily_limit, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'user', 'active', 0, NULL, ?, ?)""",
                (user_id, username, username.casefold(), salt, password_hash, now, now),
            )
            conn.execute(
                """INSERT INTO registration_daily(source_hash, day, count) VALUES (?, ?, 1)
                   ON CONFLICT(source_hash, day) DO UPDATE SET count=count+1""",
                (source_hash, day),
            )
            conn.execute(
                """INSERT INTO hermes_profiles
                   (user_id, profile_name, status, last_error, created_at, updated_at)
                   VALUES (?, ?, 'pending', NULL, ?, ?)""",
                (user_id, _default_hermes_profile_name(user_id), now, now),
            )
            token = _create_session(conn, user_id)
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValueError("用户名已存在") from exc
    user = _row_to_user(row)
    assert user is not None
    return user, token


def authenticate_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    now = int(time.time())
    with _db() as conn:
        row = conn.execute(
            """SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.expires_at>? AND u.status='active'""",
            (_token_hash(token), now),
        ).fetchone()
        conn.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
        return _row_to_user(row)


def is_valid_session(token: str) -> bool:
    return authenticate_session(token) is not None


def revoke_session(token: str) -> None:
    if not token:
        return
    with _db() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def change_password(user_id: str, old_password: str, new_password: str) -> None:
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"新密码至少 {MIN_PASSWORD_LENGTH} 位")
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id=? AND status='active'", (user_id,)
        ).fetchone()
        if row is None or not _verify_password(
            old_password, row["password_salt"], row["password_hash"]
        ):
            raise PermissionError("旧密码错误")
        salt, password_hash = _hash_password(new_password)
        conn.execute(
            "UPDATE users SET password_salt=?, password_hash=?, updated_at=? WHERE id=?",
            (salt, password_hash, int(time.time()), user_id),
        )
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


def quota_status(user: dict[str, Any], metric: str = "ai_requests") -> dict[str, int | str | None]:
    from app.config import settings

    day = datetime.now(UTC).date().isoformat()
    limit = user.get("ai_daily_limit")
    if limit is None:
        limit = settings.user_ai_daily_quota
    with _db() as conn:
        row = conn.execute(
            "SELECT count FROM usage_daily WHERE user_id=? AND metric=? AND day=?",
            (user["id"], metric, day),
        ).fetchone()
    used = int(row["count"]) if row else 0
    return {
        "metric": metric,
        "day": day,
        "limit": int(limit),
        "used": used,
        "remaining": max(0, int(limit) - used),
    }


def consume_quota(user: dict[str, Any], metric: str = "ai_requests") -> dict[str, int | str | None]:
    status = quota_status(user, metric)
    limit = int(status["limit"] or 0)
    if user.get("role") == "admin" or limit < 0:
        return status
    if limit == 0 or int(status["used"] or 0) >= limit:
        raise PermissionError("今日 AI 使用额度已用完")
    with _db() as conn:
        conn.execute(
            """INSERT INTO usage_daily(user_id, metric, day, count) VALUES (?, ?, ?, 1)
               ON CONFLICT(user_id, metric, day) DO UPDATE SET count=count+1""",
            (user["id"], metric, status["day"]),
        )
    return quota_status(user, metric)
