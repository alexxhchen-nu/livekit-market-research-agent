import os

from fastapi.testclient import TestClient

from app.api import create_app


SECRET = "test-secret"
HEADERS = {"X-Research-Secret": SECRET}


def client_for(tmp_path):
    return TestClient(create_app(tmp_path / "research.db", SECRET))


def test_answers_require_consent(tmp_path):
    client = client_for(tmp_path)

    response = client.post(
        "/api/answers",
        headers=HEADERS,
        json={
            "interview_id": "interview-1",
            "consent_status": "not_asked",
            "field": "needs_and_priorities",
            "value": "Convenient packaging",
        },
    )

    assert response.status_code == 409
    assert client.get("/api/interviews/interview-1", headers=HEADERS).status_code == 404


def test_answers_require_persisted_consent(tmp_path):
    client = client_for(tmp_path)
    answer = {
        "interview_id": "interview-1",
        "consent_status": "consented",
        "field": "needs_and_priorities",
        "value": "Convenient packaging",
    }
    consent = {
        "interview_id": "interview-1",
        "consent_status": "consented",
        "field": "consent_status",
        "value": "consented",
    }

    assert client.post("/api/answers", headers=HEADERS, json=answer).status_code == 409
    assert client.post("/api/answers", headers=HEADERS, json=consent).status_code == 201
    assert client.post("/api/answers", headers=HEADERS, json=answer).status_code == 201
    response = client.get("/api/interviews/interview-1", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["answers"] == {
        "consent_status": "consented",
        "needs_and_priorities": "Convenient packaging",
    }


def test_unknown_field_is_rejected(tmp_path):
    client = client_for(tmp_path)
    response = client.post(
        "/api/answers",
        headers=HEADERS,
        json={
            "interview_id": "interview-1",
            "consent_status": "consented",
            "field": "unapproved_field",
            "value": "value",
        },
    )

    assert response.status_code == 422


def test_frontend_is_served(tmp_path):
    response = client_for(tmp_path).get("/")

    assert response.status_code == 200
    assert "Research interview" in response.text


def test_token_persists_open_ended_study_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "very-secret-at-least-thirty-two-characters")
    client = client_for(tmp_path)
    study = {
        "topic": "Home coffee routines",
        "client_context": "A small appliance client",
        "target_audience": "People who brew coffee at home",
        "objective": "Understand morning routine pain points",
        "questions": "What slows down your morning?\nWhat would you change?",
    }

    response = client.post("/api/token", json={"language": "Chinese", "study": study})

    assert response.status_code == 200
    assert response.json()["url"] == "wss://example.livekit.cloud"
    assert response.json()["interview_id"]
    assert "very-secret-at-least-thirty-two-characters" not in response.text

    record = client.get(f"/api/interviews/{response.json()['interview_id']}", headers=HEADERS)
    assert record.json()["study"] == study
