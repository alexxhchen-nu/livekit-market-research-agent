import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .llm import LLMResponseError, LLMUnavailableError, OpenAICompatibleLLM
from .models import CreateSessionRequest, SubmitTurnRequest
from .repository import SessionNotFoundError, SQLiteInterviewRepository
from .service import InterviewCompleteError, InterviewService


def _default_service() -> InterviewService:
    database_path = Path(os.getenv("DATABASE_PATH", "data/interviews.sqlite3"))
    database_path.parent.mkdir(parents=True, exist_ok=True)

    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    llm = (
        OpenAICompatibleLLM(base_url, api_key, model)
        if base_url and api_key and model
        else None
    )
    return InterviewService(SQLiteInterviewRepository(database_path), llm)


def create_app(service: InterviewService | None = None) -> FastAPI:
    interview_service = service if service is not None else _default_service()
    application = FastAPI(title="Open Source Voice Interviewer")

    @application.exception_handler(RequestValidationError)
    def handle_validation_error(request, exc):
        return JSONResponse(status_code=422, content={"detail": "Invalid request"})

    @application.exception_handler(SessionNotFoundError)
    def handle_session_not_found(request, exc):
        return JSONResponse(
            status_code=404, content={"detail": "Interview session not found"}
        )

    @application.exception_handler(InterviewCompleteError)
    def handle_interview_complete(request, exc):
        return JSONResponse(
            status_code=409, content={"detail": "Interview is already complete"}
        )

    @application.exception_handler(LLMResponseError)
    def handle_llm_response_error(request, exc):
        return JSONResponse(status_code=502, content={"detail": "LLM response invalid"})

    @application.exception_handler(LLMUnavailableError)
    def handle_llm_unavailable(request, exc):
        return JSONResponse(
            status_code=503, content={"detail": "LLM service unavailable"}
        )

    @application.post("/sessions", status_code=201)
    def create_session(request: CreateSessionRequest):
        session, result = interview_service.start(request.language)
        return {"session_id": session.id, **result.model_dump(mode="json")}

    @application.post("/sessions/{session_id}/turns")
    def submit_turn(session_id: str, request: SubmitTurnRequest):
        return interview_service.reply(session_id, request.text).model_dump(mode="json")

    @application.get("/sessions/{session_id}")
    def get_session(session_id: str):
        return interview_service.export(session_id)

    @application.get("/sessions/{session_id}/export")
    def export_session(session_id: str):
        return interview_service.export(session_id)

    application.mount(
        "/",
        StaticFiles(
            directory=Path(__file__).with_name("web"),
            html=True,
        ),
        name="web",
    )
    return application


app = create_app()
