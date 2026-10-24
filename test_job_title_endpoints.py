from fastapi.testclient import TestClient
from data.src.webapp import app

client = TestClient(app)


def test_score_rejects_blank_job_title():
    response = client.post(
        "/api/score",
        json={
            "job_title": "   ",
            "skills": "Python",
            "session_id": "test-session",
        },
    )
    assert response.status_code == 400
    assert "job_title is required" in response.json()["error"]


def test_upload_form_rejects_blank_job_title():
    response = client.post(
        "/run",
        data={
            "job_title": "   ",
            "skills": "Python",
        },
    )
    assert response.status_code == 400
    assert "job_title is required" in response.json()["error"]


def test_download_rejects_blank_job_title():
    response = client.get(
        "/api/download_results",
        params={
            "job_title": "   ",
            "skills": "Python",
            "session_id": "test-session",
        },
    )
    assert response.status_code == 400
    assert "job_title is required" in str(response.json())
