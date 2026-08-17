from pathlib import Path

from fastapi.testclient import TestClient

import voice_interviewer
from voice_interviewer.api import create_app


WEB = Path(voice_interviewer.__file__).with_name("web")
APP_JS = WEB / "app.js"


def test_web_page_is_served_outside_repository_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(object()))

    response = client.get("/")

    assert response.status_code == 200
    assert "<title>语音访谈</title>" in response.text


def test_web_root_assets_are_served(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(object()))

    for path in ("/app.js", "/styles.css"):
        assert client.get(path).status_code == 200


def test_web_client_uses_documented_session_endpoints():
    script = APP_JS.read_text()

    assert 'fetch("/sessions"' in script
    assert '`/sessions/${encodeURIComponent(sessionId)}/turns`' in script
    assert 'SpeechRecognition' in script or 'webkitSpeechRecognition' in script
    assert "speechSynthesis.cancel()" in script
    assert "speechSynthesis.speak" in script


def test_web_client_stops_active_recognition_before_start_and_submit():
    script = APP_JS.read_text()

    assert script.count("if (recognizing) recognition.stop();") == 2


def test_web_client_renders_user_text_without_html_injection():
    script = APP_JS.read_text()

    assert "textContent" in script
    assert "innerHTML" not in script


def test_web_client_disables_turn_controls_after_completion_and_allows_restart():
    script = APP_JS.read_text()

    assert 'result.status === "complete"' in script
    assert "submitButton.disabled = true" in script
    assert "transcript.replaceChildren()" in script
    assert "startButton.disabled = false" in script
    assert "if (!completed)" in script

