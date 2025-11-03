from sklearn.feature_extraction.text import TfidfVectorizer

def get_tfidf_vectors(job_desc, resumes):
    texts = [job_desc] + list(resumes.values())
    vectorizer = TfidfVectorizer()
    vectors = vectorizer.fit_transform(texts)
    return vectors
