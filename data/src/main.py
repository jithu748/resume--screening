import os
import argparse
from extract_text import load_resumes
from preprocess import clean_text
from vectorizer import get_tfidf_vectors
from similarity import compute_cosine
from scorer import score_resume
import shutil


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

    # Interactive fallback if args not provided
    if args.job_title:
        job_title = args.job_title
    else:
        job_title = input("Job Title: ")

    if args.skills:
        job_skills = args.skills
    else:
        job_skills = input("Skills Required (comma separated): ")

    job_desc = f"{job_title} {job_skills}"

    print("\nLoading resumes...")
    # Resolve resume directory relative to this script if a relative path was provided
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
        score = score_resume(text, job_skills, cosine_scores[idx])
        results.append((file, score))

    # Sort by score
    ranked = sorted(results, key=lambda x: x[1], reverse=True)

    print("\nTop Candidates:")
    # Print results and prepare export structure
    rows = []
    for i, (file, score) in enumerate(ranked[: args.top_n], 1):
        print(f"{i}. {file} - Score: {score:.3f}")
        row = {"rank": i, "file": file, "score": score}
        if args.include_text:
            # include the original extracted text (not cleaned) for review
            row["text"] = resumes.get(file, "")
        rows.append(row)

    # Export CSV/XLSX if requested
    try:
        import pandas as _pd
    except Exception:
        _pd = None

    if args.output_csv or args.output_xlsx:
        if _pd is None:
            print("pandas is required to write CSV/XLSX output. Install pandas and try again.")
        else:
            df = _pd.DataFrame(rows)

            # If output_dir provided, resolve relative output paths against it
            output_base = None
            if args.output_dir:
                if os.path.isabs(args.output_dir):
                    output_base = args.output_dir
                else:
                    output_base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", args.output_dir))
                os.makedirs(output_base, exist_ok=True)

            if args.output_csv:
                out_csv = args.output_csv
                if output_base and not os.path.isabs(out_csv):
                    out_csv = os.path.join(output_base, out_csv)
                out_csv = os.path.abspath(out_csv)
                out_dir = os.path.dirname(out_csv)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                df.to_csv(out_csv, index=False)
                print(f"Wrote results CSV -> {out_csv}")
            if args.output_xlsx:
                out_xlsx = args.output_xlsx
                if output_base and not os.path.isabs(out_xlsx):
                    out_xlsx = os.path.join(output_base, out_xlsx)
                out_xlsx = os.path.abspath(out_xlsx)
                out_dir_x = os.path.dirname(out_xlsx)
                if out_dir_x:
                    os.makedirs(out_dir_x, exist_ok=True)
                try:
                    df.to_excel(out_xlsx, index=False)
                    print(f"Wrote results Excel -> {out_xlsx}")
                except ModuleNotFoundError:
                    print("openpyxl is required to write Excel files. Install it with: pip install openpyxl")
                except Exception as e:
                    print(f"Failed to write Excel file {out_xlsx}: {e}")

    # Copy top resumes into a folder (optional)
    if args.copy_top_dir:
        copy_dir = args.copy_top_dir
        # resolve relative to project root if not absolute
        if not os.path.isabs(copy_dir):
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            copy_dir = os.path.abspath(os.path.join(base_dir, copy_dir))
        os.makedirs(copy_dir, exist_ok=True)
        for row in rows:
            src = os.path.join(resume_dir, row["file"])
            if os.path.exists(src):
                # prefix filename with score for quick overview
                score_prefix = f"{row['score']:.3f}_"
                dst_name = score_prefix + row["file"]
                dst = os.path.join(copy_dir, dst_name)
                try:
                    shutil.copy2(src, dst)
                except Exception as e:
                    print(f"Failed to copy {src} -> {dst}: {e}")
        print(f"Copied top candidates to {copy_dir}")


if __name__ == "__main__":
    main()
