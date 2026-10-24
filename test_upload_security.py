import io
import stat
import zipfile

import pytest
from fastapi.testclient import TestClient

from data.src import webapp


client = TestClient(webapp.app)
PDF = b"%PDF-1.4\nsynthetic resume\n"


def make_docx() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return output.getvalue()


def make_zip(entries: list[tuple[str, bytes, int | None]]):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content, mode in entries:
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            if mode is not None:
                info.external_attr = mode << 16
            archive.writestr(info, content)
    return output.getvalue()


def end_session(response):
    session_id = response.json().get("session_id")
    if session_id:
        client.delete("/api/session", params={"session_id": session_id})


def test_valid_pdf_and_docx_uploads():
    response = client.post(
        "/api/upload",
        files=[
            ("files", ("resume.pdf", PDF, "application/pdf")),
            ("files", ("resume.docx", make_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ],
    )
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert set(response.json()["saved"]) == {"resume.pdf", "resume.docx"}
    end_session(response)


@pytest.mark.parametrize(
    "filename,content,expected_status",
    [
        ("empty.pdf", b"", 400),
        ("malformed.pdf", b"not a PDF", 400),
        ("malformed.docx", b"not a DOCX", 400),
        ("resume.txt", b"text", 415),
    ],
)
def test_invalid_and_unsupported_uploads_are_rejected(filename, content, expected_status):
    response = client.post("/api/upload", files={"files": (filename, content, "application/octet-stream")})
    assert response.status_code == expected_status
    assert "session_id" not in response.json()


def test_upload_size_limit_and_cleanup(monkeypatch):
    monkeypatch.setattr(webapp, "MAX_UPLOAD_SIZE_BYTES", len(PDF) - 1)
    before = set(webapp._session_storage)
    response = client.post("/api/upload", files={"files": ("resume.pdf", PDF, "application/pdf")})
    assert response.status_code == 413
    assert set(webapp._session_storage) == before


def test_total_upload_size_limit(monkeypatch):
    monkeypatch.setattr(webapp, "MAX_UPLOAD_TOTAL_BYTES", len(PDF) - 1)
    response = client.post("/api/upload", files={"files": ("resume.pdf", PDF, "application/pdf")})
    assert response.status_code == 413


def test_upload_file_count_limit(monkeypatch):
    monkeypatch.setattr(webapp, "MAX_UPLOAD_FILES", 1)
    response = client.post(
        "/api/upload",
        files=[
            ("files", ("one.pdf", PDF, "application/pdf")),
            ("files", ("two.pdf", PDF, "application/pdf")),
        ],
    )
    assert response.status_code == 413


@pytest.mark.parametrize("archive_bytes", [b"not a zip", b"PK\x03\x04incomplete"])
def test_malformed_zip_is_rejected_and_cleaned(archive_bytes):
    before = set(webapp._session_storage)
    response = client.post("/api/upload-zip", files={"file": ("resumes.zip", archive_bytes, "application/zip")})
    assert response.status_code == 400
    assert set(webapp._session_storage) == before


@pytest.mark.parametrize("member_name", ["../resume.pdf", "/resume.pdf", "C:/resume.pdf"])
def test_zip_path_traversal_and_absolute_paths_are_rejected(member_name):
    response = client.post(
        "/api/upload-zip",
        files={"file": ("resumes.zip", make_zip([(member_name, PDF, None)]), "application/zip")},
    )
    assert response.status_code == 400


def test_zip_duplicate_filenames_are_rejected():
    archive = make_zip([("first/resume.pdf", PDF, None), ("second/resume.pdf", PDF, None)])
    response = client.post("/api/upload-zip", files={"file": ("resumes.zip", archive, "application/zip")})
    assert response.status_code == 409


def test_zip_unsupported_and_malformed_resume_entries_are_rejected_and_cleaned():
    unsupported = client.post(
        "/api/upload-zip",
        files={"file": ("resumes.zip", make_zip([("notes.txt", b"text", None)]), "application/zip")},
    )
    assert unsupported.status_code == 415

    before = set(webapp._session_storage)
    malformed_resume = client.post(
        "/api/upload-zip",
        files={"file": ("resumes.zip", make_zip([("resume.pdf", b"not a PDF", None)]), "application/zip")},
    )
    assert malformed_resume.status_code == 400
    assert set(webapp._session_storage) == before


def test_zip_symlink_is_rejected():
    symlink_mode = stat.S_IFLNK | 0o777
    archive = make_zip([("resume.pdf", b"target", symlink_mode)])
    response = client.post("/api/upload-zip", files={"file": ("resumes.zip", archive, "application/zip")})
    assert response.status_code == 400


def test_zip_entry_count_limit(monkeypatch):
    monkeypatch.setattr(webapp, "ZIP_MAX_ENTRIES", 1)
    archive = make_zip([("one.pdf", PDF, None), ("two.pdf", PDF, None)])
    response = client.post("/api/upload-zip", files={"file": ("resumes.zip", archive, "application/zip")})
    assert response.status_code == 413


def test_zip_individual_and_total_extraction_limits(monkeypatch):
    monkeypatch.setattr(webapp, "ZIP_MAX_FILE_SIZE_BYTES", len(PDF) - 1)
    response = client.post("/api/upload-zip", files={"file": ("resumes.zip", make_zip([("resume.pdf", PDF, None)]), "application/zip")})
    assert response.status_code == 413

    monkeypatch.setattr(webapp, "ZIP_MAX_FILE_SIZE_BYTES", 1024)
    monkeypatch.setattr(webapp, "ZIP_MAX_TOTAL_EXTRACTED_BYTES", len(PDF))
    archive = make_zip([("one.pdf", PDF, None), ("two.pdf", PDF, None)])
    response = client.post("/api/upload-zip", files={"file": ("resumes.zip", archive, "application/zip")})
    assert response.status_code == 413


def test_zip_archive_size_and_compression_ratio_limits(monkeypatch):
    archive = make_zip([("resume.pdf", PDF, None)])
    monkeypatch.setattr(webapp, "ZIP_MAX_ARCHIVE_SIZE_BYTES", len(archive) - 1)
    response = client.post("/api/upload-zip", files={"file": ("resumes.zip", archive, "application/zip")})
    assert response.status_code == 413

    monkeypatch.setattr(webapp, "ZIP_MAX_ARCHIVE_SIZE_BYTES", 1024 * 1024)
    monkeypatch.setattr(webapp, "ZIP_MAX_COMPRESSION_RATIO", 1.0)
    compressible_pdf = b"%PDF-1.4\n" + (b"A" * 4096)
    ratio_archive = make_zip([("resume.pdf", compressible_pdf, None)])
    response = client.post("/api/upload-zip", files={"file": ("resumes.zip", ratio_archive, "application/zip")})
    assert response.status_code == 413


def test_run_endpoint_uses_the_same_upload_validation(monkeypatch):
    monkeypatch.setattr(webapp, "load_resumes", lambda resume_folder: {"resume.pdf": "Software Engineer Python"})
    monkeypatch.setattr(webapp, "clean_text", lambda value: value)
    monkeypatch.setattr(webapp, "_compute_job_title_relevance", lambda title, resumes: {name: 1.0 for name in resumes})
    monkeypatch.setattr(webapp, "get_tfidf_vectors", lambda description, resumes: [1.0])
    monkeypatch.setattr(webapp, "compute_cosine", lambda vectors: [1.0])
    monkeypatch.setattr(webapp, "score_resume", lambda text, skills, similarity: {"score": 1.0, "matched_skills": [], "missing_skills": []})

    response = client.post(
        "/run",
        data={"job_title": "Software Engineer", "skills": "Python"},
        files={"resume": ("resume.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["file"] == "resume.pdf"

    response = client.post(
        "/run",
        data={"job_title": "Software Engineer", "skills": "Python"},
        files={"resume_zip": ("resumes.zip", make_zip([("resume.pdf", PDF, None)]), "application/zip")},
    )
    assert response.status_code == 200
