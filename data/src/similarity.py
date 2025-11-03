from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

def compute_cosine(vectors):
    job_vec = vectors[0]   # first is job description
    resume_vecs = vectors[1:]
    scores = cosine_similarity(job_vec, resume_vecs)
    return scores.flatten()
