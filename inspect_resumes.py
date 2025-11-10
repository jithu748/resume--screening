# inspect_resumes.py
# Put this file in your project root (next to data/ and .venv/)
# Run with: .\.venv\Scripts\python.exe inspect_resumes.py

import os, textwrap, hashlib
from pathlib import Path

# adjust if your resumes folder is different
RESUME_DIR = Path("data") / "resume_uploads"

# import your project's extractor (same as webapp uses)
try:
    from data.src.extract_text import load_resumes
except Exception as e:
    print("Failed to import load_resumes from data.src.extract_text:", e)
    raise SystemExit(1)

print("Resume dir:", RESUME_DIR.resolve())
if not RESUME_DIR.exists():
    print("ERROR: resume uploads folder not found:", RESUME_DIR)
    raise SystemExit(1)

resumes = load_resumes(resume_folder=str(RESUME_DIR))
print("Found resumes:", list(resumes.keys()))

if not resumes:
    print("No resumes found — put some pdf/docx files in", RESUME_DIR)
    raise SystemExit(0)

print("\nPer-file info (clean preview + hash):\n")
for name, text in resumes.items():
    t = (text or "")
    # small preview (first 400 chars)
    preview = t[:400].replace("\n", " ").strip()
    h = hashlib.sha256(t.encode("utf-8")).hexdigest()[:12]
    print(f"--- {name} ---")
    print("Length:", len(t))
    print("SHA12:", h)
    print("Preview:", textwrap.fill(preview or "<empty text>", width=100))
    print()
