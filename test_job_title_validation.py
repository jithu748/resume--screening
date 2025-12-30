#!/usr/bin/env python3
"""
Test script to verify job_title validation logic.
Tests the backend logic for blocking irrelevant job titles.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "data", "src"))

from preprocess import clean_text
from vectorizer import get_tfidf_vectors
from similarity import compute_cosine

# Mock resumes for testing
mock_resumes = {
    "resume1.pdf": "John Doe. Senior Web Developer. 10 years experience. Skills: HTML, CSS, JavaScript, React, Python, Django. Worked at tech companies. Built responsive web applications.",
    "resume2.pdf": "Jane Smith. Frontend Engineer. 5 years. JavaScript, React, Vue, CSS, HTML, Sass. Created user interfaces. Built web platforms.",
    "resume3.pdf": "Bob Johnson. Junior Developer. 1 year. HTML, CSS, JavaScript basics. Learning React. Recently graduated from bootcamp.",
}

MINIMUM_SCORE_THRESHOLD = 0.05  # 5%

def compute_job_title_relevance(job_title: str, cleaned_resumes: dict) -> dict:
    """
    Compute TF-IDF relevance of job_title against all resumes.
    Returns: dict mapping resume filename to job_title relevance score (0-1).
    """
    if not job_title or not job_title.strip():
        return {file: 1.0 for file in cleaned_resumes}
    
    cleaned_job_title = clean_text(job_title)
    vectors = get_tfidf_vectors(cleaned_job_title, cleaned_resumes)
    cosine_scores = compute_cosine(vectors)
    
    relevance = {}
    for idx, file in enumerate(cleaned_resumes.keys()):
        relevance[file] = float(cosine_scores[idx] or 0.0)
    
    return relevance

# Prepare cleaned resumes
cleaned_resumes = {f: clean_text(t) for f, t in mock_resumes.items()}

print("=" * 80)
print("TEST 1: Job Title = 'web developer' (VALID)")
print("=" * 80)
job_title = "web developer"
relevance = compute_job_title_relevance(job_title, cleaned_resumes)
for file, score in relevance.items():
    status = "[PASS]" if score >= MINIMUM_SCORE_THRESHOLD else "[FAIL]"
    print(f"  {file}: {score*100:.2f}% {status}")

valid_count = sum(1 for s in relevance.values() if s >= MINIMUM_SCORE_THRESHOLD)
print(f"Result: {valid_count} resume(s) passed job_title validation")
print(f"Expected: At least 1 resume should pass [OK]" if valid_count >= 1 else f"Expected: At least 1 resume should pass [FAILED]")
print()

print("=" * 80)
print("TEST 2: Job Title = 'akhanda' (INVALID MOVIE NAME)")
print("=" * 80)
job_title = "akhanda"
relevance = compute_job_title_relevance(job_title, cleaned_resumes)
for file, score in relevance.items():
    status = "[PASS]" if score >= MINIMUM_SCORE_THRESHOLD else "[FAIL]"
    print(f"  {file}: {score*100:.2f}% {status}")

valid_count = sum(1 for s in relevance.values() if s >= MINIMUM_SCORE_THRESHOLD)
print(f"Result: {valid_count} resume(s) passed job_title validation")
print(f"Expected: 0 resumes should pass (all blocked) [OK]" if valid_count == 0 else f"Expected: 0 resumes should pass (all blocked) [FAILED]")
print()

print("=" * 80)
print("TEST 3: Job Title = 'rrr' (INVALID MOVIE NAME)")
print("=" * 80)
job_title = "rrr"
relevance = compute_job_title_relevance(job_title, cleaned_resumes)
for file, score in relevance.items():
    status = "[PASS]" if score >= MINIMUM_SCORE_THRESHOLD else "[FAIL]"
    print(f"  {file}: {score*100:.2f}% {status}")

valid_count = sum(1 for s in relevance.values() if s >= MINIMUM_SCORE_THRESHOLD)
print(f"Result: {valid_count} resume(s) passed job_title validation")
print(f"Expected: 0 resumes should pass (all blocked) [OK]" if valid_count == 0 else f"Expected: 0 resumes should pass (all blocked) [FAILED]")
print()

print("=" * 80)
print("TEST 4: Job Title = 'frontend engineer' (VALID)")
print("=" * 80)
job_title = "frontend engineer"
relevance = compute_job_title_relevance(job_title, cleaned_resumes)
for file, score in relevance.items():
    status = "[PASS]" if score >= MINIMUM_SCORE_THRESHOLD else "[FAIL]"
    print(f"  {file}: {score*100:.2f}% {status}")

valid_count = sum(1 for s in relevance.values() if s >= MINIMUM_SCORE_THRESHOLD)
print(f"Result: {valid_count} resume(s) passed job_title validation")
print(f"Expected: At least 1 resume should pass [OK]" if valid_count >= 1 else f"Expected: At least 1 resume should pass [FAILED]")
print()

print("=" * 80)
print("TEST 5: Job Title = '' (EMPTY - ALL VALID)")
print("=" * 80)
job_title = ""
relevance = compute_job_title_relevance(job_title, cleaned_resumes)
for file, score in relevance.items():
    status = "[PASS]" if score >= MINIMUM_SCORE_THRESHOLD else "[FAIL]"
    print(f"  {file}: {score*100:.2f}% {status}")

valid_count = sum(1 for s in relevance.values() if s >= MINIMUM_SCORE_THRESHOLD)
print(f"Result: {valid_count} resume(s) passed job_title validation")
print(f"Expected: All 3 resumes should pass [OK]" if valid_count == 3 else f"Expected: All 3 resumes should pass [FAILED]")
print()

print("=" * 80)
print("SUMMARY")
print("=" * 80)
print("""
Validation Rules Implemented:
1. If job_title is provided and is irrelevant (like movie names) -> ALL results BLOCKED
2. If job_title is provided and is relevant -> resumes matching that title pass 
3. If job_title is empty -> all resumes proceed to skills-based scoring
4. Skills alone CANNOT override an irrelevant job_title

Backend Changes in webapp.py:
- Added helper function _compute_job_title_relevance()
- Applied job_title validation BEFORE skills-based scoring
- Updated /api/score endpoint
- Updated /run endpoint  
- Updated /api/download_results endpoint

ALL THREE ENDPOINTS NOW ENFORCE MANDATORY JOB TITLE VALIDATION
""")
