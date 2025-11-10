# data/src/scorer.py
import re
import csv
import os
from typing import Optional

def score_resume(resume_text: str, job_skills: str, similarity_score: float,
                 verbose: bool = True, log_csv: Optional[str] = None) -> float:
    """
    Score a resume and optionally print debug info and append a row to a CSV file.

    - resume_text: extracted resume text
    - job_skills: comma-separated skills string like "html,css,javascript"
    - similarity_score: TF-IDF cosine score (0..1)
    - verbose: if True print debug info to console
    - log_csv: if provided, append a line to this CSV path
    """
    # Normalize resume text: lowercase, remove punctuation
    resume_text_norm = re.sub(r"[^\w\s]", " ", (resume_text or "").lower())
    resume_words = set(resume_text_norm.split())

    # Normalize skills
    required_skills = [s.strip().lower() for s in (job_skills or "").split(",") if s.strip()]
    required_skills_set = set(required_skills)

    # Avoid division by zero
    if not required_skills_set:
        skill_match = 0.0
        found_skills = []
    else:
        found_skills = sorted(list(resume_words.intersection(required_skills_set)))
        skill_match = len(found_skills) / len(required_skills_set)

    # Weighted combination (same formula you used)
    final_score = 0.7 * float(similarity_score or 0.0) + 0.3 * float(skill_match or 0.0)

    # Verbose console output
    if verbose:
        print(f"  • Skills provided: {', '.join(required_skills_set) if required_skills_set else '(none)'}")
        print(f"  • Found {len(found_skills)} / {len(required_skills_set) if required_skills_set else 0} skills in resume")
        if found_skills:
            print(f"  • Matched skills: {', '.join(found_skills)}")
        print(f"  • Skill match: {skill_match*100:.2f}%")
        print(f"  • TF-IDF similarity: {float(similarity_score or 0.0)*100:.2f}%")
        print(f"  → Final weighted score: {final_score*100:.2f}%")
        print("-" * 60)

    # Optional CSV logging
    if log_csv:
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(log_csv)), exist_ok=True)
        write_header = not os.path.exists(log_csv)
        try:
            with open(log_csv, mode="a", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                if write_header:
                    writer.writerow(["file", "skill_list", "matched_skills", "skill_match_pct",
                                     "tfidf_pct", "final_score_pct"])
                # the caller should pass filename by context; we'll allow file empty string
                writer.writerow([
                    "",  # file name — caller may replace this when calling
                    ";".join(required_skills),
                    ";".join(found_skills),
                    f"{skill_match*100:.2f}",
                    f"{float(similarity_score or 0.0)*100:.2f}",
                    f"{final_score*100:.2f}"
                ])
        except Exception as e:
            if verbose:
                print(f"[WARN] Failed to write debug CSV: {e}")

    return round(final_score, 3)
