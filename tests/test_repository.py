import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from voice_interviewer.models import InterviewSession
from voice_interviewer.repository import SessionNotFoundError, SQLiteInterviewRepository
from voice_interviewer.templates import default_template


class TrackingConnection:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.closed = False
        self.foreign_keys_enabled = (
            connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        )

    def close(self) -> None:
        self.closed = True
        self.connection.close()

    def __getattr__(self, name):
        return getattr(self.connection, name)


class TrackingRepository(SQLiteInterviewRepository):
    def __init__(self, path) -> None:
        self.connections: list[TrackingConnection] = []
        super().__init__(path)

    def _connect(self):
        connection = TrackingConnection(super()._connect())
        self.connections.append(connection)
        return connection


def make_session(session_id: str = "session-1") -> InterviewSession:
    return InterviewSession(
        id=session_id,
        template=default_template(),
        language="zh-CN",
        created_at="2026-08-14T00:00:00+00:00",
    )


def test_repository_exports_session_turns_and_facts(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")
    repository.create_session(make_session())
    repository.add_turn("session-1", "我每周购买一次", "您通常购买什么？")
    repository.save_facts("session-1", {"current_behavior": "每周购买一次"})

    exported = repository.export_session("session-1")

    assert exported["session"]["id"] == "session-1"
    assert exported["turns"][0]["user_text"] == "我每周购买一次"
    assert exported["facts"] == {"current_behavior": "每周购买一次"}


def test_missing_session_returns_none(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")

    assert repository.get_session("missing") is None
    assert repository.export_session("missing") is None


def test_repository_restores_template_and_turn_order(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")
    session = make_session()
    repository.create_session(session)
    repository.add_turn("session-1", "第一句", "第一个问题")
    repository.add_turn("session-1", "第二句", "第二个问题")

    restored = repository.get_session("session-1")
    exported = repository.export_session("session-1")

    assert restored == session
    assert [turn["user_text"] for turn in exported["turns"]] == ["第一句", "第二句"]


def test_save_facts_replaces_existing_field_value(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")
    repository.create_session(make_session())
    repository.save_facts("session-1", {"current_behavior": "每周一次", "needs": "省时"})
    repository.save_facts("session-1", {"current_behavior": "每天一次"})

    assert repository.export_session("session-1")["facts"] == {
        "current_behavior": "每天一次",
        "needs": "省时",
    }


def test_connections_enable_foreign_keys_and_close_after_use(tmp_path):
    repository = TrackingRepository(tmp_path / "interviews.sqlite3")
    repository.create_session(make_session())

    assert repository.connections
    assert all(connection.foreign_keys_enabled for connection in repository.connections)
    assert all(connection.closed for connection in repository.connections)


def test_unknown_session_writes_raise_domain_error_without_orphans(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")

    with pytest.raises(SessionNotFoundError):
        repository.add_turn("missing", "user", "interviewer")
    with pytest.raises(SessionNotFoundError):
        repository.save_facts("missing", {"needs": "speed"})

    repository.create_session(make_session("missing"))
    exported = repository.export_session("missing")

    assert exported["turns"] == []
    assert exported["facts"] == {}


def test_concurrent_add_turns_keep_every_turn_and_sequence(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")
    repository.create_session(make_session())

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [
            executor.submit(repository.add_turn, "session-1", str(index), "reply")
            for index in range(32)
        ]
        for future in futures:
            future.result()

    turns = repository.export_session("session-1")["turns"]
    assert [turn["sequence"] for turn in turns] == list(range(1, 33))
    assert {turn["user_text"] for turn in turns} == {str(index) for index in range(32)}


def test_save_reply_persists_turn_and_facts_together(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")
    repository.create_session(make_session())

    repository.save_reply("session-1", "user", "interviewer", {"needs": "speed"})

    exported = repository.export_session("session-1")
    assert exported["turns"] == [
        {"sequence": 1, "user_text": "user", "interviewer_text": "interviewer"}
    ]
    assert exported["facts"] == {"needs": "speed"}


def test_save_reply_updates_status_and_completed_at_atomically(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")
    repository.create_session(make_session())

    repository.save_reply(
        "session-1",
        "user",
        "interviewer",
        {"needs": "speed"},
        status="complete",
        completed_at="2026-08-14T01:02:03+00:00",
    )

    session = repository.get_session("session-1")
    assert session.status == "complete"
    assert session.completed_at == "2026-08-14T01:02:03+00:00"


def test_save_reply_keeps_completed_at_unchanged_for_noncomplete_status(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")
    session = make_session()
    session.status = "complete"
    session.completed_at = "2026-08-14T01:02:03+00:00"
    repository.create_session(session)

    repository.save_reply(
        "session-1",
        "user",
        "interviewer",
        {},
        status="awaiting_confirmation",
        completed_at="2026-08-14T04:05:06+00:00",
    )

    restored = repository.get_session("session-1")
    assert restored.status == "awaiting_confirmation"
    assert restored.completed_at == "2026-08-14T01:02:03+00:00"


def test_save_reply_rolls_back_turn_and_facts_when_a_fact_write_fails(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")
    repository.create_session(make_session())
    repository.save_facts("session-1", {"needs": "old"})

    with pytest.raises(sqlite3.IntegrityError):
        repository.save_reply(
            "session-1",
            "user",
            "interviewer",
            {"needs": "new", "broken": None},  # type: ignore[dict-item]
            status="complete",
            completed_at="2026-08-14T01:02:03+00:00",
        )

    exported = repository.export_session("session-1")
    assert exported["turns"] == []
    assert exported["facts"] == {"needs": "old"}
    restored = repository.get_session("session-1")
    assert restored.status == "active"
    assert restored.completed_at is None
