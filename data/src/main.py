import os
import argparse
from extract_text import load_resumes
from preprocess import clean_text
from vectorizer import get_tfidf_vectors
from similarity import compute_cosine
from scorer import score_resume
import shutil


# ✅ Added reusable function
def run_screening(job_title: str,
                  job_skills: str,
                  resume_dir: str,
                  top_n: int = 10,
                  include_text: bool = False,
                  copy_top_dir: str = None):
    """
    Reusable version of your resume screening logic.
    Returns a dictionary with rows of results (rank, file, score, etc.)
    """
    if not os.path.isabs(resume_dir):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
        resume_dir = os.path.abspath(os.path.join(base_dir, resume_dir))

    resumes = load_resumes(resume_folder=resume_dir)
    if not resumes:
        return {"error": f"No resumes found in '{resume_dir}'", "rows": []}

    cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}
    job_desc = f"{job_title} {job_skills}"

    vectors = get_tfidf_vectors(clean_text(job_desc), cleaned_resumes)
    cosine_scores = compute_cosine(vectors)

    results = []
    for idx, (file, text) in enumerate(cleaned_resumes.items()):
        score_info = score_resume(text, job_skills, cosine_scores[idx])
        if isinstance(score_info, dict):
            score = float(score_info.get("score", 0.0))
            matches = score_info.get("matches", [])
        else:
            try:
                score = float(score_info)
            except Exception:
                score = 0.0
            matches = []
        results.append({"file": file, "score": score, "matches": matches, "text": resumes.get(file, "")})

    ranked = sorted(results, key=lambda x: x["score"], reverse=True)

    rows = []
    for i, r in enumerate(ranked[:top_n], 1):
        row = {"rank": i, "file": r["file"], "score": r["score"]}
        if include_text:
            row["text"] = r.get("text", "")
        if r.get("matches"):
            row["matches"] = r["matches"]
        rows.append(row)

    # Optional: copy top resumes to a folder
    if copy_top_dir:
        copy_dir = copy_top_dir if os.path.isabs(copy_top_dir) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".", copy_top_dir))
        os.makedirs(copy_dir, exist_ok=True)
        for row in rows:
            src = os.path.join(resume_dir, row["file"])
            if os.path.exists(src):
                # Use percent-style name for readability
                numeric_score = row.get("score", 0.0)
                try:
                    numeric_score = float(numeric_score)
                except Exception:
                    numeric_score = 0.0
                numeric_score = max(0.0, min(1.0, numeric_score))
                score_pct = round(numeric_score * 100, 2)
                dst_name = f"{score_pct}pct_{row['file']}"
                shutil.copy2(src, os.path.join(copy_dir, dst_name))

    return {"rows": rows}


# ✅ Your existing CLI code — unchanged
def parse_args():
    p = argparse.ArgumentParser(description="Resume screening runner")
    p.add_argument("--job-title", dest="job_title", help="Job title (e.g. 'Full Stack Developer')")
    p.add_argument("--skills", dest="skills", help="Comma-separated skills (e.g. 'python,react')")
    p.add_argument("--resume-dir", dest="resume_dir", default="resume_uploads/",
                   help="Path to the resumes folder (default: resume_uploads/ relative to data folder)")
    p.add_argument("--top", dest="top_n", type=int, default=10, help="How many top candidates to show")
    p.add_argument("--output-csv", dest="output_csv", help="Path to write results CSV (optional)")
    p.add_argument("--output-xlsx", dest="output_xlsx", help="Path to write results Excel file (optional)")
    p.add_argument("--copy-top-dir", dest="copy_top_dir", help="Directory to copy top-N resume files into (optional)")
    p.add_argument("--output-dir", dest="output_dir", help="Base output directory to resolve relative output paths (optional)")
    p.add_argument("--include-text", dest="include_text", action="store_true", help="Include full resume text in CSV/XLSX output")
    p.add_argument("--zip", dest="zip", action="store_true", help="Create a zip archive of copied top resumes (requires --copy-top-dir)")
    return p.parse_args()


def main():
    args = parse_args()

    # interactive fallback if not provided
    job_title = args.job_title or input("Job Title: ")
    job_skills = args.skills or input("Skills Required (comma separated): ")
    job_desc = f"{job_title} {job_skills}"

    print("\nLoading resumes...")
    if os.path.isabs(args.resume_dir):
        resume_dir = args.resume_dir
    else:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        resume_dir = os.path.abspath(os.path.join(base_dir, args.resume_dir))

    resumes = load_resumes(resume_folder=resume_dir)
    if not resumes:
        print(f"No resumes found in '{args.resume_dir}'. Place .pdf or .docx files there and try again.")
        return

    cleaned_resumes = {f: clean_text(t) for f, t in resumes.items()}

    print("Vectorizing & scoring...")
    vectors = get_tfidf_vectors(clean_text(job_desc), cleaned_resumes)
    cosine_scores = compute_cosine(vectors)

    results = []
    for idx, (file, text) in enumerate(cleaned_resumes.items()):
        score_info = score_resume(text, job_skills, cosine_scores[idx])
        # Coerce score to float safely (score_resume may return dict or numeric)
        if isinstance(score_info, dict):
            try:
                score = float(score_info.get("score", 0.0))
            except Exception:
                score = 0.0
        else:
            try:
                score = float(score_info)
            except Exception:
                score = 0.0
        results.append((file, score))

    ranked = sorted(results, key=lambda x: x[1], reverse=True)

    print("\nTop Candidates:")
    for i, (file, score) in enumerate(ranked[: args.top_n], 1):
        # ensure score is numeric, then clamp to 0..1 and convert to percentage
        try:
            numeric_score = float(score)
        except Exception:
            numeric_score = 0.0
        # if your scores are already in 0..1 (cosine/combined), convert to 0..100
        numeric_score = max(0.0, min(1.0, numeric_score))
        score_pct = round(numeric_score * 100, 2)
        print(f"{i}. {file} - Score: {score_pct}%")

    # Copy top resumes if needed
    if args.copy_top_dir:
        copy_dir = args.copy_top_dir
        if not os.path.isabs(copy_dir):
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            copy_dir = os.path.abspath(os.path.join(base_dir, copy_dir))
        os.makedirs(copy_dir, exist_ok=True)
        for i, (file, score) in enumerate(ranked[: args.top_n], 1):
            src = os.path.join(resume_dir, file)
            if os.path.exists(src):
                try:
                    numeric_score = float(score)
                except Exception:
                    numeric_score = 0.0
                numeric_score = max(0.0, min(1.0, numeric_score))
                score_pct = round(numeric_score * 100, 2)
                dst_name = f"{score_pct}pct_{file}"
                shutil.copy2(src, os.path.join(copy_dir, dst_name))
        print(f"Copied top candidates to {copy_dir}")


if __name__ == "__main__":
    main()
