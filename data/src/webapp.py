import os
import sys
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Query, Form
import io
import zipfile
from fastapi.responses import JSONResponse, StreamingResponse
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

app = FastAPI(title="Resume Screening Web UI")

# --- Paths & static mounts ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

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

# In-memory store: maps session_id -> { 'dir': str, 'files': List[str], 'expires_at': float }
_session_storage: dict[str, dict] = {}
_session_lock = threading.Lock()

def _now_ts() -> float:
    return time.time()

def _touch_session(session_id: str) -> None:
    with _session_lock:
        s = _session_storage.get(session_id)
        if s:
            s['expires_at'] = _now_ts() + SESSION_TTL_SECONDS

def _create_session(session_id: Optional[str] = None) -> tuple[str, str]:
    sid = session_id or str(uuid.uuid4())
    temp_dir = tempfile.mkdtemp(prefix=f"resume_session_{sid}_")
    with _session_lock:
        _session_storage[sid] = {
            'dir': temp_dir,
            'files': [],
            'expires_at': _now_ts() + SESSION_TTL_SECONDS,
        }
    return sid, temp_dir

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

def _get_session_info(session_id: str) -> Optional[dict]:
    with _session_lock:
        s = _session_storage.get(session_id)
        if not s:
            return None
        return {
            'dir': s['dir'],
            'files': list(s['files']),
            'expires_at': s['expires_at'],
            'expires_in': max(0, int(s['expires_at'] - _now_ts())),
        }

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
            try:
                if dir_path:
                    shutil.rmtree(dir_path, ignore_errors=True)
            except Exception:
                pass
            with _session_lock:
                _session_storage.pop(sid, None)
            print(f"[CLEANUP] Expired session {sid[:8]}... cleaned up")

@app.on_event("startup")
def _start_cleanup_thread():
    t = threading.Thread(target=_cleanup_expired_sessions_loop, daemon=True)
    t.start()


@app.delete("/api/session")
def end_session(session_id: str = Query(...)):
    """Manually end a session: delete temp dir and remove from memory."""
    dir_path = _get_session_dir(session_id)
    if not dir_path:
        return JSONResponse({"message": "Session already ended or expired"}, status_code=200)
    try:
        shutil.rmtree(dir_path, ignore_errors=True)
    except Exception:
        pass
    with _session_lock:
        _session_storage.pop(session_id, None)
    return {"message": "Session ended and files removed", "session_id": session_id}


@app.post("/api/end_session")
async def end_session_post(request: Request):
    """Manually end a session via POST. Accepts JSON, form, or query param.
    Body (preferred JSON): {"session_id": "..."}
    """
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

    dir_path = _get_session_dir(session_id)
    if not dir_path:
        return {"message": "Session already ended or expired", "session_id": session_id}

    try:
        shutil.rmtree(dir_path, ignore_errors=True)
    except Exception:
        pass
    with _session_lock:
        _session_storage.pop(session_id, None)
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


def save_uploaded_file(upload: UploadFile, temp_dir: str) -> str:
    """
    Save an uploaded file to the temporary directory.
    Returns the saved filename.
    Handles duplicate names by adding counter suffix.
    """
    filename = os.path.basename(upload.filename)
    dest = os.path.join(temp_dir, filename)
    
    # Avoid overwrite by adding suffix if needed
    base, ext = os.path.splitext(filename)
    counter = 1
    final_name = filename
    final_dest = dest
    while os.path.exists(final_dest):
        final_name = f"{base}_{counter}{ext}"
        final_dest = os.path.join(temp_dir, final_name)
        counter += 1
    
    return final_name, final_dest


# NOTE: Removed the global UPLOADS_DIR mount for security.
# Files are now processed in temporary session-isolated directories.

# resume uploads directory (serve as /uploads/<filename>)
# UPLOADS_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "resume_uploads"))
# os.makedirs(UPLOADS_DIR, exist_ok=True)
# app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Allow local testing from browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


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


@app.post("/api/score")
async def api_score(request: Request):
    """
    Accepts JSON body:
      {"job_title": "...", "skills": "a,b,c", "top_n": 5, "session_id": "..."}
    
    session_id is REQUIRED to identify which uploaded resumes to score.
    Returns: {"results": [{rank, file, score}, ...]}
    
    After scoring, the session files are automatically cleaned up.
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    job_title = payload.get("job_title", "")
    skills = payload.get("skills", "")
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
    resume_dir = _get_session_dir(session_id)
    _touch_session(session_id)

    job_desc = f"{job_title} {skills}"

    try:
        # Load and process resumes
        resumes = load_resumes(resume_folder=resume_dir)
        if not resumes:
            return JSONResponse({"error": "No resumes found in session"}, status_code=400)

        cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}

        vectors = get_tfidf_vectors(clean_text(job_desc), cleaned_resumes)
        cosine_scores = compute_cosine(vectors)

        results = []
        for idx, (file, text) in enumerate(cleaned_resumes.items()):
            try:
                score_obj = score_resume(text, skills, float(cosine_scores[idx]))
                if isinstance(score_obj, dict):
                    score_val = float(score_obj.get("score", 0.0))
                else:
                    score_val = float(score_obj or 0.0)
            except Exception:
                score_val = float(cosine_scores[idx] or 0.0)
            results.append({"file": file, "score": score_val})

        ranked = sorted(results, key=lambda x: x["score"], reverse=True)

        # Return top_n
        out = []
        for i, rec in enumerate(ranked[:top_n], 1):
            out.append({"rank": i, "file": rec["file"], "score": rec["score"]})

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
):
    """
    Backwards-compatible endpoint that accepts form data with file uploads.
    Creates a temporary session, processes files, scores them, and cleans up.
    """
    if not job_title and not skills:
        return JSONResponse({"error": "Provide job_title or skills"}, status_code=400)

    # Create temporary session directory
    session_id = str(uuid.uuid4())
    temp_dir = tempfile.mkdtemp(prefix=f"resume_session_{session_id}_")
    
    try:
        saved = []
        
        # Save single resume if provided
        if resume:
            final_name, final_dest = save_uploaded_file(resume, temp_dir)
            content = await resume.read()
            with open(final_dest, "wb") as out:
                out.write(content)
            saved.append(final_name)
        
        # Save and extract zip if provided
        if resume_zip:
            content = await resume_zip.read()
            try:
                z = zipfile.ZipFile(io.BytesIO(content))
            except Exception as e:
                return JSONResponse({"error": f"Invalid zip file: {e}"}, status_code=400)
            
            for info in z.infolist():
                name = info.filename
                if name.endswith("/") or name.endswith("\\"):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext not in [".pdf", ".docx"]:
                    continue
                filename = os.path.basename(name)
                dest = os.path.join(temp_dir, filename)
                try:
                    with z.open(info) as src, open(dest, "wb") as out:
                        out.write(src.read())
                    saved.append(filename)
                except Exception as e:
                    return JSONResponse({"error": f"Failed to extract {name}: {e}"}, status_code=500)
        
        # Process resumes in the temp directory
        job_desc = f"{job_title} {skills}"
        resumes = load_resumes(resume_folder=temp_dir)
        
        if not resumes:
            return JSONResponse({"error": "No resumes found"}, status_code=400)

        cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}
        vectors = get_tfidf_vectors(clean_text(job_desc), cleaned_resumes)
        cosine_scores = compute_cosine(vectors)

        results = []
        for idx, (file, text) in enumerate(cleaned_resumes.items()):
            try:
                score_obj = score_resume(text, skills, float(cosine_scores[idx]))
                if isinstance(score_obj, dict):
                    score_val = float(score_obj.get("score", 0.0))
                else:
                    score_val = float(score_obj or 0.0)
            except Exception:
                score_val = float(cosine_scores[idx] or 0.0)
            results.append({"file": file, "score": score_val})

        ranked = sorted(results, key=lambda x: x["score"], reverse=True)

        out = []
        for i, rec in enumerate(ranked[:top_n], 1):
            out.append({"rank": i, "file": rec["file"], "score": rec["score"]})

        return {"results": out}
    
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
    session_id: str = Query(...)
):
    """
    Run screening and stream CSV of results for download.
    Requires session_id from a previous upload.
    
    Query params: job_title, skills, top_n, session_id
    Example:
      /api/download_results?job_title=Web%20Dev&skills=python,html&top_n=5&session_id=abc123
    
    Files are cleaned up after download.
    """
    if not job_title and not skills:
        raise HTTPException(status_code=400, detail="Provide job_title or skills")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    # Get the session directory
    if not _is_session_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid or expired session_id")
    resume_dir = _get_session_dir(session_id)
    _touch_session(session_id)

    job_desc = f"{job_title} {skills}"

    try:
        resumes = load_resumes(resume_folder=resume_dir)
        if not resumes:
            raise HTTPException(status_code=400, detail="No resumes found")

        cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}

        vectors = get_tfidf_vectors(clean_text(job_desc), cleaned_resumes)
        cosine_scores = compute_cosine(vectors)

        results = []
        for idx, (file, text) in enumerate(cleaned_resumes.items()):
            score = score_resume(text, skills, float(cosine_scores[idx]))
            results.append({"file": file, "score": score})

        ranked = sorted(results, key=lambda x: x["score"], reverse=True)

        # Build CSV rows
        import csv
        from io import StringIO

        sio = StringIO()
        writer = csv.writer(sio)
        writer.writerow(["rank", "file", "score", "text"])
        for i, rec in enumerate(ranked[:top_n], 1):
            text_val = resumes.get(rec["file"], "")
            writer.writerow([i, rec["file"], rec["score"], text_val])

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
async def upload_zip(file: UploadFile = File(...), session_id: Optional[str] = Form(None)):
    """
    Upload a single ZIP archive containing many resumes (pdf/docx).
    Extracts into a temporary session directory and returns session_id + saved filenames.
    """
    # Create or reuse session
    if session_id and _is_session_valid(session_id):
        temp_dir = _get_session_dir(session_id)
        _touch_session(session_id)
    else:
        session_id, temp_dir = _create_session(session_id)
    
    try:
        content = await file.read()
        z = zipfile.ZipFile(io.BytesIO(content))
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        del _session_storage[session_id]
        return JSONResponse({"error": f"Invalid zip file: {e}"}, status_code=400)

    saved = []
    for info in z.infolist():
        name = info.filename
        # skip directories
        if name.endswith('/') or name.endswith('\\'):
            continue
        # only accept pdf/docx
        ext = os.path.splitext(name)[1].lower()
        if ext not in ['.pdf', '.docx']:
            continue
        # sanitize basename
        filename = os.path.basename(name)
        dest = os.path.join(temp_dir, filename)
        try:
            with z.open(info) as src, open(dest, 'wb') as out:
                out.write(src.read())
            saved.append(filename)
            _add_session_file(session_id, filename)
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            with _session_lock:
                _session_storage.pop(session_id, None)
            return JSONResponse({"error": f"Failed to extract {name}: {e}"}, status_code=500)
    
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
async def upload_resumes(files: List[UploadFile] = File(...), session_id: Optional[str] = Form(None)):
    """
    Upload one or more resume files (pdf/docx).
    Returns a session_id that must be used for subsequent scoring requests.
    Files are stored in a temporary session-isolated directory.
    """
    # Create or reuse session
    if session_id and _is_session_valid(session_id):
        temp_dir = _get_session_dir(session_id)
        _touch_session(session_id)
    else:
        session_id, temp_dir = _create_session(session_id)
    
    saved = []
    for f in files:
        try:
            final_name, final_dest = save_uploaded_file(f, temp_dir)
            content = await f.read()
            with open(final_dest, "wb") as out:
                out.write(content)
            saved.append(final_name)
            _add_session_file(session_id, final_name)
        except Exception as e:
            # Clean up on error
            shutil.rmtree(temp_dir, ignore_errors=True)
            with _session_lock:
                _session_storage.pop(session_id, None)
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
def session_status(session_id: str = Query(...)):
    """Return current session details: count, files, expires_in."""
    info = _get_session_info(session_id)
    if not info:
        return JSONResponse({"error": "Invalid or expired session_id"}, status_code=400)
    return {
        "session_id": session_id,
        "count": len(info['files']),
        "files": info['files'],
        "expires_in": info['expires_in'],
    }
