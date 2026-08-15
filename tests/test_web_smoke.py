import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def wait_for_server(url: str, timeout: float = 15) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"Server did not start at {url}")


def test_home_page_renders_study_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_DATABASE_PATH", str(tmp_path / "research.db"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.api:app", "--host", "127.0.0.1", "--port", "8010"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_for_server("http://127.0.0.1:8010/")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("http://127.0.0.1:8010/")
            page.wait_for_load_state("networkidle")
            assert page.locator("#study-topic").is_visible()
            assert page.locator("#start").is_enabled()
            assert page.locator("#live-interview").count() == 1
            assert page.locator("#live-interview").is_hidden()
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_live_interview_view_has_turn_and_transcript_controls(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_DATABASE_PATH", str(tmp_path / "research.db"))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content((ROOT / "web" / "index.html").read_text())
        assert page.locator("#live-interview").count() == 1
        assert page.locator("#turn-status").count() == 1
        assert page.locator("#transcript").count() == 1
        assert page.locator("#recording-notice").count() == 1
        browser.close()
