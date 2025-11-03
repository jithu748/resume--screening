# Resume Screening Project — Interview Cheat Sheet

Quick one-page summary of key points to review before interviews.

## One-Minute Pitch 🎯

"I built an automated resume screening system that uses NLP to match job requirements with candidate resumes. It extracts text from PDFs/Word docs, processes the content using TF-IDF vectorization, and ranks candidates using cosine similarity plus explicit skill matching. The tool is modular, supports automation via CLI, and includes features for exporting results and archiving top matches."

## Core Features & Components 🔧

- Text extraction: PDF (pdfminer.six) + DOCX (python-docx)
- Preprocessing: NLTK for tokenization, stopwords, normalization
- Vectorization: scikit-learn TF-IDF
- Scoring: cosine similarity + weighted skill presence
- Exports: CSV/Excel output, copy/zip top matches

## Technical Implementation 💻

Key files and responsibilities:
1. `extract_text.py`: PDF/DOCX parsing
2. `preprocess.py`: text cleaning pipeline
3. `vectorizer.py`: TF-IDF using sklearn
4. `similarity.py`: cosine similarity computation
5. `scorer.py`: business rules, skill matching
6. `main.py`: CLI + orchestration

## Design Decisions & Tradeoffs 🤔

1. Why TF-IDF?
   - Fast, memory-efficient (sparse matrices)
   - Interpretable results
   - Good baseline for structured text
   - Easy to tune and explain

2. Why modular design?
   - Separate concerns for testing
   - Easy to replace components
   - Clean pipeline: extract → clean → vectorize → score
   - Flexible output options

3. Error handling strategy:
   - Graceful PDF extraction failures
   - Auto-create missing directories
   - Optional Excel export (openpyxl)
   - CLI with sane defaults

## Scaling Considerations 📈

Current approach:
- Good for hundreds of resumes
- In-memory TF-IDF computation
- Sequential file processing

Scaling options:
1. Persist vectors to disk (joblib)
2. Multiprocessing for extraction
3. Batch processing for large sets
4. Consider ANN (FAISS) for huge scale

## Real-World Challenges 🌍

1. Document processing:
   - Scanned PDFs need OCR
   - Inconsistent resume formats
   - PDF extraction failures
   - Large batches of files

2. Search quality:
   - Skill variations/synonyms
   - Context-dependent terms
   - Balance similarity vs skills

## Extensions & Improvements 🚀

Already implemented:
- CLI automation support
- Export capabilities (CSV/Excel)
- Copy/zip top matches
- Automated setup (venv, NLTK data)

Planned improvements:
1. Vector persistence for speed
2. Parallel text extraction
3. FastAPI web interface
4. Optional dense embeddings

## Common Questions & Answers 💭

Q: How does it handle different file formats?
A: Uses specialized libraries (pdfminer.six, python-docx) with fallback handling.

Q: How do you ensure fair ranking?
A: Combine TF-IDF similarity with explicit skill checks, weights in scorer.py.

Q: What's the performance like?
A: Fast for hundreds of resumes; scales via persistence/batching.

Q: How would you deploy this?
A: Add FastAPI, use vector store, add monitoring.

## Key Metrics & Limits 📊

- Memory usage: O(n) with number of resumes
- Processing time: Linear + vectorization
- File size limits: Practical PDF/DOCX sizes
- Recommended batch size: ~500 files

## Best Practices 👌

1. Input preparation:
   - Convert scanned PDFs
   - Use consistent formats
   - Verify text extraction

2. Performance:
   - Batch large uploads
   - Monitor memory usage
   - Use persistence for repeat runs

3. Results:
   - Review top-N scores
   - Check extracted skills
   - Validate on known good matches
