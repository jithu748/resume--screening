import os
from docx import Document
from pdfminer.high_level import extract_text

def extract_from_pdf(pdf_path):
    try:
        return extract_text(pdf_path)
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
        return ""

def extract_from_docx(docx_path):
    try:
        doc = Document(docx_path)
        return " ".join([para.text for para in doc.paragraphs])
    except Exception as e:
        print(f"Error reading {docx_path}: {e}")
        return ""

def load_resumes(resume_folder="../resume_uploads/"):
    resumes = {}
    for file in os.listdir(resume_folder):
        path = os.path.join(resume_folder, file)
        if file.endswith(".pdf"):
            text = extract_from_pdf(path)
        elif file.endswith(".docx"):
            text = extract_from_docx(path)
        else:
            continue
        resumes[file] = text
    return resumes
