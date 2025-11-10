"""
Debug script for verifying ML scoring in Resume Screening.
Generates per-resume breakdown (TF-IDF %, Skill Match %, Final Score %)
and saves a CSV report (out/debug_scores.csv).
"""

import os
import re
import csv
from data.src.extract_text import load_resumes
from data.src.preprocess import clean_text
from data.src.vectorizer import get_tfidf_vectors
from data.src.similarity import compute_cosine
from data.src.scorer import score_resume

# === CONFIGURATION ===
JOB_TITLE = "web developer"
JOB_SKILLS = "html,css,javascript"
TOP_N = 10
OUTPUT_CSV = "out/debug_scores.csv"

# === DETERMINE PATHS ===
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
RESUME_DIR = os.path.join(PROJECT_ROOT, "data", "resume_uploads")

print(f"Resume dir: {RESUME_DIR}")

if not os.path.isdir(RESUME_DIR):
    print("Resume folder not found. Please check path.")
    exit(1)

resumes = load_resumes(resume_folder=RESUME_DIR)
if not resumes:
    print("No resumes found; place some files in data/resume_uploads and re-run.")
    exit(0)

print(f"Found resumes: {list(resumes.keys())}")
print()
print(f"Job description for test: {JOB_TITLE} {JOB_SKILLS}")
print("\nComputing TF-IDF vectors...\n")

# === PREPROCESS & VECTORIZE ===
cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}
vectors = get_tfidf_vectors(clean_text(f"{JOB_TITLE} {JOB_SKILLS}"), cleaned_resumes)
cosine_scores = compute_cosine(vectors)

# === OPEN CSV OUTPUT ===
os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(["file", "skill_match_%", "tfidf_%", "final_score_%", "matched_skills"])

    print("Cosine similarity values (raw):")
    for idx, (file, text) in enumerate(cleaned_resumes.items()):
        cosine_val = float(cosine_scores[idx])
        print(f"  {idx+1}. {file} -> cosine={cosine_val:.6f}  -> as % = {cosine_val*100:.2f}%")

    print("\nNow calling score_resume for each file...\n")

    for idx, (file, text) in enumerate(cleaned_resumes.items()):
        cosine_val = float(cosine_scores[idx])

        # Run scoring (with verbose=True for detailed info)
        final_score = score_resume(text, JOB_SKILLS, cosine_val, verbose=True)

        # Compute matched skills (for CSV)
        resume_text_norm = re.sub(r"[^\w\s]", " ", text.lower())
        resume_words = set(resume_text_norm.split())
        required_skills = [s.strip().lower() for s in JOB_SKILLS.split(",") if s.strip()]
        matched_skills = sorted(list(resume_words.intersection(required_skills)))
        skill_match = len(matched_skills) / len(required_skills) if required_skills else 0.0

        # Write CSV row
        writer.writerow([
            file,
            f"{skill_match*100:.2f}",
            f"{cosine_val*100:.2f}",
            f"{final_score*100:.2f}",
            "; ".join(matched_skills)
        ])

print()
print(f"✅ Debug scoring complete! Results saved to: {OUTPUT_CSV}")
print("You can open it in Excel or VS Code to inspect all values.\n")
print("Tip: For a perfect 100%, create a file containing exactly the job description text and re-run this test.")
