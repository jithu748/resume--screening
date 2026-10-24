import csv
import io
import os
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

from data.src import webapp


PDF = b"%PDF-1.4\nsynthetic test resume\n"


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "AUTH_DB_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setattr(webapp, "AUTH_MIGRATION_PATH", os.path.join(webapp.PROJECT_ROOT, "migrations", "001_auth_and_tenant.sql"))
    monkeypatch.setattr(webapp, "AUTH_REQUIRED", True)
    webapp._session_storage.clear()
    webapp._login_failures.clear()
    return TestClient(webapp.app)


def register(client, email, agency_name):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct horse battery staple", "agency_name": agency_name},
    )
    assert response.status_code == 200, response.text
    return response.json()


def csrf_headers(client):
    return {"X-CSRF-Token": client.cookies[webapp.CSRF_COOKIE_NAME]}


def upload(client, filename="resume.pdf"):
    response = client.post(
        "/api/upload",
        files={"files": (filename, PDF, "application/pdf")},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_registration_hashes_password_and_creates_safe_owner(auth_client, tmp_path):
    details = register(auth_client, "owner@example.test", "Agency One")
    assert details["role"] == "owner"
    assert "agency_id" in details
    with sqlite3.connect(tmp_path / "auth.sqlite3") as connection:
        row = connection.execute("SELECT password_hash FROM users").fetchone()
    assert row is not None
    assert row[0].startswith("scrypt$")
    assert "correct horse battery staple" not in row[0]

    rejected = auth_client.post(
        "/api/auth/register",
        json={"email": "join@example.test", "password": "correct horse battery staple", "agency_id": details["agency_id"], "role": "admin", "agency_name": "Nope"},
    )
    assert rejected.status_code == 400


def test_login_logout_and_csrf(auth_client):
    register(auth_client, "login@example.test", "Login Agency")
    auth_client.post("/api/auth/logout", headers=csrf_headers(auth_client))
    assert auth_client.get("/api/auth/me").status_code == 401

    logged_in = auth_client.post(
        "/api/auth/login",
        json={"email": "login@example.test", "password": "correct horse battery staple"},
    )
    assert logged_in.status_code == 200
    auth_cookie_headers = [value for value in logged_in.headers.get_list("set-cookie") if value.startswith(f"{webapp.AUTH_COOKIE_NAME}=")]
    csrf_cookie_headers = [value for value in logged_in.headers.get_list("set-cookie") if value.startswith(f"{webapp.CSRF_COOKIE_NAME}=")]
    assert auth_cookie_headers and "HttpOnly" in auth_cookie_headers[0] and "SameSite=lax" in auth_cookie_headers[0]
    assert csrf_cookie_headers and "HttpOnly" not in csrf_cookie_headers[0] and "SameSite=lax" in csrf_cookie_headers[0]
    assert auth_client.get("/api/auth/me").status_code == 200
    missing_csrf = auth_client.post("/api/upload", files={"files": ("resume.pdf", PDF, "application/pdf")})
    assert missing_csrf.status_code == 403

    logout = auth_client.post("/api/auth/logout", headers=csrf_headers(auth_client))
    assert logout.status_code == 200
    assert auth_client.get("/api/auth/me").status_code == 401


def test_unauthenticated_access_is_denied_in_required_mode(auth_client):
    anonymous = TestClient(webapp.app)
    assert anonymous.get("/api/auth/me").status_code == 401
    assert anonymous.get("/api/session_status", params={"session_id": "unknown"}).status_code == 401
    assert anonymous.post("/api/upload", files={"files": ("resume.pdf", PDF, "application/pdf")}).status_code == 401


def test_anonymous_compatibility_mode_remains_explicit(auth_client, monkeypatch):
    monkeypatch.setattr(webapp, "AUTH_REQUIRED", False)
    anonymous = TestClient(webapp.app)
    response = anonymous.post("/api/upload", files={"files": ("resume.pdf", PDF, "application/pdf")})
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    assert anonymous.get("/api/session_status", params={"session_id": session_id}).status_code == 200
    anonymous.delete("/api/session", params={"session_id": session_id})


def test_user_and_agency_isolation_across_sensitive_routes(auth_client):
    owner_a = register(auth_client, "a@example.test", "Agency A")
    session_a = upload(auth_client, "a.pdf")["session_id"]

    client_b = TestClient(webapp.app)
    register(client_b, "b@example.test", "Agency B")
    session_b = upload(client_b, "b.pdf")["session_id"]

    assert auth_client.get("/api/session_status", params={"session_id": session_b}).status_code == 403
    assert auth_client.get(f"/view/{session_b}/b.pdf").status_code == 403
    assert auth_client.post(
        "/api/score", json={"job_title": "Engineer", "skills": "Python", "session_id": session_b}, headers=csrf_headers(auth_client)
    ).status_code == 403
    assert auth_client.get(
        "/api/download_results", params={"job_title": "Engineer", "skills": "Python", "session_id": session_b}
    ).status_code == 403
    assert auth_client.delete("/api/session", params={"session_id": session_b}, headers=csrf_headers(auth_client)).status_code == 403
    assert auth_client.get("/api/session_status", params={"session_id": session_a}).status_code == 200
    assert owner_a["role"] == "owner"


def test_invitation_membership_and_role_boundary(auth_client):
    owner = register(auth_client, "owner2@example.test", "Agency Shared")
    invite = auth_client.post(
        f"/api/agencies/{owner['agency_id']}/invitations",
        json={"email": "recruiter@example.test", "role": "recruiter"},
        headers=csrf_headers(auth_client),
    )
    assert invite.status_code == 200
    token = invite.json()["invitation_token"]

    recruiter = TestClient(webapp.app)
    register(recruiter, "recruiter@example.test", "Recruiter Personal Agency")
    accepted = recruiter.post(
        "/api/auth/accept-invitation", json={"invitation_token": token}, headers=csrf_headers(recruiter)
    )
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "recruiter"

    forbidden = recruiter.post(
        f"/api/agencies/{owner['agency_id']}/invitations",
        json={"email": "admin@example.test", "role": "admin"},
        headers=csrf_headers(recruiter),
    )
    assert forbidden.status_code == 403


def test_expired_auth_session_and_login_rate_limit(auth_client, tmp_path):
    register(auth_client, "expire@example.test", "Expiry Agency")
    token = auth_client.cookies[webapp.AUTH_COOKIE_NAME]
    with sqlite3.connect(tmp_path / "auth.sqlite3") as connection:
        connection.execute("UPDATE auth_sessions SET idle_expires_at = 0 WHERE token_hash = ?", (__import__("hashlib").sha256(token.encode()).hexdigest(),))
    assert auth_client.get("/api/auth/me").status_code == 401

    for _ in range(5):
        response = auth_client.post("/api/auth/login", json={"email": "missing@example.test", "password": "wrong password"})
        assert response.status_code == 401
    assert auth_client.post("/api/auth/login", json={"email": "missing@example.test", "password": "wrong password"}).status_code == 429


def test_csv_export_does_not_include_resume_text(auth_client, monkeypatch):
    register(auth_client, "csv@example.test", "CSV Agency")
    session_id = upload(auth_client)["session_id"]
    monkeypatch.setattr(webapp, "load_resumes", lambda resume_folder: {"resume.pdf": "PRIVATE CANDIDATE TEXT"})
    monkeypatch.setattr(webapp, "clean_text", lambda value: value)
    monkeypatch.setattr(webapp, "_compute_job_title_relevance", lambda title, resumes: {name: 1.0 for name in resumes})
    monkeypatch.setattr(webapp, "get_tfidf_vectors", lambda description, resumes: [1.0])
    monkeypatch.setattr(webapp, "compute_cosine", lambda vectors: [1.0])
    monkeypatch.setattr(webapp, "score_resume", lambda text, skills, similarity: {"score": 1.0, "matched_skills": ["python"], "missing_skills": []})
    response = auth_client.get(
        "/api/download_results",
        params={"job_title": "Engineer", "skills": "Python", "session_id": session_id},
    )
    assert response.status_code == 200
    assert "PRIVATE CANDIDATE TEXT" not in response.text
    assert next(csv.reader(io.StringIO(response.text))) == ["rank", "file", "score", "matched_skills", "missing_skills"]


def test_production_configuration_fails_closed():
    with pytest.raises(RuntimeError):
        webapp.validate_production_configuration("production", False, "", [], None)
    with pytest.raises(RuntimeError):
        webapp.validate_production_configuration("production", True, "sqlite:///local.db", ["https://app.example"], "true")
    with pytest.raises(RuntimeError):
        webapp.validate_production_configuration(
            "production", True, "postgresql://db", ["https://app.example"], "true", postgres_adapter_ready=False
        )
    webapp.validate_production_configuration(
        "production", True, "postgresql://db", ["https://app.example"], "true", postgres_adapter_ready=True
    )


def test_local_demo_configuration_requires_development_and_loopback_origins():
    webapp.validate_local_demo_configuration(
        "development", True, False, ["http://127.0.0.1:8081", "http://localhost:8081"]
    )
    with pytest.raises(RuntimeError):
        webapp.validate_local_demo_configuration(
            "production", True, False, ["http://127.0.0.1:8081"]
        )
    with pytest.raises(RuntimeError):
        webapp.validate_local_demo_configuration(
            "development", True, True, ["http://127.0.0.1:8081"]
        )
    with pytest.raises(RuntimeError):
        webapp.validate_local_demo_configuration(
            "development", True, False, ["https://public.example"]
        )


def test_local_demo_loopback_client_check():
    assert webapp._is_loopback_client("127.0.0.1")
    assert webapp._is_loopback_client("::1")
    assert webapp._is_loopback_client("localhost")
    assert not webapp._is_loopback_client("192.0.2.10")
    assert not webapp._is_loopback_client(None)


def test_local_demo_template_hides_authentication_controls():
    rendered = webapp.templates.get_template("index.html").render(
        request=None,
        local_demo_mode=True,
    )
    assert 'id="auth-card"' not in rendered

    rendered_authenticated_mode = webapp.templates.get_template("index.html").render(
        request=None,
        local_demo_mode=False,
    )
    assert 'id="auth-card"' in rendered_authenticated_mode


def test_cors_allows_only_configured_origins(auth_client):
    allowed = auth_client.options("/api/auth/me", headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:8000"
    denied = auth_client.options("/api/auth/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in denied.headers
