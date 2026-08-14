import json
import os
import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from livekit import api


FIELDS = {
    "consent_status",
    "preferred_language",
    "interview_status",
    "legal_age_eligibility",
    "broad_region",
    "participant_profile",
    "product_category",
    "current_behavior",
    "usage_frequency",
    "usage_occasions",
    "current_products_or_brands",
    "needs_and_priorities",
    "decision_criteria",
    "preferred_features",
    "pain_points_and_barriers",
    "alternatives_considered",
    "price_sensitivity",
    "purchase_channel",
    "unmet_needs",
    "purchase_intent",
    "key_quotes",
    "open_questions",
    "follow_up_permission",
    "research_summary",
}


class Answer(BaseModel):
    interview_id: str = Field(min_length=1, max_length=100)
    consent_status: str
    field: str
    value: str = Field(min_length=1, max_length=4000)


class StudyConfig(BaseModel):
    topic: str = Field(default="Open research conversation", min_length=1, max_length=300)
    client_context: str = Field(default="", max_length=2000)
    target_audience: str = Field(default="", max_length=1000)
    objective: str = Field(default="Understand the participant's perspective.", min_length=1, max_length=2000)
    questions: str = Field(default="", max_length=4000)


class TokenRequest(BaseModel):
    interview_id: str | None = Field(default=None, max_length=100)
    language: str = Field(default="English", pattern="^(English|Chinese|mixed)$")
    study: StudyConfig = Field(default_factory=StudyConfig)


def create_app(database_path: Path, research_secret: str) -> FastAPI:
    app = FastAPI()
    web_dir = Path(__file__).resolve().parent.parent / "web"

    def connection():
        database_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(database_path)
        db.execute(
            """CREATE TABLE IF NOT EXISTS answers (
                interview_id TEXT NOT NULL,
                field TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (interview_id, field)
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS studies (
                interview_id TEXT PRIMARY KEY,
                config TEXT NOT NULL
            )"""
        )
        return db

    def require_secret(value: str | None):
        if not value or not secrets.compare_digest(value, research_secret):
            raise HTTPException(401, "Unauthorized")

    @app.get("/")
    def index():
        return FileResponse(web_dir / "index.html")

    @app.get("/app.js")
    def javascript():
        return FileResponse(web_dir / "app.js", media_type="text/javascript")

    @app.get("/styles.css")
    def styles():
        return FileResponse(web_dir / "styles.css", media_type="text/css")

    @app.post("/api/answers", status_code=201)
    def save_answer(answer: Answer, x_research_secret: str | None = Header(default=None)):
        require_secret(x_research_secret)
        if answer.field not in FIELDS:
            raise HTTPException(422, "Unknown research field")

        with connection() as db:
            if answer.field != "consent_status":
                saved_consent = db.execute(
                    "SELECT value FROM answers WHERE interview_id = ? AND field = 'consent_status'",
                    (answer.interview_id,),
                ).fetchone()
                if not saved_consent or saved_consent[0] != "consented":
                    raise HTTPException(409, "Participant consent is required")
            db.execute(
                """INSERT INTO answers (interview_id, field, value)
                VALUES (?, ?, ?)
                ON CONFLICT(interview_id, field) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP""",
                (answer.interview_id, answer.field, answer.value),
            )
        return {"saved": answer.field}

    @app.get("/api/interviews/{interview_id}")
    def get_interview(interview_id: str, x_research_secret: str | None = Header(default=None)):
        require_secret(x_research_secret)
        with connection() as db:
            rows = db.execute(
                "SELECT field, value FROM answers WHERE interview_id = ?", (interview_id,)
            ).fetchall()
        with connection() as db:
            study = db.execute(
                "SELECT config FROM studies WHERE interview_id = ?", (interview_id,)
            ).fetchone()
        if not rows and not study:
            raise HTTPException(404, "Interview not found")
        return {
            "interview_id": interview_id,
            "study": json.loads(study[0]) if study else None,
            "answers": dict(rows),
        }

    @app.post("/api/token")
    def token(request: TokenRequest):
        livekit_url = os.environ.get("LIVEKIT_URL")
        livekit_key = os.environ.get("LIVEKIT_API_KEY")
        livekit_secret = os.environ.get("LIVEKIT_API_SECRET")
        agent_name = os.environ.get("LIVEKIT_AGENT_NAME", "market-research-agent")
        if not all((livekit_url, livekit_key, livekit_secret)):
            raise HTTPException(503, "LiveKit is not configured")

        interview_id = request.interview_id or str(uuid4())
        with connection() as db:
            existing_study = db.execute(
                "SELECT config FROM studies WHERE interview_id = ?", (interview_id,)
            ).fetchone()
            if not existing_study:
                db.execute(
                    "INSERT INTO studies (interview_id, config) VALUES (?, ?)",
                    (interview_id, request.study.model_dump_json()),
                )
        room = f"research-{interview_id}"
        metadata = json.dumps({"interview_id": interview_id, "language": request.language})
        room_config = api.RoomConfiguration(
            agents=[api.RoomAgentDispatch(agent_name=agent_name, metadata=metadata)]
        )
        token = (
            api.AccessToken(livekit_key, livekit_secret)
            .with_ttl(timedelta(minutes=30))
            .with_identity(f"participant-{uuid4().hex[:12]}")
            .with_name("Research participant")
            .with_metadata(metadata)
            .with_room_config(room_config)
            .with_grants(api.VideoGrants(room_join=True, room=room))
            .to_jwt()
        )
        return {
            "url": livekit_url,
            "token": token,
            "room": room,
            "interview_id": interview_id,
            "agent_name": agent_name,
        }

    return app


load_dotenv(".env")

app = create_app(
    Path(os.environ.get("RESEARCH_DATABASE_PATH", "data/research.db")),
    os.environ.get("RESEARCH_DATA_SECRET", "development-only-secret"),
)
