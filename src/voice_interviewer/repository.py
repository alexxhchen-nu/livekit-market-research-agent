import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import InterviewSession


class SessionNotFoundError(Exception):
    pass


class SQLiteInterviewRepository:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    template_json TEXT NOT NULL,
                    language TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS turns (
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    user_text TEXT NOT NULL,
                    interviewer_text TEXT NOT NULL,
                    PRIMARY KEY (session_id, sequence),
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS facts (
                    session_id TEXT NOT NULL,
                    field_id TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (session_id, field_id),
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );
                """
            )

    def create_session(self, session: InterviewSession) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO sessions
                    (id, template_json, language, status, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.template.model_dump_json(),
                    session.language,
                    session.status,
                    session.created_at,
                    session.completed_at,
                ),
            )

    def get_session(self, session_id: str) -> InterviewSession | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, template_json, language, status, created_at, completed_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return InterviewSession(
            id=row["id"],
            template=json.loads(row["template_json"]),
            language=row["language"],
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    def _require_session(self, connection: sqlite3.Connection, session_id: str) -> None:
        if connection.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
        ).fetchone() is None:
            raise SessionNotFoundError(session_id)

    def _add_turn(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        user_text: str,
        interviewer_text: str,
    ) -> None:
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM turns WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO turns (session_id, sequence, user_text, interviewer_text)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, sequence, user_text, interviewer_text),
        )

    def _save_facts(
        self, connection: sqlite3.Connection, session_id: str, facts: dict[str, str]
    ) -> None:
        connection.executemany(
            """
            INSERT INTO facts (session_id, field_id, value)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id, field_id) DO UPDATE SET value = excluded.value
            """,
            ((session_id, field_id, value) for field_id, value in facts.items()),
        )

    def add_turn(self, session_id: str, user_text: str, interviewer_text: str) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_session(connection, session_id)
            self._add_turn(connection, session_id, user_text, interviewer_text)

    def save_facts(self, session_id: str, facts: dict[str, str]) -> None:
        with self._connection() as connection:
            self._require_session(connection, session_id)
            self._save_facts(connection, session_id, facts)

    def save_reply(
        self,
        session_id: str,
        user_text: str,
        interviewer_text: str,
        facts: dict[str, str],
        *,
        status: str | None = None,
        completed_at: str | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_session(connection, session_id)
            self._add_turn(connection, session_id, user_text, interviewer_text)
            self._save_facts(connection, session_id, facts)
            if status is not None:
                connection.execute(
                    """
                    UPDATE sessions
                    SET status = ?,
                        completed_at = CASE
                            WHEN ? = 'complete' THEN ?
                            ELSE completed_at
                        END
                    WHERE id = ?
                    """,
                    (status, status, completed_at, session_id),
                )

    def export_session(self, session_id: str) -> dict[str, object] | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        with self._connection() as connection:
            turns = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT sequence, user_text, interviewer_text
                    FROM turns
                    WHERE session_id = ?
                    ORDER BY sequence
                    """,
                    (session_id,),
                )
            ]
            facts = {
                row["field_id"]: row["value"]
                for row in connection.execute(
                    """
                    SELECT field_id, value
                    FROM facts
                    WHERE session_id = ?
                    ORDER BY field_id
                    """,
                    (session_id,),
                )
            }
        return {
            "session": session.model_dump(mode="json"),
            "turns": turns,
            "facts": facts,
        }
