import os
import sys
import hashlib
import hmac
from fastapi import Depends, FastAPI, Request, Response, UploadFile, File, HTTPException, Query, Form
import io
import zipfile
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import tempfile
import shutil
import uuid
from contextlib import contextmanager
import threading
import time
import mimetypes
import stat
from pathlib import PurePosixPath


# ensure local src folder is on sys.path so imports like `import extract_text` work
src_dir = os.path.dirname(__file__)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Import existing project functions
from extract_text import load_resumes
from preprocess import clean_text
from vectorizer import get_tfidf_vectors
from similarity import compute_cosine
from scorer import score_resume
import auth_store

app = FastAPI(title="Resume Screening Web UI")

# --- Paths & static mounts ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
AUTH_DB_PATH = os.getenv("AUTH_DB_PATH", os.path.join(PROJECT_ROOT, "auth.sqlite3"))


def _auth_database_target() -> str:
    return os.getenv("DATABASE_URL") if APP_ENV == "production" else AUTH_DB_PATH
AUTH_MIGRATION_PATH = os.getenv(
    "AUTH_MIGRATION_PATH", os.path.join(PROJECT_ROOT, "migrations", "001_auth_and_tenant.sql")
)
AUTH_COOKIE_NAME = "resume_auth"
CSRF_COOKIE_NAME = "resume_csrf"
AUTH_IDLE_SECONDS = int(os.getenv("AUTH_IDLE_SECONDS", 8 * 60 * 60))
AUTH_ABSOLUTE_SECONDS = int(os.getenv("AUTH_ABSOLUTE_SECONDS", 24 * 60 * 60))
INVITATION_SECONDS = int(os.getenv("INVITATION_SECONDS", 7 * 24 * 60 * 60))


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if value.strip().lower() in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean configuration: {name}")


AUTH_REQUIRED = _env_bool("AUTH_REQUIRED", APP_ENV == "production")
PRODUCTION_POSTGRES_ADAPTER_READY = auth_store.postgres_available()
_configured_origins = [origin.strip().rstrip("/") for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
if "*" in _configured_origins:
    raise RuntimeError("Wildcard CORS origins are not allowed with credentials")
CORS_ALLOWED_ORIGINS = _configured_origins or ["http://localhost:8000", "http://127.0.0.1:8000"]


def validate_production_configuration(
    app_env: str, auth_required: bool, database_url: str, allowed_origins: list[str], explicit_auth_required: Optional[str],
    postgres_adapter_ready: bool = PRODUCTION_POSTGRES_ADAPTER_READY,
) -> None:
    if app_env == "production":
        if explicit_auth_required != "true" or not auth_required:
            raise RuntimeError("Production requires AUTH_REQUIRED=true")
        if not database_url.lower().startswith(("postgresql://", "postgres://")):
            raise RuntimeError("Production requires a PostgreSQL DATABASE_URL")
        if not allowed_origins:
            raise RuntimeError("Production requires CORS_ALLOWED_ORIGINS")
        if not postgres_adapter_ready:
            raise RuntimeError("Production PostgreSQL authentication adapter is not available")


validate_production_configuration(
    APP_ENV, AUTH_REQUIRED, os.getenv("DATABASE_URL", ""), _configured_origins, os.getenv("AUTH_REQUIRED")
)


def _ensure_auth_schema() -> None:
    if APP_ENV == "production" and not PRODUCTION_POSTGRES_ADAPTER_READY:
        raise RuntimeError("Production PostgreSQL authentication adapter is not available")
    auth_store.ensure_schema(_auth_database_target(), AUTH_MIGRATION_PATH)


def _principal_from_request(request: Request) -> Optional[dict]:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return None
    try:
        _ensure_auth_schema()
        return auth_store.get_auth_session(_auth_database_target(), token, AUTH_IDLE_SECONDS)
    except (OSError, ValueError, RuntimeError):
        return None


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in CORS_ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Origin is not allowed")


def _check_csrf(request: Request, principal: dict) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    _check_origin(request)
    csrf_header = request.headers.get("x-csrf-token")
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    if not csrf_header or not csrf_cookie or not hmac.compare_digest(csrf_header, csrf_cookie) or not hmac.compare_digest(
        hashlib.sha256(csrf_header.encode()).hexdigest(), principal["csrf_hash"]
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def require_sensitive_access(request: Request) -> Optional[dict]:
    principal = _principal_from_request(request)
    if principal is None and AUTH_REQUIRED:
        raise HTTPException(status_code=401, detail="Authentication required")
    if principal is not None:
        _check_csrf(request, principal)
    elif request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        _check_origin(request)
    return principal

# static files (css/js) for the web UI
STATIC_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "web", "static"))
TEMPLATES_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "web", "templates"))

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ======================================================================
# SESSION-ISOLATED STORAGE WITH TTL
# Each user gets a session-specific temp directory.
# Sessions expire automatically after a configured TTL.
# ======================================================================

# TTL in seconds (default 10 minutes as requested)
SESSION_TTL_SECONDS = 10 * 60

# Upload limits are intentionally conservative and can be overridden by the
# process environment without changing the application code.
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("RESUME_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
MAX_UPLOAD_TOTAL_BYTES = int(os.getenv("RESUME_MAX_UPLOAD_TOTAL_BYTES", 100 * 1024 * 1024))
MAX_UPLOAD_FILES = int(os.getenv("RESUME_MAX_UPLOAD_FILES", 50))
ZIP_MAX_ARCHIVE_SIZE_BYTES = int(os.getenv("RESUME_MAX_ZIP_BYTES", 50 * 1024 * 1024))
ZIP_MAX_ENTRIES = int(os.getenv("RESUME_MAX_ZIP_ENTRIES", 100))
ZIP_MAX_FILE_SIZE_BYTES = int(os.getenv("RESUME_MAX_ZIP_FILE_BYTES", 10 * 1024 * 1024))
ZIP_MAX_TOTAL_EXTRACTED_BYTES = int(os.getenv("RESUME_MAX_ZIP_TOTAL_BYTES", 100 * 1024 * 1024))
ZIP_MAX_COMPRESSION_RATIO = float(os.getenv("RESUME_MAX_ZIP_COMPRESSION_RATIO", 100.0))
UPLOAD_CHUNK_SIZE = 64 * 1024

# In-memory store mirrors the local temporary directory; authenticated ownership
# is also persisted in the migration-backed store.
_session_storage: dict[str, dict] = {}
_session_lock = threading.Lock()

def _now_ts() -> float:
    return time.time()

def _touch_session(session_id: str) -> None:
    with _session_lock:
        s = _session_storage.get(session_id)
        if s:
            s['expires_at'] = _now_ts() + SESSION_TTL_SECONDS

def _create_session(owner_user_id: Optional[str] = None, agency_id: Optional[str] = None) -> tuple[str, str]:
    """Create a new server-generated session without overwriting an existing one."""
    while True:
        sid = str(uuid.uuid4())
        temp_dir = tempfile.mkdtemp(prefix="resume_session_")

        with _session_lock:
            if sid not in _session_storage:
                _session_storage[sid] = {
                    'dir': temp_dir,
                    'files': [],
                    'owner_user_id': owner_user_id,
                    'agency_id': agency_id,
                    'expires_at': _now_ts() + SESSION_TTL_SECONDS,
                }
                if owner_user_id and agency_id:
                    try:
                        _ensure_auth_schema()
                        auth_store.create_resume_session(
                            _auth_database_target(), sid, temp_dir, owner_user_id, agency_id, _now_ts() + SESSION_TTL_SECONDS
                        )
                    except Exception:
                        _session_storage.pop(sid, None)
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        raise
                return sid, temp_dir

        # Extremely unlikely UUID collision: discard the unused directory.
        shutil.rmtree(temp_dir, ignore_errors=True)

def _is_session_valid(session_id: str) -> bool:
    with _session_lock:
        s = _session_storage.get(session_id)
        return bool(s and s['expires_at'] > _now_ts() and os.path.isdir(s['dir']))

def _get_session_dir(session_id: str) -> Optional[str]:
    with _session_lock:
        s = _session_storage.get(session_id)
        return s['dir'] if s else None

def _add_session_file(session_id: str, filename: str) -> None:
    with _session_lock:
        s = _session_storage.get(session_id)
        if s:
            s['files'].append(filename)
            s['expires_at'] = _now_ts() + SESSION_TTL_SECONDS
            if s.get('owner_user_id'):
                _ensure_auth_schema()
                auth_store.add_resume_file(_auth_database_target(), session_id, filename)

def _get_session_info(session_id: str) -> Optional[dict]:
    with _session_lock:
        s = _session_storage.get(session_id)
        if not s:
            return None
        return {
            'dir': s['dir'],
            'files': list(s['files']),
            'owner_user_id': s.get('owner_user_id'),
            'agency_id': s.get('agency_id'),
            'expires_at': s['expires_at'],
            'expires_in': max(0, int(s['expires_at'] - _now_ts())),
        }


def _discard_session(session_id: str, temp_dir: str) -> None:
    """Remove a temporary session and its files after a failed request."""
    with _session_lock:
        stored = _session_storage.get(session_id)
        authenticated_owner = bool(stored and stored.get("owner_user_id"))
    shutil.rmtree(temp_dir, ignore_errors=True)
    with _session_lock:
        _session_storage.pop(session_id, None)
    if authenticated_owner:
        try:
            _ensure_auth_schema()
            auth_store.end_resume_session(_auth_database_target(), session_id)
        except (OSError, RuntimeError):
            pass


def _authorize_session(session_id: str, principal: Optional[dict], action: str) -> dict:
    """Authorize a session before accessing its files or results."""
    info = _get_session_info(session_id)
    if not info or not _is_session_valid(session_id):
        raise HTTPException(status_code=404, detail="Session expired or invalid")
    if not isinstance(principal, dict):
        if info.get("owner_user_id") or AUTH_REQUIRED:
            raise HTTPException(status_code=403, detail="Access denied")
        return info
    if info.get("agency_id") != principal.get("agency_id"):
        raise HTTPException(status_code=403, detail="Access denied")
    role = principal.get("role")
    same_user = info.get("owner_user_id") == principal.get("user_id")
    if action == "read" and (same_user or role in {"owner", "admin", "viewer"}):
        return info
    if action in {"write", "delete"} and (same_user and role in {"owner", "admin", "recruiter"} or role in {"owner", "admin"}):
        return info
    raise HTTPException(status_code=403, detail="Access denied")

def _cleanup_expired_sessions_loop():
    while True:
        time.sleep(60)
        now = _now_ts()
        expired: list[str] = []
        with _session_lock:
            for sid, s in list(_session_storage.items()):
                if s['expires_at'] <= now:
                    expired.append(sid)
        for sid in expired:
            dir_path = _get_session_dir(sid)
            with _session_lock:
                stored = _session_storage.get(sid)
                authenticated_owner = bool(stored and stored.get("owner_user_id"))
            try:
                if dir_path:
                    shutil.rmtree(dir_path, ignore_errors=True)
            except Exception:
                pass
            with _session_lock:
                _session_storage.pop(sid, None)
            if authenticated_owner:
                try:
                    _ensure_auth_schema()
                    auth_store.end_resume_session(_auth_database_target(), sid)
                except (OSError, RuntimeError):
                    pass
            print(f"[CLEANUP] Expired session {sid[:8]}... cleaned up")

@app.on_event("startup")
def _start_cleanup_thread():
    t = threading.Thread(target=_cleanup_expired_sessions_loop, daemon=True)
    t.start()


@app.delete("/api/session")
def end_session(session_id: str = Query(...), principal: Optional[dict] = Depends(require_sensitive_access)):
    """Manually end a session: delete temp dir and remove from memory."""
    _authorize_session(session_id, principal, "delete")
    dir_path = _get_session_dir(session_id)
    if not dir_path:
        return JSONResponse({"message": "Session already ended or expired"}, status_code=200)
    try:
        shutil.rmtree(dir_path, ignore_errors=True)
    except Exception:
        pass
    with _session_lock:
        _session_storage.pop(session_id, None)
    if isinstance(principal, dict):
        try:
            _ensure_auth_schema()
            auth_store.end_resume_session(_auth_database_target(), session_id)
        except (OSError, RuntimeError):
            pass
    return {"message": "Session ended and files removed", "session_id": session_id}


@app.post("/api/end_session")
async def end_session_post(request: Request):
    """Manually end a session via POST. Accepts JSON, form, or query param.
    Body (preferred JSON): {"session_id": "..."}
    """
    principal = require_sensitive_access(request)
    session_id = None
    # Try JSON
    try:
        data = await request.json()
        if isinstance(data, dict):
            session_id = data.get("session_id")
    except Exception:
        session_id = None
    # Try form data
    if not session_id:
        try:
            form = await request.form()
            session_id = form.get("session_id")
        except Exception:
            pass
    # Try query string
    if not session_id:
        session_id = request.query_params.get("session_id")

    if not session_id:
        return JSONResponse({"error": "session_id is required"}, status_code=400)

    _authorize_session(session_id, principal, "delete")
    dir_path = _get_session_dir(session_id)
    if not dir_path:
        return {"message": "Session already ended or expired", "session_id": session_id}

    try:
        shutil.rmtree(dir_path, ignore_errors=True)
    except Exception:
        pass
    with _session_lock:
        _session_storage.pop(session_id, None)
    if isinstance(principal, dict):
        try:
            _ensure_auth_schema()
            auth_store.end_resume_session(_auth_database_target(), session_id)
        except (OSError, RuntimeError):
            pass
    return {"message": "Session ended and files removed", "session_id": session_id}


@contextmanager
def get_session_dir(session_id: str = None):
    """
    Context manager that creates and cleans up a temporary directory for a session.
    Usage:
        with get_session_dir(session_id) as temp_dir:
            # use temp_dir for uploads
            pass
        # temp_dir is automatically deleted after exiting
    """
    if session_id is None:
        session_id = str(uuid.uuid4())
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp(prefix=f"resume_session_{session_id}_")
    
    try:
        yield temp_dir
    finally:
        # Clean up: remove temp directory and all contents
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def _safe_resume_filename(raw_filename: Optional[str]) -> tuple[str, str]:
    """Return a safe filename and its supported lower-case extension."""
    if not raw_filename or "\x00" in raw_filename:
        raise HTTPException(status_code=400, detail="Filename is required and must be safe")
    if os.path.basename(raw_filename) != raw_filename or "/" in raw_filename or "\\" in raw_filename:
        raise HTTPException(status_code=400, detail="Path separators are not allowed in filenames")
    filename = raw_filename.strip()
    if not filename or filename in {".", ".."} or len(filename) > 255:
        raise HTTPException(status_code=400, detail="Filename is invalid")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Only PDF and DOCX resumes are supported")
    return filename, ext


def _unique_destination(filename: str, temp_dir: str, used_names: set[str]) -> tuple[str, str]:
    """Choose a non-overwriting filename for ordinary multipart uploads."""
    base, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1
    while candidate in used_names or os.path.exists(os.path.join(temp_dir, candidate)):
        candidate = f"{base}_{counter}{ext}"
        counter += 1
    return candidate, os.path.join(temp_dir, candidate)


async def _write_upload_bounded(upload: UploadFile, destination: str, maximum: int) -> int:
    """Stream an UploadFile to disk and reject it once the limit is exceeded."""
    total = 0
    with open(destination, "wb") as output:
        while True:
            chunk = await upload.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise HTTPException(status_code=413, detail="Uploaded file exceeds the configured size limit")
            output.write(chunk)
    return total


def _validate_resume_content(path: str, extension: str) -> None:
    """Validate a resume's basic file signature and structure."""
    if os.path.getsize(path) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if extension == ".pdf":
        with open(path, "rb") as source:
            if source.read(5) != b"%PDF-":
                raise HTTPException(status_code=400, detail="Uploaded PDF has an invalid file signature")
        return

    if not zipfile.is_zipfile(path):
        raise HTTPException(status_code=400, detail="Uploaded DOCX is not a valid Office archive")
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise HTTPException(status_code=400, detail="Uploaded DOCX has an invalid document structure")
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Uploaded DOCX is malformed") from exc


async def _save_validated_resume(upload: UploadFile, temp_dir: str, used_names: set[str]) -> str:
    filename, extension = _safe_resume_filename(upload.filename)
    final_name, destination = _unique_destination(filename, temp_dir, used_names)
    try:
        await _write_upload_bounded(upload, destination, MAX_UPLOAD_SIZE_BYTES)
        _validate_resume_content(destination, extension)
    except Exception:
        try:
            os.remove(destination)
        except FileNotFoundError:
            pass
        raise
    used_names.add(final_name)
    if _directory_file_size(temp_dir) > MAX_UPLOAD_TOTAL_BYTES:
        try:
            os.remove(os.path.join(temp_dir, final_name))
        except FileNotFoundError:
            pass
        used_names.discard(final_name)
        raise HTTPException(status_code=413, detail="Upload exceeds the configured total size limit")
    return final_name


def _directory_file_size(temp_dir: str) -> int:
    return sum(
        os.path.getsize(os.path.join(temp_dir, name))
        for name in os.listdir(temp_dir)
        if os.path.isfile(os.path.join(temp_dir, name)) and not name.startswith(".resume_upload")
    )


def _validate_archive_member(info: zipfile.ZipInfo) -> Optional[str]:
    """Validate one ZIP member and return its safe output basename."""
    name = info.filename
    if not name or "\x00" in name or len(name) > 255:
        raise HTTPException(status_code=400, detail="ZIP contains an unsafe filename")
    if "\\" in name:
        raise HTTPException(status_code=400, detail="ZIP contains an unsafe filename")
    path = PurePosixPath(name)
    if path.is_absolute() or ":" in path.parts[0] or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(status_code=400, detail="ZIP contains a traversal or absolute path")
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        raise HTTPException(status_code=400, detail="ZIP contains a symbolic link")
    if stat.S_ISDIR(mode) or name.endswith("/"):
        return None
    filename, extension = _safe_resume_filename(path.name)
    if info.flag_bits & 0x1:
        raise HTTPException(status_code=400, detail="Encrypted ZIP entries are not supported")
    if info.file_size > ZIP_MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="ZIP entry exceeds the configured file size limit")
    if info.compress_size == 0 and info.file_size > 0:
        raise HTTPException(status_code=400, detail="ZIP entry has an invalid compression ratio")
    if info.compress_size and info.file_size / info.compress_size > ZIP_MAX_COMPRESSION_RATIO:
        raise HTTPException(status_code=413, detail="ZIP entry exceeds the configured compression ratio")
    return filename


def _extract_zip_safely(archive_path: str, temp_dir: str, used_names: set[str]) -> list[str]:
    """Validate and stream-extract a bounded ZIP archive into temp_dir."""
    saved: list[str] = []
    total_size = _directory_file_size(temp_dir)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > ZIP_MAX_ENTRIES:
                raise HTTPException(status_code=413, detail="ZIP contains too many entries")
            members: list[tuple[zipfile.ZipInfo, str]] = []
            for info in infos:
                filename = _validate_archive_member(info)
                if filename is None:
                    continue
                if filename in used_names or filename in {item[1] for item in members}:
                    raise HTTPException(status_code=409, detail="ZIP contains duplicate filenames")
                total_size += info.file_size
                if total_size > ZIP_MAX_TOTAL_EXTRACTED_BYTES or total_size > MAX_UPLOAD_TOTAL_BYTES:
                    raise HTTPException(status_code=413, detail="ZIP exceeds the total extracted size limit")
                members.append((info, filename))
            if len(used_names) + len(members) > MAX_UPLOAD_FILES:
                raise HTTPException(status_code=413, detail="Upload contains too many resumes")

            for info, filename in members:
                destination = os.path.join(temp_dir, filename)
                written = 0
                with archive.open(info, "r") as source, open(destination, "wb") as output:
                    while True:
                        chunk = source.read(UPLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > ZIP_MAX_FILE_SIZE_BYTES:
                            raise HTTPException(status_code=413, detail="ZIP entry exceeds the configured file size limit")
                        output.write(chunk)
                _validate_resume_content(destination, os.path.splitext(filename)[1].lower())
                used_names.add(filename)
                saved.append(filename)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid or malformed ZIP archive") from exc
    return saved


async def _save_and_extract_zip(upload: UploadFile, temp_dir: str, used_names: set[str]) -> list[str]:
    """Bound and extract an uploaded ZIP without keeping it in memory."""
    archive_path = os.path.join(temp_dir, ".resume_upload.zip")
    try:
        await _write_upload_bounded(upload, archive_path, ZIP_MAX_ARCHIVE_SIZE_BYTES)
        return _extract_zip_safely(archive_path, temp_dir, used_names)
    finally:
        try:
            os.remove(archive_path)
        except FileNotFoundError:
            pass


# NOTE: Removed the global UPLOADS_DIR mount for security.
# Files are now processed in temporary session-isolated directories.

# resume uploads directory (serve as /uploads/<filename>)
# UPLOADS_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "resume_uploads"))
# os.makedirs(UPLOADS_DIR, exist_ok=True)
# app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Allow local testing from browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


_login_failures: dict[str, list[float]] = {}
_login_failure_lock = threading.Lock()
_DUMMY_PASSWORD_HASH = auth_store.hash_password("resume-screening-invalid-login-dummy")


def _login_allowed(keys: list[str]) -> bool:
    now = _now_ts()
    with _login_failure_lock:
        for key in keys:
            attempts = [timestamp for timestamp in _login_failures.get(key, []) if timestamp > now - 900]
            _login_failures[key] = attempts
            if len(attempts) >= 5:
                return False
    return True


def _record_login_failure(keys: list[str]) -> None:
    now = _now_ts()
    with _login_failure_lock:
        for key in keys:
            _login_failures.setdefault(key, []).append(now)


def _set_auth_cookies(response: Response, token: str, csrf_token: str) -> None:
    secure = APP_ENV == "production"
    response.set_cookie(
        AUTH_COOKIE_NAME, token, max_age=AUTH_ABSOLUTE_SECONDS, httponly=True,
        secure=secure, samesite="lax", path="/"
    )
    response.set_cookie(
        CSRF_COOKIE_NAME, csrf_token, max_age=AUTH_ABSOLUTE_SECONDS, httponly=False,
        secure=secure, samesite="lax", path="/"
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@app.post("/api/auth/register")
async def register(request: Request, response: Response):
    _check_origin(request)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid registration request"}, status_code=400)
    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", ""))
    agency_name = str(payload.get("agency_name", "")).strip()
    if payload.get("agency_id") or payload.get("role") or len(email) < 3 or len(password) < 12 or len(agency_name) < 2:
        return JSONResponse({"error": "Unable to create account"}, status_code=400)
    try:
        _ensure_auth_schema()
        principal = auth_store.create_agency_owner(
            _auth_database_target(), agency_name, email, auth_store.hash_password(password)
        )
        token, csrf_token = auth_store.create_auth_session(
            _auth_database_target(), principal["user_id"], principal["agency_id"], AUTH_IDLE_SECONDS, AUTH_ABSOLUTE_SECONDS
        )
    except (ValueError, OSError, RuntimeError):
        return JSONResponse({"error": "Unable to create account"}, status_code=400)
    _set_auth_cookies(response, token, csrf_token)
    return {"user": principal["email"], "agency_id": principal["agency_id"], "role": principal["role"]}


@app.post("/api/auth/login")
async def login(request: Request, response: Response):
    _check_origin(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", ""))
    client_ip = request.client.host if request.client else "unknown"
    normalized = auth_store.normalize_email(email)
    keys = [f"ip:{client_ip}", f"email:{normalized}"]
    if not _login_allowed(keys):
        return JSONResponse({"error": "Login temporarily unavailable"}, status_code=429)
    try:
        _ensure_auth_schema()
        user = auth_store.get_user_for_login(_auth_database_target(), email)
        password_ok = auth_store.verify_password(password, user["password_hash"] if user else _DUMMY_PASSWORD_HASH)
    except (OSError, RuntimeError, ValueError):
        user = None
        password_ok = False
    if not user or not user["is_active"] or not password_ok:
        _record_login_failure(keys)
        return JSONResponse({"error": "Invalid email or password"}, status_code=401)
    principal = auth_store.get_membership(_auth_database_target(), user["id"])
    if principal is None:
        _record_login_failure(keys)
        return JSONResponse({"error": "Invalid email or password"}, status_code=401)
    token, csrf_token = auth_store.create_auth_session(
        _auth_database_target(), principal["user_id"], principal["agency_id"], AUTH_IDLE_SECONDS, AUTH_ABSOLUTE_SECONDS
    )
    _set_auth_cookies(response, token, csrf_token)
    return {"user": principal["email"], "agency_id": principal["agency_id"], "role": principal["role"]}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    principal = _principal_from_request(request)
    if principal is not None:
        _check_csrf(request, principal)
        token = request.cookies.get(AUTH_COOKIE_NAME)
        if token:
            _ensure_auth_schema()
            auth_store.revoke_auth_session(_auth_database_target(), token)
    _clear_auth_cookies(response)
    return {"message": "Logged out"}


@app.get("/api/auth/me")
async def current_user(request: Request):
    principal = _principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"user": principal["email"], "agency_id": principal["agency_id"], "role": principal["role"]}


@app.post("/api/agencies/{agency_id}/invitations")
async def create_invitation(agency_id: str, request: Request, principal: Optional[dict] = Depends(require_sensitive_access)):
    if not isinstance(principal, dict) or principal.get("agency_id") != agency_id or principal.get("role") not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        payload = await request.json()
        email = str(payload.get("email", "")).strip()
        role = str(payload.get("role", "recruiter")).strip().lower()
        if not email or role not in {"admin", "recruiter", "viewer"}:
            raise ValueError
        if role == "admin" and principal.get("role") != "owner":
            raise ValueError
        _ensure_auth_schema()
        token = auth_store.create_invitation(
            _auth_database_target(), agency_id, email, role, principal["user_id"], INVITATION_SECONDS
        )
        return {"invitation_token": token, "agency_id": agency_id, "role": role}
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid invitation request")


@app.post("/api/auth/accept-invitation")
async def accept_invitation(request: Request, principal: Optional[dict] = Depends(require_sensitive_access)):
    if not isinstance(principal, dict):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = await request.json()
        token = str(payload.get("invitation_token", ""))
        if not token:
            raise ValueError
        _ensure_auth_schema()
        membership = auth_store.accept_invitation(
            _auth_database_target(), token, principal["user_id"], principal["email"]
        )
        auth_token = request.cookies.get(AUTH_COOKIE_NAME)
        if auth_token:
            auth_store.switch_auth_session_agency(_auth_database_target(), auth_token, membership["agency_id"])
        return {"agency_id": membership["agency_id"], "role": membership["role"]}
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid invitation")


@app.get("/view/{session_id}/{filename}")
async def view_resume(session_id: str, filename: str, principal: Optional[dict] = Depends(require_sensitive_access)):
    """
    Serve a resume file for viewing in the browser.
    Returns the file with appropriate content-type for PDF/DOCX.
    """
    # Validate ownership before exposing a file.
    _authorize_session(session_id, principal, "read")
    
    # Get session directory
    session_dir = _get_session_dir(session_id)
    if not session_dir:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Accept only a filename, never a caller-supplied path.
    if (
        not filename
        or filename in {".", ".."}
        or os.path.basename(filename) != filename
        or "/" in filename
        or "\\" in filename
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    # Resolve paths and verify the target remains inside the session directory.
    session_root = os.path.realpath(session_dir)
    file_path = os.path.realpath(os.path.join(session_root, filename))

    try:
        if os.path.commonpath([session_root, file_path]) != session_root:
            raise HTTPException(status_code=403, detail="Access denied")
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        # Default based on extension
        if filename.lower().endswith('.pdf'):
            content_type = 'application/pdf'
        elif filename.lower().endswith('.docx'):
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            content_type = 'application/octet-stream'
    
    # Touch session to extend TTL
    _touch_session(session_id)
    
    # Return file with inline disposition for browser viewing
    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=filename,
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


@app.get("/api/list_uploads")
def list_uploads():
    """
    DEPRECATED: This endpoint is no longer supported.
    Uploads are now session-isolated and not persisted on the server.
    """
    return {
        "files": [],
        "count": 0,
        "message": "Uploads are session-isolated and automatically cleaned up after processing"
    }


@app.delete("/api/clear_uploads")
def clear_uploads():
    """
    DEPRECATED: No longer needed.
    Uploads are automatically cleaned up after each session.
    """
    return {
        "removed": 0,
        "message": "Auto-cleanup is enabled. No manual clearing needed."
    }


def _compute_job_title_relevance(job_title: str, cleaned_resumes: dict) -> dict:
    """
    Compute TF-IDF relevance of job_title against all resumes.
    Returns: dict mapping resume filename to job_title relevance score (0-1).
    """
    if not job_title or not job_title.strip():
        return {file: 1.0 for file in cleaned_resumes}  # If no job_title, all resumes are valid
    
    cleaned_job_title = clean_text(job_title)
    vectors = get_tfidf_vectors(cleaned_job_title, cleaned_resumes)
    cosine_scores = compute_cosine(vectors)
    
    # Map each resume to its job_title relevance score
    relevance = {}
    for idx, file in enumerate(cleaned_resumes.keys()):
        relevance[file] = float(cosine_scores[idx] or 0.0)
    
    return relevance


@app.post("/api/score")
async def api_score(request: Request, principal: Optional[dict] = Depends(require_sensitive_access)):
    """
    Accepts JSON body:
      {"job_title": "...", "skills": "a,b,c", "top_n": 5, "session_id": "..."}
    
    session_id is REQUIRED to identify which uploaded resumes to score.
    Returns: {"results": [{rank, file, score}, ...]}
    
    MANDATORY VALIDATION:
    - If job_title is provided, it MUST meet MINIMUM_SCORE_THRESHOLD
    - Skills alone CANNOT override an irrelevant job_title
    - Only when job_title is relevant OR job_title is empty → results can be returned
    
    After scoring, the session files are automatically cleaned up.
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    job_title = payload.get("job_title", "").strip()
    if not job_title:
        return JSONResponse({"error": "job_title is required"}, status_code=400)
    skills = payload.get("skills", "").strip()
    session_id = payload.get("session_id", "")
    
    try:
        top_n = int(payload.get("top_n", 10))
    except Exception:
        top_n = 10

    if not job_title and not skills:
        return JSONResponse({"error": "Provide job_title or skills"}, status_code=400)
    
    if not session_id:
        return JSONResponse({"error": "session_id is required. Upload files first to get a session_id."}, status_code=400)
    
    # Get the session directory
    if not _is_session_valid(session_id):
        return JSONResponse({"error": "Invalid or expired session_id. Please upload files again."}, status_code=400)
    _authorize_session(session_id, principal, "write")
    resume_dir = _get_session_dir(session_id)
    _touch_session(session_id)

    MINIMUM_SCORE_THRESHOLD = 0.05  # 5%

    try:
        # Load and process resumes
        resumes = load_resumes(resume_folder=resume_dir)
        if not resumes:
            return JSONResponse({"error": "No resumes found in session"}, status_code=400)

        cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}
        
        # Track which resumes passed job_title validation (for early filtering)
        job_title_validated_files = None

        # MANDATORY JOB TITLE VALIDATION
        # If job_title is provided, validate it FIRST
        # Skills alone CANNOT override an irrelevant job_title
        if job_title:
            job_title_relevance = _compute_job_title_relevance(job_title, cleaned_resumes)
            
            # Check if ANY resume meets the job_title threshold
            valid_resumes = {file: score for file, score in job_title_relevance.items() 
                           if score >= MINIMUM_SCORE_THRESHOLD}
            
            if not valid_resumes:
                # Job title is irrelevant to ALL resumes - block all results
                return {"results": []}
            
            # Only resumes passing job-title validation may be scored.
            job_title_validated_files = set(valid_resumes.keys())

        # Now score with combined job_title + skills (or skills only if no job_title)
        # Use ALL cleaned_resumes for TF-IDF vector space computation
        job_desc = f"{job_title} {skills}".strip()
        
        vectors = get_tfidf_vectors(clean_text(job_desc), cleaned_resumes)
        cosine_scores = compute_cosine(vectors)

        results = []
        for idx, (file, text) in enumerate(cleaned_resumes.items()):
            # If job_title validation is active, skip resumes that didn't pass job_title check
            if job_title_validated_files is not None and file not in job_title_validated_files:
                continue
            try:
                # Use idx for cosine_scores since it corresponds to position in cleaned_resumes
                score_obj = score_resume(text, skills, float(cosine_scores[idx] or 0.0))
                matched_skills = []
                missing_skills = []
                if isinstance(score_obj, dict):
                    score_val = float(score_obj.get("score", 0.0))
                    matched_skills = score_obj.get("matched_skills", [])
                    missing_skills = score_obj.get("missing_skills", [])
                else:
                    score_val = float(score_obj or 0.0)
            except Exception as e:
                score_val = float(cosine_scores[idx] or 0.0)
                matched_skills = []
                missing_skills = []
            results.append({"file": file, "score": score_val, "matched_skills": matched_skills, "missing_skills": missing_skills})

        # Filter out resumes with score below minimum threshold (5%)
        filtered_results = [r for r in results if r["score"] >= MINIMUM_SCORE_THRESHOLD]

        # If no results meet the threshold, return empty array
        if not filtered_results:
            return {"results": []}

        ranked = sorted(filtered_results, key=lambda x: x["score"], reverse=True)

        # Return top_n
        out = []
        for i, rec in enumerate(ranked[:top_n], 1):
            out.append({"rank": i, "file": rec["file"], "score": rec["score"], "matched_skills": rec.get("matched_skills", []), "missing_skills": rec.get("missing_skills", [])})

        return {"results": out}
    
    finally:
        # Refresh TTL after use (sliding expiration)
        _touch_session(session_id)


@app.post("/run")
async def run_and_score(
    job_title: Optional[str] = Form(""),
    skills: Optional[str] = Form(""),
    top_n: Optional[int] = Form(10),
    resume: Optional[UploadFile] = File(None),
    resume_zip: Optional[UploadFile] = File(None),
    principal: Optional[dict] = Depends(require_sensitive_access),
):
    """
    Backwards-compatible endpoint that accepts form data with file uploads.
    Creates a temporary session, processes files, scores them, and cleans up.
    
    MANDATORY VALIDATION:
    - If job_title is provided, it MUST meet MINIMUM_SCORE_THRESHOLD
    - Skills alone CANNOT override an irrelevant job_title
    """
    job_title = (job_title or "").strip()
    if not job_title:
        return JSONResponse({"error": "job_title is required"}, status_code=400)
    skills = (skills or "").strip()
    
    if not job_title and not skills:
        return JSONResponse({"error": "Provide job_title or skills"}, status_code=400)

    # Create temporary session directory
    session_id = str(uuid.uuid4())
    temp_dir = tempfile.mkdtemp(prefix=f"resume_session_{session_id}_")
    
    MINIMUM_SCORE_THRESHOLD = 0.05  # 5%
    
    try:
        saved = []
        
        used_names: set[str] = set()

        # Save single resume if provided
        if resume:
            final_name = await _save_validated_resume(resume, temp_dir, used_names)
            saved.append(final_name)
        
        # Save and extract zip if provided
        if resume_zip:
            saved.extend(await _save_and_extract_zip(resume_zip, temp_dir, used_names))
        
        # Load resumes
        resumes = load_resumes(resume_folder=temp_dir)
        
        if not resumes:
            return JSONResponse({"error": "No resumes found"}, status_code=400)

        cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}
        
        # Track which resumes passed job_title validation (for early filtering)
        job_title_validated_files = None
        
        # MANDATORY JOB TITLE VALIDATION
        # If job_title is provided, validate it FIRST
        # Skills alone CANNOT override an irrelevant job_title
        if job_title:
            job_title_relevance = _compute_job_title_relevance(job_title, cleaned_resumes)
            
            # Check if ANY resume meets the job_title threshold
            valid_resumes = {file: score for file, score in job_title_relevance.items() 
                           if score >= MINIMUM_SCORE_THRESHOLD}
            
            if not valid_resumes:
                # Job title is irrelevant to ALL resumes - block all results
                return {"results": []}
            
            # Only resumes passing job-title validation may be scored.
            job_title_validated_files = set(valid_resumes.keys())
        
        # Now score with combined job_title + skills (or skills only if no job_title)
        # Use ALL cleaned_resumes for TF-IDF vector space computation
        job_desc = f"{job_title} {skills}".strip()
        
        vectors = get_tfidf_vectors(clean_text(job_desc), cleaned_resumes)
        cosine_scores = compute_cosine(vectors)

        results = []
        for idx, (file, text) in enumerate(cleaned_resumes.items()):
            # If job_title validation is active, skip resumes that didn't pass job_title check
            if job_title_validated_files is not None and file not in job_title_validated_files:
                continue
            
            try:
                # Use idx for cosine_scores since it corresponds to position in cleaned_resumes
                score_obj = score_resume(text, skills, float(cosine_scores[idx] or 0.0))
                matched_skills = []
                missing_skills = []
                if isinstance(score_obj, dict):
                    score_val = float(score_obj.get("score", 0.0))
                    matched_skills = score_obj.get("matched_skills", [])
                    missing_skills = score_obj.get("missing_skills", [])
                else:
                    score_val = float(score_obj or 0.0)
            except Exception as e:
                score_val = float(cosine_scores[idx] or 0.0)
                matched_skills = []
                missing_skills = []
            results.append({"file": file, "score": score_val, "matched_skills": matched_skills, "missing_skills": missing_skills})

        # Filter out resumes with score below minimum threshold (5%)
        filtered_results = [r for r in results if r["score"] >= MINIMUM_SCORE_THRESHOLD]
        
        if not filtered_results:
            return {"results": []}

        ranked = sorted(filtered_results, key=lambda x: x["score"], reverse=True)

        out = []
        for i, rec in enumerate(ranked[:top_n], 1):
            out.append({"rank": i, "file": rec["file"], "score": rec["score"], "matched_skills": rec.get("matched_skills", []), "missing_skills": rec.get("missing_skills", [])})

        return {"results": out}
    
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({"error": f"Failed to process: {e}"}, status_code=500)
    
    finally:
        # Always clean up the temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[CLEANUP] Temp session {session_id[:8]}... cleaned up")


@app.get("/api/download_results")
def download_results(
    job_title: str = Query(...),
    skills: str = Query(...),
    top_n: int = Query(10),
    session_id: str = Query(...),
    principal: Optional[dict] = Depends(require_sensitive_access),
):
    """
    Run screening and stream CSV of results for download.
    Requires session_id from a previous upload.
    
    Query params: job_title, skills, top_n, session_id
    Example:
      /api/download_results?job_title=Web%20Dev&skills=python,html&top_n=5&session_id=abc123
    
    MANDATORY VALIDATION:
    - If job_title is provided, it MUST meet MINIMUM_SCORE_THRESHOLD
    - Skills alone CANNOT override an irrelevant job_title
    
    Files are cleaned up after download.
    """
    job_title = (job_title or "").strip()
    if not job_title:
        return JSONResponse({"error": "job_title is required"}, status_code=400)
    skills = (skills or "").strip()
    
    if not job_title and not skills:
        raise HTTPException(status_code=400, detail="Provide job_title or skills")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    # Get the session directory
    if not _is_session_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid or expired session_id")
    _authorize_session(session_id, principal, "read")
    resume_dir = _get_session_dir(session_id)
    _touch_session(session_id)

    MINIMUM_SCORE_THRESHOLD = 0.05  # 5%

    try:
        resumes = load_resumes(resume_folder=resume_dir)
        if not resumes:
            raise HTTPException(status_code=400, detail="No resumes found")

        cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}
        
        # MANDATORY JOB TITLE VALIDATION
        # If job_title is provided, validate it FIRST
        # Skills alone CANNOT override an irrelevant job_title
        if job_title:
            job_title_relevance = _compute_job_title_relevance(job_title, cleaned_resumes)
            
            # Check if ANY resume meets the job_title threshold
            valid_resumes = {file: score for file, score in job_title_relevance.items() 
                           if score >= MINIMUM_SCORE_THRESHOLD}
            
            if not valid_resumes:
                # Job title is irrelevant - return empty CSV with just header
                import csv
                from io import StringIO
                
                sio = StringIO()
                writer = csv.writer(sio)
                writer.writerow(["rank", "file", "score", "matched_skills", "missing_skills"])
                csv_bytes = sio.getvalue().encode("utf-8")
                buf = io.BytesIO(csv_bytes)
                buf.seek(0)
                filename = "shortlisted.csv"
                
                return StreamingResponse(
                    buf,
                    media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"},
                )
            
            # Only resumes passing job-title validation may be scored.
            job_title_validated_files = set(valid_resumes.keys())
        else:
            job_title_validated_files = None
        
        # Now score with combined job_title + skills (or skills only if no job_title)
        # Use ALL cleaned_resumes for TF-IDF vector space computation
        job_desc = f"{job_title} {skills}".strip()

        vectors = get_tfidf_vectors(clean_text(job_desc), cleaned_resumes)
        cosine_scores = compute_cosine(vectors)

        results = []
        for idx, (file, text) in enumerate(cleaned_resumes.items()):
            # If job_title validation is active, skip resumes that didn't pass job_title check
            if job_title_validated_files is not None and file not in job_title_validated_files:
                continue
            
            try:
                # Use idx for cosine_scores since it corresponds to position in cleaned_resumes
                score = score_resume(text, skills, float(cosine_scores[idx] or 0.0))
                if isinstance(score, dict):
                    score_val = float(score.get("score", 0.0))
                    matched_skills = score.get("matched_skills", [])
                    missing_skills = score.get("missing_skills", [])
                else:
                    score_val = float(score or 0.0)
                    matched_skills = []
                    missing_skills = []
            except Exception as e:
                score_val = float(cosine_scores[idx] or 0.0)
                matched_skills = []
                missing_skills = []
            results.append({
                "file": file,
                "score": score_val,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
            })

        # Filter out resumes with score below minimum threshold (5%)
        filtered_results = [r for r in results if r["score"] >= MINIMUM_SCORE_THRESHOLD]
        
        ranked = sorted(filtered_results, key=lambda x: x["score"], reverse=True)

        # Build CSV rows
        import csv
        from io import StringIO

        sio = StringIO()
        writer = csv.writer(sio)
        writer.writerow(["rank", "file", "score", "matched_skills", "missing_skills"])
        for i, rec in enumerate(ranked[:top_n], 1):
            writer.writerow([
                i,
                rec["file"],
                rec["score"],
                rec.get("matched_skills", []),
                rec.get("missing_skills", []),
            ])

        csv_bytes = sio.getvalue().encode("utf-8")
        buf = io.BytesIO(csv_bytes)
        buf.seek(0)
        filename = "shortlisted.csv"
        
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    
    finally:
        # Refresh TTL after use (sliding expiration)
        _touch_session(session_id)


@app.post("/api/upload-zip")
async def upload_zip(
    file: UploadFile = File(...), session_id: Optional[str] = Form(None),
    principal: Optional[dict] = Depends(require_sensitive_access),
):
    """
    Upload a single ZIP archive containing many resumes (pdf/docx).
    Extracts into a temporary session directory and returns session_id + saved filenames.
    """
    # Always create a fresh server-generated session.
    # Never reuse a session supplied by the caller.
    owner_user_id = principal.get("user_id") if isinstance(principal, dict) else None
    agency_id = principal.get("agency_id") if isinstance(principal, dict) else None
    session_id, temp_dir = _create_session(owner_user_id, agency_id)
    
    try:
        used_names: set[str] = set()
        saved = await _save_and_extract_zip(file, temp_dir, used_names)
        for filename in saved:
            _add_session_file(session_id, filename)
    except HTTPException as exc:
        _discard_session(session_id, temp_dir)
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    except Exception as exc:
        _discard_session(session_id, temp_dir)
        return JSONResponse({"error": f"Failed to extract ZIP: {exc}"}, status_code=500)

    if not saved:
        _discard_session(session_id, temp_dir)
        return JSONResponse({"error": "ZIP contains no supported resume files"}, status_code=400)
    
    print(f"[UPLOAD-ZIP] Session {session_id[:8]}... extracted {len(saved)} resumes")
    info = _get_session_info(session_id)
    return {
        "saved": saved,
        "count": len(saved),
        "files": info['files'] if info else saved,
        "session_id": session_id,
        "message": "ZIP extracted successfully. Use session_id for scoring."
    }


@app.post("/api/upload")
async def upload_resumes(
    files: List[UploadFile] = File(...), session_id: Optional[str] = Form(None),
    principal: Optional[dict] = Depends(require_sensitive_access),
):
    """
    Upload one or more resume files (pdf/docx).
    Returns a session_id that must be used for subsequent scoring requests.
    Files are stored in a temporary session-isolated directory.
    """
    if not files:
        return JSONResponse({"error": "At least one resume file is required"}, status_code=400)
    if len(files) > MAX_UPLOAD_FILES:
        return JSONResponse({"error": "Upload contains too many resumes"}, status_code=413)

    # Always create a fresh server-generated session.
    # Never reuse a session supplied by the caller.
    owner_user_id = principal.get("user_id") if isinstance(principal, dict) else None
    agency_id = principal.get("agency_id") if isinstance(principal, dict) else None
    session_id, temp_dir = _create_session(owner_user_id, agency_id)
    
    saved = []
    used_names: set[str] = set()
    for f in files:
        try:
            final_name = await _save_validated_resume(f, temp_dir, used_names)
            saved.append(final_name)
            _add_session_file(session_id, final_name)
        except HTTPException as exc:
            _discard_session(session_id, temp_dir)
            return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
        except Exception as e:
            # Clean up on error
            _discard_session(session_id, temp_dir)
            return JSONResponse({"error": f"Failed to save {f.filename}: {e}"}, status_code=500)
    
    print(f"[UPLOAD] Session {session_id[:8]}... saved {len(saved)} resumes")
    info = _get_session_info(session_id)
    return {
        "saved": saved,
        "count": len(info['files']) if info else len(saved),
        "files": info['files'] if info else saved,
        "session_id": session_id,
        "expires_in": info['expires_in'] if info else SESSION_TTL_SECONDS,
        "message": "Files uploaded successfully. Use session_id for scoring."
    }

@app.get("/api/session_status")
def session_status(session_id: str = Query(...), principal: Optional[dict] = Depends(require_sensitive_access)):
    """Return current session details: count, files, expires_in."""
    _authorize_session(session_id, principal, "read")
    info = _get_session_info(session_id)
    if not info:
        return JSONResponse({"error": "Invalid or expired session_id"}, status_code=400)
    return {
        "session_id": session_id,
        "count": len(info['files']),
        "files": info['files'],
        "expires_in": info['expires_in'],
    }
