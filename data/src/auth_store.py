"""SQLite/PostgreSQL persistence for authentication and ownership."""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SCRYPT_MAXMEM = 128 * 1024 * 1024
SCHEMA_VERSION = "001_auth_and_tenant"
_PG_PREFIXES = ("postgresql://", "postgres://")


class _Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class _Cursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, sqlite3.Row):
            return _Row(row)
        if isinstance(row, dict):
            return _Row(row)
        names = [item[0] for item in (self._cursor.description or [])]
        return _Row(zip(names, row))


class _Connection:
    def __init__(self, target: str):
        self.is_postgres = target.lower().startswith(_PG_PREFIXES)
        if self.is_postgres:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError("PostgreSQL authentication requires the psycopg driver") from exc
            self.raw = psycopg.connect(target)
            self.placeholder = "%s"
        else:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            self.raw = sqlite3.connect(target, timeout=10, check_same_thread=False)
            self.raw.row_factory = sqlite3.Row
            self.raw.execute("PRAGMA foreign_keys = ON")
            self.placeholder = "?"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            (self.raw.commit if exc_type is None else self.raw.rollback)()
        finally:
            self.raw.close()
        return False

    def execute(self, sql: str, params=()):
        if self.is_postgres:
            sql = sql.replace("?", "%s")
        return _Cursor(self.raw.execute(sql, params))


def postgres_available() -> bool:
    return importlib.util.find_spec("psycopg") is not None


def _is_postgres_target(target: str) -> bool:
    return target.lower().startswith(_PG_PREFIXES)


def _migration_path(target: str, migration_path: Optional[str]) -> Path:
    if migration_path is None:
        name = "001_auth_and_tenant_postgres.sql" if _is_postgres_target(target) else "001_auth_and_tenant.sql"
        return Path(__file__).parents[1] / "migrations" / name
    requested = Path(migration_path)
    if _is_postgres_target(target) and requested.name == "001_auth_and_tenant.sql":
        return requested.with_name("001_auth_and_tenant_postgres.sql")
    return requested


def _execute_script(connection: _Connection, script: str) -> None:
    for statement in re.split(r";\s*(?:\r?\n|$)", script):
        if statement.strip():
            connection.execute(statement.strip())


def ensure_schema(db_path: str, migration_path: Optional[str] = None) -> None:
    migration_sql = _migration_path(db_path, migration_path).read_text(encoding="utf-8")
    with _Connection(db_path) as connection:
        _execute_script(connection, migration_sql)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?) ON CONFLICT(version) DO NOTHING",
            (SCHEMA_VERSION, time.time()),
        )


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN, maxmem=SCRYPT_MAXMEM)
    return "$".join(("scrypt", f"n={SCRYPT_N},r={SCRYPT_R},p={SCRYPT_P}", salt.hex(), derived.hex()))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, params, salt_hex, expected_hex = encoded.split("$", 3)
        if algorithm != "scrypt":
            return False
        values = dict(item.split("=", 1) for item in params.split(","))
        expected = bytes.fromhex(expected_hex)
        derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=int(values["n"]), r=int(values["r"]), p=int(values["p"]), dklen=len(expected), maxmem=SCRYPT_MAXMEM)
        return hmac.compare_digest(derived, expected)
    except (KeyError, ValueError, TypeError):
        return False


def _principal_row(connection: _Connection, user_id: str, agency_id: str) -> dict[str, Any]:
    p = connection.placeholder
    row = connection.execute(
        f"SELECT u.id AS user_id, u.email, a.id AS agency_id, a.name AS agency_name, m.role FROM users u JOIN agency_memberships m ON m.user_id=u.id JOIN agencies a ON a.id=m.agency_id WHERE u.id={p} AND a.id={p} AND u.is_active=TRUE",
        (user_id, agency_id),
    ).fetchone()
    if row is None:
        raise ValueError("membership not found")
    return dict(row)


def _integrity_error(exc: Exception) -> bool:
    return isinstance(exc, sqlite3.IntegrityError) or exc.__class__.__name__ in {"IntegrityError", "UniqueViolation", "ForeignKeyViolation", "CheckViolation"}


def create_agency_owner(db_path: str, agency_name: str, email: str, password_hash: str) -> dict[str, Any]:
    now, user_id, agency_id = time.time(), str(uuid.uuid4()), str(uuid.uuid4())
    with _Connection(db_path) as connection:
        p = connection.placeholder
        try:
            connection.execute(f"INSERT INTO users(id,email,password_hash,created_at) VALUES ({p},{p},{p},{p})", (user_id, normalize_email(email), password_hash, now))
            connection.execute(f"INSERT INTO agencies(id,name,created_at) VALUES ({p},{p},{p})", (agency_id, agency_name, now))
            connection.execute(f"INSERT INTO agency_memberships(user_id,agency_id,role,created_at) VALUES ({p},{p},'owner',{p})", (user_id, agency_id, now))
        except Exception as exc:
            if _integrity_error(exc):
                raise ValueError("account already exists") from exc
            raise
        return _principal_row(connection, user_id, agency_id)


def get_user_for_login(db_path: str, email: str) -> Optional[dict[str, Any]]:
    with _Connection(db_path) as connection:
        p = connection.placeholder
        row = connection.execute(f"SELECT id,email,password_hash,is_active FROM users WHERE email={p}", (normalize_email(email),)).fetchone()
        return dict(row) if row else None


def get_membership(db_path: str, user_id: str, agency_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    with _Connection(db_path) as connection:
        p = connection.placeholder
        row = connection.execute(f"SELECT u.id AS user_id,u.email,a.id AS agency_id,a.name AS agency_name,m.role FROM users u JOIN agency_memberships m ON m.user_id=u.id JOIN agencies a ON a.id=m.agency_id WHERE u.id={p} AND ({p} IS NULL OR a.id={p}) AND u.is_active=TRUE ORDER BY a.created_at LIMIT 1", (user_id, agency_id, agency_id)).fetchone()
        return dict(row) if row else None


def create_auth_session(db_path: str, user_id: str, agency_id: str, idle_seconds: int, absolute_seconds: int) -> tuple[str, str]:
    now, token, csrf_token = time.time(), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with _Connection(db_path) as connection:
        p = connection.placeholder
        connection.execute(f"INSERT INTO auth_sessions(token_hash,user_id,csrf_hash,created_at,last_seen,idle_expires_at,absolute_expires_at,revoked_at,agency_id) VALUES ({p},{p},{p},{p},{p},{p},{p},NULL,{p})", (hashlib.sha256(token.encode()).hexdigest(), user_id, hashlib.sha256(csrf_token.encode()).hexdigest(), now, now, now + idle_seconds, now + absolute_seconds, agency_id))
    return token, csrf_token


def get_auth_session(db_path: str, token: str, idle_seconds: int) -> Optional[dict[str, Any]]:
    token_hash, now = hashlib.sha256(token.encode()).hexdigest(), time.time()
    with _Connection(db_path) as connection:
        p = connection.placeholder
        row = connection.execute(f"SELECT * FROM auth_sessions WHERE token_hash={p} AND revoked_at IS NULL", (token_hash,)).fetchone()
        if row is None:
            return None
        if row["idle_expires_at"] <= now or row["absolute_expires_at"] <= now:
            connection.execute(f"UPDATE auth_sessions SET revoked_at={p} WHERE token_hash={p}", (now, token_hash))
            return None
        connection.execute(f"UPDATE auth_sessions SET last_seen={p},idle_expires_at={p} WHERE token_hash={p}", (now, now + idle_seconds, token_hash))
        principal = _principal_row(connection, row["user_id"], row["agency_id"])
        principal.update(csrf_hash=row["csrf_hash"], token_hash=token_hash)
        return principal


def revoke_auth_session(db_path: str, token: str) -> None:
    with _Connection(db_path) as connection:
        p = connection.placeholder
        connection.execute(f"UPDATE auth_sessions SET revoked_at={p} WHERE token_hash={p}", (time.time(), hashlib.sha256(token.encode()).hexdigest()))


def switch_auth_session_agency(db_path: str, token: str, agency_id: str) -> None:
    with _Connection(db_path) as connection:
        p, token_hash = connection.placeholder, hashlib.sha256(token.encode()).hexdigest()
        user_row = connection.execute(f"SELECT user_id FROM auth_sessions WHERE token_hash={p}", (token_hash,)).fetchone()
        if user_row is None:
            raise ValueError("authentication session not found")
        if connection.execute(f"SELECT 1 FROM agency_memberships WHERE user_id={p} AND agency_id={p}", (user_row[0], agency_id)).fetchone() is None:
            raise ValueError("membership not found")
        connection.execute(f"UPDATE auth_sessions SET agency_id={p} WHERE token_hash={p}", (agency_id, token_hash))


def add_membership(db_path: str, user_id: str, agency_id: str, role: str) -> None:
    with _Connection(db_path) as connection:
        p = connection.placeholder
        connection.execute(f"INSERT INTO agency_memberships(user_id,agency_id,role,created_at) VALUES ({p},{p},{p},{p})", (user_id, agency_id, role, time.time()))


def create_invitation(db_path: str, agency_id: str, email: str, role: str, created_by_user_id: str, expires_seconds: int) -> str:
    token = secrets.token_urlsafe(32)
    with _Connection(db_path) as connection:
        p = connection.placeholder
        connection.execute(f"INSERT INTO agency_invitations(token_hash,agency_id,email,role,created_by_user_id,created_at,expires_at) VALUES ({p},{p},{p},{p},{p},{p},{p})", (hashlib.sha256(token.encode()).hexdigest(), agency_id, normalize_email(email), role, created_by_user_id, time.time(), time.time() + expires_seconds))
    return token


def accept_invitation(db_path: str, token: str, user_id: str, email: str) -> dict[str, Any]:
    token_hash, now = hashlib.sha256(token.encode()).hexdigest(), time.time()
    with _Connection(db_path) as connection:
        p = connection.placeholder
        invitation = connection.execute(f"SELECT * FROM agency_invitations WHERE token_hash={p} AND accepted_at IS NULL", (token_hash,)).fetchone()
        if invitation is None or invitation["expires_at"] <= now or invitation["email"] != normalize_email(email):
            raise ValueError("invalid invitation")
        try:
            connection.execute(f"INSERT INTO agency_memberships(user_id,agency_id,role,created_at) VALUES ({p},{p},{p},{p})", (user_id, invitation["agency_id"], invitation["role"], now))
        except Exception as exc:
            if _integrity_error(exc):
                raise ValueError("membership already exists") from exc
            raise
        connection.execute(f"UPDATE agency_invitations SET accepted_at={p} WHERE token_hash={p}", (now, token_hash))
        return _principal_row(connection, user_id, invitation["agency_id"])


def create_resume_session(db_path: str, session_id: str, directory: str, user_id: Optional[str], agency_id: Optional[str], expires_at: float) -> None:
    with _Connection(db_path) as connection:
        p = connection.placeholder
        connection.execute(f"INSERT INTO resume_sessions(session_id,owner_user_id,agency_id,directory,created_at,expires_at) VALUES ({p},{p},{p},{p},{p},{p})", (session_id, user_id, agency_id, directory, time.time(), expires_at))


def add_resume_file(db_path: str, session_id: str, filename: str) -> None:
    with _Connection(db_path) as connection:
        p = connection.placeholder
        connection.execute(f"INSERT INTO resume_files(session_id,filename,created_at) VALUES ({p},{p},{p}) ON CONFLICT(session_id,filename) DO NOTHING", (session_id, filename, time.time()))


def get_resume_session(db_path: str, session_id: str) -> Optional[dict[str, Any]]:
    with _Connection(db_path) as connection:
        p = connection.placeholder
        row = connection.execute(f"SELECT * FROM resume_sessions WHERE session_id={p}", (session_id,)).fetchone()
        return dict(row) if row else None


def end_resume_session(db_path: str, session_id: str) -> None:
    with _Connection(db_path) as connection:
        p = connection.placeholder
        connection.execute(f"UPDATE resume_sessions SET ended_at={p} WHERE session_id={p}", (time.time(), session_id))
