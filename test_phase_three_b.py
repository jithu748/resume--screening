import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import pytest

from data.src import auth_store


def _safe_postgres_test_target(raw_target):
    """Accept only a loopback PostgreSQL URL for a clearly test-scoped database."""
    parsed = urlparse(raw_target)
    host = (parsed.hostname or "").lower()
    database = parsed.path.lstrip("/").lower()
    username = (parsed.username or "").lower()
    password = (parsed.password or "").lower()
    placeholders = {
        "user", "username", "your_user", "your_username", "your_actual_user", "<username>",
        "password", "your_password", "your_actual_password", "<password>", "changeme", "change_me",
    }
    safe_host = host in {"localhost", "127.0.0.1", "::1"}
    safe_name = (
        database.startswith("test_")
        or database.startswith("test-")
        or database.endswith("_test")
        or database.endswith("-test")
    )
    credentials_are_placeholders = username in placeholders or password in placeholders
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not safe_host
        or not safe_name
        or not username
        or credentials_are_placeholders
    ):
        raise RuntimeError("TEST_POSTGRES_URL must target a loopback PostgreSQL database with a test-scoped name")
    return raw_target


def test_postgres_target_guard_only_allows_local_test_database():
    assert _safe_postgres_test_target("postgresql://resume_test_user@localhost/resume_screening_phase3c_test").endswith("phase3c_test")
    with pytest.raises(RuntimeError):
        _safe_postgres_test_target("postgresql://user@db.example/resume_screening")
    with pytest.raises(RuntimeError):
        _safe_postgres_test_target("postgresql://user@localhost/resume_screening")
    with pytest.raises(RuntimeError):
        _safe_postgres_test_target("postgresql://YOUR_ACTUAL_USER:YOUR_ACTUAL_PASSWORD@localhost/resume_screening_phase3c_test")


def test_sqlite_schema_is_repeatable_and_uses_portable_conflicts(tmp_path):
    database = str(tmp_path / "auth.sqlite3")
    auth_store.ensure_schema(database)
    auth_store.ensure_schema(database)
    principal = auth_store.create_agency_owner(database, "Synthetic Agency", "unit@example.test", auth_store.hash_password("a strong synthetic password"))
    token, csrf = auth_store.create_auth_session(database, principal["user_id"], principal["agency_id"], 60, 120)
    assert csrf
    assert auth_store.get_auth_session(database, token, 60)["agency_id"] == principal["agency_id"]
    auth_store.create_resume_session(database, "synthetic-session", str(tmp_path), principal["user_id"], principal["agency_id"], 9999999999)
    auth_store.add_resume_file(database, "synthetic-session", "resume.pdf")
    auth_store.add_resume_file(database, "synthetic-session", "resume.pdf")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM resume_files").fetchone()[0] == 1


def test_frontend_auth_contract_is_present():
    source = Path("data/web/static/app.js").read_text(encoding="utf-8")
    assert "credentials: 'include'" in source
    assert "X-CSRF-Token" in source
    assert "/api/auth/login" in source
    assert "/api/auth/register" in source
    assert "/api/auth/logout" in source
    assert "response.status === 401" in source
    assert "response.status === 403" in source


@pytest.mark.postgres
def test_postgres_adapter_against_real_service():
    """Opt-in integration test; requires a dedicated disposable TEST_POSTGRES_URL."""
    target = os.getenv("TEST_POSTGRES_URL")
    if not target:
        pytest.skip("TEST_POSTGRES_URL is not configured; no real PostgreSQL service was supplied")
    if not auth_store.postgres_available():
        pytest.skip("psycopg is not installed in the active test environment")
    target = _safe_postgres_test_target(target)
    # This test deliberately uses the caller-provided dedicated test database.
    auth_store.ensure_schema(target)
    principal = auth_store.create_agency_owner(target, "Integration Synthetic Agency", f"integration-{os.getpid()}@example.test", auth_store.hash_password("synthetic integration password"))
    token, _ = auth_store.create_auth_session(target, principal["user_id"], principal["agency_id"], 60, 120)
    assert auth_store.get_auth_session(target, token, 60)["user_id"] == principal["user_id"]
