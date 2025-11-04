Resume Screening — Full (from-scratch) Guide and Interview Notes

This README now contains a complete "from-scratch" explanation you can use to understand the project end-to-end, run it locally, and explain it in interviews. It covers setup, run commands, internals, tradeoffs, and suggested next steps.

Table of contents
- From scratch setup (step-by-step)
- Quick run examples
- Detailed code walkthrough (file-by-file)
- How scoring works (exact flow)
- Exports and automation options (CSV/XLSX, copy, zip)
- Limitations, tradeoffs and scaling
- Troubleshooting common errors
- Interview cheat-sheet (ready-to-speak bullets + 1-minute pitch)
- Next steps you can implement

## From-scratch setup (Windows PowerShell)

Prerequisites
- Python 3.10+ installed and available in PATH. If not installed, get it from https://www.python.org/downloads/
- Git (optional) to clone the repo.

Step 1 — Clone and inspect repo
```powershell
cd C:\path\where\you\keep\projects
git clone <repo-url> resume_screening
cd "d:\projects\resume_screening"
```

Step 2 — Create & activate a virtual environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Step 3 — Upgrade pip and install dependencies
```powershell
D:/projects/resume_screening/.venv/Scripts/python.exe -m pip install --upgrade pip
D:/projects/resume_screening/.venv/Scripts/python.exe -m pip install -r data/requirements.txt
# Optional for Excel output
D:/projects/resume_screening/.venv/Scripts/python.exe -m pip install openpyxl
```

Step 4 — (one-time) download NLTK data
```powershell
D:/projects/resume_screening/.venv/Scripts/python.exe -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet'); nltk.download('omw-1.4')"
```

Step 5 — Put your resumes in `data/resume_uploads/`
- Supported: `.pdf` and `.docx`.
- If you have scanned PDFs (image-only), run OCR first (Tesseract) to produce a text PDF or convert to `.docx`.

Step 6 — Run the app
- Interactive (prompts):
```powershell
D:/projects/resume_screening/.venv/Scripts/python.exe main.py
```
- Non-interactive (recommended for automation):
```powershell
D:/projects/resume_screening/.venv/Scripts/python.exe main.py --job-title "Web Developer" --skills "python,html,css" --top 5
```

## Quick run examples (copyable)

- Print top 5 matches:
```powershell
D:/projects/resume_screening/.venv/Scripts/python.exe main.py --job-title "Web Developer" --skills "python,html,css" --top 5
```

- Export CSV and copy top-3 resumes into `out/shortlisted` and zip them:
```powershell
D:/projects/resume_screening/.venv/Scripts/python.exe main.py --job-title "Web Dev" --skills "python,html" --top 3 --output-csv out/results.csv --copy-top-dir out/shortlisted --zip
```

- Include full extracted text in CSV (can be large):
```powershell
D:/projects/resume_screening/.venv/Scripts/python.exe main.py --job-title "Data Scientist" --skills "python,pandas" --include-text --output-csv out/results_with_text.csv
```

## Web UI & Bulk import

You can run a simple web interface (FastAPI + static frontend) that allows:
- Running the same TF-IDF scoring from your browser
- Uploading single or multiple resume files (.pdf/.docx)
- Uploading a single ZIP archive containing hundreds of resumes (server extracts them into `data/resume_uploads`)

Run the webapp (from project root):

```powershell
# activate venv first
.\.venv\Scripts\Activate.ps1
# install web deps if needed
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn python-multipart
# start the server
D:/projects/resume_screening/.venv/Scripts/python.exe -m uvicorn data.src.webapp:app --reload
```

Using the UI:
- Open http://127.0.0.1:8000/ in your browser.
- Use the "Upload ZIP" button to upload a single .zip that contains many resumes (the server will extract .pdf and .docx files automatically into `data/resume_uploads/`).
- Or use the file chooser to select multiple files at once and click "Upload".

Local bulk import (fast copy of many files)
- If you already have a local folder with many resumes, you can run the helper script to copy them into the project folder:

```powershell
D:/projects/resume_screening/.venv/Scripts/python.exe scripts/import_folder.py "C:\path\to\resumes"
```

This script copies only `.pdf` and `.docx` files and is efficient for moving hundreds of files into the app.


## Detailed code walkthrough (file-by-file)

- `main.py` (project root): small launcher that ensures `data/src` is on `sys.path` and runs the CLI-enabled script.
- `data/src/main.py`: the orchestrator. Responsibilities:
  - Parse CLI args (argparse).
  - Load resumes from `--resume-dir` (default `data/resume_uploads`).
  - Preprocess, vectorize and compute similarity.
  - Score resumes using `scorer.py` logic.
  - Print and optionally export results (CSV/XLSX), copy resumes, zip outputs.
- `data/src/extract_text.py`: text extraction functions. Key points:
  - Uses `pdfminer.six` to extract text from regular PDFs.
  - Uses `python-docx` (`from docx import Document`) to read `.docx`.
  - `load_resumes(resume_folder)` returns a dict mapping filename -> extracted text.
- `data/src/preprocess.py`: cleaning utilities. Typical tasks:
  - Lowercasing, punctuation removal, normalization.
  - Tokenization and stopword removal (NLTK).
  - (Optional) lemmatization or stemming.
- `data/src/vectorizer.py`: builds TF-IDF with sklearn. The code fits TF-IDF on [job_desc] + resumes and returns a matrix.
- `data/src/similarity.py`: computes cosine similarity. It compares job vector vs resume vectors and returns scores.
- `data/src/scorer.py`: applies business rules combining similarity and explicit skill checks.

## How scoring works (flow)

1. Job description (job title + skills string) is cleaned and converted to a TF-IDF vector.
2. Each resume is cleaned and converted to TF-IDF vectors using the same vocabulary.
3. Cosine similarity between the job vector and each resume vector is computed.
4. `scorer.py` adjusts the raw similarity by checking presence of required skills (simple substring checks or token matches). Final score is a weighted combination.

You can open `data/src/scorer.py` to see exact weights and matching strategy — this is the main place to adjust how much skills vs semantic match matter.

## Exports and automation options

- `--output-csv PATH` — writes ranked results to CSV. If `--include-text` is given, CSV includes a `text` column.
- `--output-xlsx PATH` — writes Excel output (requires `openpyxl`).
- `--copy-top-dir PATH` — copies top-N resumes to the provided directory; filenames are prefixed with the score.
- `--zip` — creates a zip of the copied directory (use together with `--copy-top-dir`).
- `--output-dir DIR` — base directory to resolve relative output paths (useful for CI).

All outputs create missing directories automatically.

## Limitations, tradeoffs and scaling (talking points)

- TF-IDF (current approach):
  - Pros: cheap, explainable, sparse; good baseline for structured resume text.
  - Cons: limited semantic understanding; fails on paraphrased or implicit matches.
- Preprocessing and extraction are brittle across resume formats — inconsistent layouts reduce extraction quality.
- Memory: TF-IDF keeps sparse matrices in memory. For thousands of resumes, consider precomputing and storing vectors or using an index.

## Troubleshooting — common errors and fixes

- ModuleNotFoundError: make sure you activated the venv and installed `requirements.txt`.
  - Example: `D:/projects/resume_screening/.venv/Scripts/python.exe -m pip install -r data/requirements.txt`
- `No /Root object! - Is this really a PDF?` — `pdfminer` failed; the PDF might be corrupted or scanned. Use OCR (Tesseract) to extract text first.
- Empty results or low scores — check `data/resume_uploads` contains valid `.pdf`/`.docx` and that `load_resumes()` returns non-empty strings.
- Excel export fails: install `openpyxl` in the venv.

## Interview cheat-sheet ( ready-to-speak bullets )

Use these concise points when asked about the project:

- "I built a modular resume-screening tool that extracts text from PDF/DOCX, preprocesses it, vectorizes using TF-IDF, and ranks resumes by cosine similarity combined with explicit skill matching."
- "Design: separate concerns — extraction, preprocessing, vectorization, scoring, and output; this makes testing and replacement of components straightforward."
- "Why TF-IDF: quick baseline, interpretable, sparse (memory efficient), easy to compute and tune."
- "Scaling plan: precompute and persist resume vectors, or move to semantic embeddings and an ANN index (FAISS) for large-scale matching."
- "Error handling: handle invalid PDFs gracefully, create output directories automatically, and provide CSV/XLSX exports and zipped shortlisted resumes for downstream workflows."
- "Next steps: add multiprocessing for IO-heavy text extraction, persist vectors with joblib for repeated queries, add a tiny REST API for non-CLI usage."

One-minute pitch (template):

"I built an automated resume-screening prototype that reads PDF and Word resumes, normalizes and vectorizes their text with TF-IDF, and ranks candidates by cosine similarity combined with explicit skill checks. It's modular, supports CLI automation and exporting results (CSV/Excel), and can be scaled to thousands of resumes by persisting vectors or switching to dense embeddings with an ANN index."

## Next steps (what we can implement quickly)

If you want, I can implement any of these next items — tell me which and I'll add it to the todo list and start:

1. Persist resume vectors to disk (joblib) so queries are fast after indexing.
2. Parallelize text extraction with multiprocessing to handle large batches.
3. Add a small FastAPI service to accept a job description and return ranked candidates (useful for an internal dashboard).
4. Produce a one-page printable interview cheat-sheet (bullet points only).

---

If you'd like, I will now add the one-page interview cheat-sheet as a separate file `INTERVIEW.md` and/or implement vector persistence (option 1). Which should I do next?
