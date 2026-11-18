import json

import pytest
from fastapi.testclient import TestClient

from voice_interviewer.api import create_app
from voice_interviewer.llm import LLMResponseError, LLMUnavailableError, ScriptedLLM
from voice_interviewer.repository import SQLiteInterviewRepository
from voice_interviewer.service import InterviewCompleteError, InterviewService


def make_service(tmp_path, responses: list[str]) -> InterviewService:
    return InterviewService(
        SQLiteInterviewRepository(tmp_path / "db.sqlite3"), ScriptedLLM(responses)
    )


class ExportOnlyService:
    __slots__ = ()

    def export(self, session_id: str) -> dict[str, object]:
        return {
            "session": {"id": session_id},
            "turns": [],
            "facts": {},
        }


def test_api_reads_and_exports_through_public_service_export():
    client = TestClient(create_app(ExportOnlyService()))

    read = client.get("/sessions/session-id")
    exported = client.get("/sessions/session-id/export")

    expected = {"session": {"id": "session-id"}, "turns": [], "facts": {}}
    assert read.status_code == 200
    assert read.json() == expected
    assert exported.status_code == 200
    assert exported.json() == expected


def test_api_creates_submits_reads_and_exports_session(tmp_path):
    service = make_service(
        tmp_path,
        [
            json.dumps(
                {
                    "facts": {"context": "个人使用"},
                    "interviewer_text": "您多久购买一次？",
                    "complete": False,
                }
            )
        ],
    )
    client = TestClient(create_app(service))

    created = client.post("/sessions", json={"language": "zh-CN"})
    session_id = created.json()["session_id"]
    replied = client.post(f"/sessions/{session_id}/turns", json={"text": "我为自己购买"})
    read = client.get(f"/sessions/{session_id}")
    exported = client.get(f"/sessions/{session_id}/export")

    assert created.status_code == 201
    assert created.json()["status"] == "active"
    assert replied.status_code == 200
    assert replied.json()["facts"] == {"context": "个人使用"}
    assert read.status_code == 200
    assert read.json() == exported.json()
    assert exported.status_code == 200
    assert exported.json()["facts"] == {"context": "个人使用"}
    assert exported.json()["turns"][0]["user_text"] == "我为自己购买"


def test_api_start_works_without_llm_and_reply_returns_503(tmp_path):
    client = TestClient(
        create_app(InterviewService(SQLiteInterviewRepository(tmp_path / "db.sqlite3")))
    )

    created = client.post("/sessions", json={"language": "zh-CN"})
    response = client.post(
        f"/sessions/{created.json()['session_id']}/turns", json={"text": "回答"}
    )

    assert created.status_code == 201
    assert response.status_code == 503
    assert response.json() == {"detail": "LLM service unavailable"}


@pytest.mark.parametrize("text", ["   ", "x" * 4001])
def test_api_rejects_invalid_turn_text_with_422(tmp_path, text):
    client = TestClient(create_app(make_service(tmp_path, [])))
    session_id = client.post("/sessions", json={}).json()["session_id"]

    response = client.post(f"/sessions/{session_id}/turns", json={"text": text})

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_api_maps_missing_session_to_404(tmp_path):
    client = TestClient(create_app(make_service(tmp_path, [])))

    get_response = client.get("/sessions/missing")
    post_response = client.post("/sessions/missing/turns", json={"text": "回答"})

    assert get_response.status_code == 404
    assert get_response.json() == {"detail": "Interview session not found"}
    assert post_response.status_code == 404
    assert post_response.json() == {"detail": "Interview session not found"}


class ErrorService:
    def __init__(self, error: Exception):
        self.error = error

    def reply(self, session_id: str, text: str):
        raise self.error


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (InterviewCompleteError("secret session id"), 409, "Interview is already complete"),
        (LLMResponseError("secret-api-key upstream body"), 502, "LLM response invalid"),
        (LLMUnavailableError("secret-api-key upstream body"), 503, "LLM service unavailable"),
    ],
)
def test_api_maps_domain_errors_to_safe_responses(error, status_code, detail):
    client = TestClient(create_app(ErrorService(error)))

    response = client.post("/sessions/session-id/turns", json={"text": "回答"})

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert "secret-api-key" not in response.text
    assert "upstream body" not in response.text


def test_default_app_uses_database_and_llm_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "nested" / "interviews.sqlite3"))
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    client = TestClient(create_app())

    response = client.post("/sessions", json={})

    assert response.status_code == 201
    assert (tmp_path / "nested" / "interviews.sqlite3").exists()
