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

# resume uploads directory (serve as /uploads/<filename>)
UPLOADS_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "resume_uploads"))
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

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
    """Return list of files currently saved in the server uploads folder."""
    try:
        files = sorted([f for f in os.listdir(UPLOADS_DIR) if os.path.isfile(os.path.join(UPLOADS_DIR, f))])
    except Exception:
        files = []
    return {"files": files, "count": len(files)}


@app.delete("/api/clear_uploads")
def clear_uploads():
    """Delete all files in the uploads folder (useful for testing)."""
    removed = 0
    errors = []
    for name in list(os.listdir(UPLOADS_DIR)):
        path = os.path.join(UPLOADS_DIR, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
                removed += 1
        except Exception as e:
            errors.append(str(e))
    return {"removed": removed, "errors": errors}


@app.post("/api/score")
async def api_score(request: Request):
    """
    Accepts JSON body:
      {"job_title": "...", "skills": "a,b,c", "top_n": 5}
    Returns: {"results": [{rank, file, score}, ...]}
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    job_title = payload.get("job_title", "")
    skills = payload.get("skills", "")
    try:
        top_n = int(payload.get("top_n", 10))
    except Exception:
        top_n = 10

    if not job_title and not skills:
        return JSONResponse({"error": "Provide job_title or skills"}, status_code=400)

    job_desc = f"{job_title} {skills}"

    # resolve resume directory (default: resume_uploads)
    resume_dir = UPLOADS_DIR
    if not os.path.isdir(resume_dir):
        return JSONResponse({"error": f"Resume folder not found: {resume_dir}"}, status_code=400)

    # always re-load resumes from disk so newly uploaded files are included immediately
    resumes = load_resumes(resume_folder=resume_dir)
    if not resumes:
        return JSONResponse({"error": "No resumes found"}, status_code=400)

    cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}

    vectors = get_tfidf_vectors(clean_text(job_desc), cleaned_resumes)
    cosine_scores = compute_cosine(vectors)

    results = []
    # compute score_resume for each resume in the same ordering as cleaned_resumes.items()
    for idx, (file, text) in enumerate(cleaned_resumes.items()):
        # score_resume may return a dict or a numeric value — handle both
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


@app.post("/run")
async def run_and_score(
    job_title: Optional[str] = Form(""),
    skills: Optional[str] = Form(""),
    top_n: Optional[int] = Form(10),
    resume: Optional[UploadFile] = File(None),
    resume_zip: Optional[UploadFile] = File(None),
):
    """
    Backwards-compatible endpoint to support older templates that POST a form to /run
    Accepts optional uploaded resume or resume_zip, saves them, and then returns scoring results.
    """
    # Save single resume if provided
    try:
        if resume:
            saved = []
            filename = os.path.basename(resume.filename)
            dest = os.path.join(UPLOADS_DIR, filename)
            base, ext = os.path.splitext(filename)
            counter = 1
            final_name = filename
            final_dest = dest
            while os.path.exists(final_dest):
                final_name = f"{base}_{counter}{ext}"
                final_dest = os.path.join(UPLOADS_DIR, final_name)
                counter += 1
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
            saved = []
            for info in z.infolist():
                name = info.filename
                if name.endswith("/") or name.endswith("\\"):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext not in [".pdf", ".docx"]:
                    continue
                filename = os.path.basename(name)
                dest = os.path.join(UPLOADS_DIR, filename)
                try:
                    with z.open(info) as src, open(dest, "wb") as out:
                        out.write(src.read())
                    saved.append(filename)
                except Exception as e:
                    return JSONResponse({"error": f"Failed to extract {name}: {e}"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": f"Failed to save uploaded files: {e}"}, status_code=500)

    # Now re-use api_score logic by building a JSON-like payload and calling internal logic.
    if not job_title and not skills:
        return JSONResponse({"error": "Provide job_title or skills"}, status_code=400)

    job_desc = f"{job_title} {skills}"
    resume_dir = UPLOADS_DIR
    if not os.path.isdir(resume_dir):
        return JSONResponse({"error": f"Resume folder not found: {resume_dir}"}, status_code=400)

    resumes = load_resumes(resume_folder=resume_dir)
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


@app.get("/api/download_results")
def download_results(job_title: str = Query(...), skills: str = Query(...), top_n: int = Query(10)):
    """
    Run screening and stream CSV of results for download.
    Query params: job_title, skills, top_n
    Example:
      /api/download_results?job_title=Web%20Dev&skills=python,html&top_n=5
    """
    if not job_title and not skills:
        raise HTTPException(status_code=400, detail="Provide job_title or skills")

    job_desc = f"{job_title} {skills}"

    resume_dir = UPLOADS_DIR
    if not os.path.isdir(resume_dir):
        raise HTTPException(status_code=400, detail=f"Resume folder not found: {resume_dir}")

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

    # Build CSV rows (include rank, file, score). Include extracted text column too.
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


@app.post("/api/upload-zip")
async def upload_zip(file: UploadFile = File(...)):
    """Upload a single ZIP archive containing many resumes (pdf/docx). Extracts into resume_uploads/ and returns saved filenames."""
    save_dir = UPLOADS_DIR
    os.makedirs(save_dir, exist_ok=True)
    try:
        content = await file.read()
        z = zipfile.ZipFile(io.BytesIO(content))
    except Exception as e:
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
        dest = os.path.join(save_dir, filename)
        try:
            with z.open(info) as src, open(dest, 'wb') as out:
                out.write(src.read())
            saved.append(filename)
        except Exception as e:
            return JSONResponse({"error": f"Failed to extract {name}: {e}"}, status_code=500)
    return {"saved": saved, "count": len(saved)}


@app.post("/api/upload")
async def upload_resumes(files: List[UploadFile] = File(...)):
    """Upload one or more resume files (pdf/docx). Saves to resume_uploads/"""
    save_dir = UPLOADS_DIR
    os.makedirs(save_dir, exist_ok=True)
    saved = []
    for f in files:
        # sanitize filename
        filename = os.path.basename(f.filename)
        dest = os.path.join(save_dir, filename)

        # avoid overwrite by adding suffix if already exists
        base, ext = os.path.splitext(filename)
        counter = 1
        final_name = filename
        final_dest = dest
        while os.path.exists(final_dest):
            final_name = f"{base}_{counter}{ext}"
            final_dest = os.path.join(save_dir, final_name)
            counter += 1

        try:
            content = await f.read()
            with open(final_dest, "wb") as out:
                out.write(content)
            saved.append(final_name)
        except Exception as e:
            return JSONResponse({"error": f"Failed to save {filename}: {e}"}, status_code=500)

    # Log saved names (helpful on server logs)
    print("[UPLOAD] saved resumes:", saved)
    return {"saved": saved, "count": len(saved)}
