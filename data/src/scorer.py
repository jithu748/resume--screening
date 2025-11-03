def score_resume(resume_text, job_skills, similarity_score):
    resume_words = set(resume_text.split())
    required_skills = set(job_skills.lower().split(","))
    skill_match = len(resume_words.intersection(required_skills)) / len(required_skills)
    
    final_score = 0.7 * similarity_score + 0.3 * skill_match
    return round(final_score, 3)
