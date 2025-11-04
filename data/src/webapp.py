import os
import sys
from fastapi import FastAPI, Request, UploadFile, File
import io
import zipfile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import os
from typing import List
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

# ensure local src folder is on sys.path so imports like `import extract_text` work
src_dir = os.path.dirname(__file__)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

app = FastAPI(title="Resume Screening Web UI")

# Mount static files
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "web", "static"))
TEMPLATES_DIR = os.path.abspath(os.path.join(BASE_DIR, "web", "templates"))

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Allow local testing from browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=None)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/score")
async def api_score(payload: dict):
    """Accepts: {"job_title": "...", "skills": "a,b,c", "top_n": 5}
    Returns: JSON list of {file, score, rank}
    """
    job_title = payload.get("job_title", "")
    skills = payload.get("skills", "")
    top_n = int(payload.get("top_n", 10))

    if not job_title and not skills:
        return JSONResponse({"error": "Provide job_title or skills"}, status_code=400)

    job_desc = f"{job_title} {skills}"

    # resolve resume directory (default: data/resume_uploads)
    resume_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resume_uploads"))
    if not os.path.isdir(resume_dir):
        return JSONResponse({"error": f"Resume folder not found: {resume_dir}"}, status_code=400)

    resumes = load_resumes(resume_folder=resume_dir)
    if not resumes:
        return JSONResponse({"error": "No resumes found"}, status_code=400)

    cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}

    vectors = get_tfidf_vectors(clean_text(job_desc), cleaned_resumes)
    cosine_scores = compute_cosine(vectors)

    results = []
    # compute score_resume for each resume in the same ordering as cleaned_resumes.values()
    for idx, (file, text) in enumerate(cleaned_resumes.items()):
        score = score_resume(text, skills, float(cosine_scores[idx]))
        results.append({"file": file, "score": score})

    ranked = sorted(results, key=lambda x: x["score"], reverse=True)

    # Return top_n
    out = []
    for i, rec in enumerate(ranked[:top_n], 1):
        out.append({"rank": i, "file": rec["file"], "score": rec["score"]})

    return {"results": out}


@app.post("/api/upload-zip")
async def upload_zip(file: UploadFile = File(...)):
    """Upload a single ZIP archive containing many resumes (pdf/docx). Extracts into data/resume_uploads/ and returns saved filenames."""
    save_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resume_uploads"))
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
    """Upload one or more resume files (pdf/docx). Saves to data/resume_uploads/"""
    save_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resume_uploads"))
    os.makedirs(save_dir, exist_ok=True)
    saved = []
    for f in files:
        # sanitize filename
        filename = os.path.basename(f.filename)
        dest = os.path.join(save_dir, filename)
        try:
            content = await f.read()
            with open(dest, "wb") as out:
                out.write(content)
            saved.append(filename)
        except Exception as e:
            return JSONResponse({"error": f"Failed to save {filename}: {e}"}, status_code=500)
    return {"saved": saved, "count": len(saved)}
