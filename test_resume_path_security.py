
import asyncio
import shutil
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from data.src.webapp import (
    app,
    _create_session,
    _session_storage,
    _session_lock,
    view_resume,
)

client = TestClient(app)


@pytest.fixture
def test_session():
    session_id, session_dir = _create_session()
    try:
        yield session_id, session_dir
    finally:
        with _session_lock:
            _session_storage.pop(session_id, None)
        shutil.rmtree(session_dir, ignore_errors=True)


def test_valid_resume_can_be_viewed(test_session):
    session_id, session_dir = test_session
    resume = Path(session_dir) / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 test content")

    with _session_lock:
        _session_storage[session_id]["files"].append("resume.pdf")

    response = client.get(f"/view/{session_id}/resume.pdf")

    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 test content"


@pytest.mark.parametrize(
    "filename",
    [
        "../secret.pdf",
        "..\\secret.pdf",
        "nested/resume.pdf",
        "nested\\resume.pdf",
        "",
        ".",
        "..",
    ],
)
def test_unsafe_filename_is_rejected(test_session, filename):
    session_id, _ = test_session

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(view_resume(session_id, filename))

    assert exc_info.value.status_code == 403
