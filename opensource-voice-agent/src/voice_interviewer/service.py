import json
from datetime import datetime, timezone
from uuid import uuid4

from .llm import InterviewLLM, LLMResponseError, LLMUnavailableError
from .models import InterviewSession, TurnResult
from .repository import SessionNotFoundError, SQLiteInterviewRepository
from .templates import default_template

MAX_TEXT_LENGTH = 4000


class InterviewCompleteError(Exception):
    pass


def _clean_text(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("text must not be blank")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError("text must be 4000 characters or fewer")
    return text


class InterviewService:
    def __init__(
        self, repository: SQLiteInterviewRepository, llm: InterviewLLM | None = None
    ):
        self._repository = repository
        self._llm = llm

    def start(self, language: str) -> tuple[InterviewSession, TurnResult]:
        template = default_template(language)
        session = InterviewSession(
            id=str(uuid4()),
            template=template,
            language=language,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._repository.create_session(session)
        missing_fields = [field.id for field in template.fields if field.required]
        first_field = template.fields[0]
        return session, TurnResult(
            interviewer_text=f"请介绍一下您的{first_field.label}。",
            status="active",
            missing_fields=missing_fields,
        )

    def export(self, session_id: str) -> dict[str, object]:
        exported = self._repository.export_session(session_id)
        if exported is None:
            raise SessionNotFoundError(session_id)
        return exported

    def reply(self, session_id: str, text: str) -> TurnResult:
        text = _clean_text(text)
        session = self._repository.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        if session.status == "complete":
            raise InterviewCompleteError(session_id)
        if self._llm is None:
            raise LLMUnavailableError("LLM service is unavailable")

        exported = self._repository.export_session(session_id)
        assert exported is not None
        response = self._parse_response(self._llm.complete(self._prompt(session, exported, text)))
        allowed_fields = {field.id for field in session.template.fields}
        facts = {
            field_id: value
            for field_id, value in response["facts"].items()
            if field_id in allowed_fields
        }
        facts = {
            field_id: self._clean_llm_text(value, "fact values")
            for field_id, value in facts.items()
        }
        interviewer_text = self._clean_llm_text(
            response["interviewer_text"], "interviewer_text"
        )

        current_facts = exported["facts"]
        assert isinstance(current_facts, dict)
        all_facts = {**current_facts, **facts}
        missing_fields = [
            field.id
            for field in session.template.fields
            if field.required and not all_facts.get(field.id, "").strip()
        ]
        if missing_fields:
            status = "active"
        elif session.status == "awaiting_confirmation" and response["complete"]:
            status = "complete"
        else:
            status = "awaiting_confirmation"
        completed_at = (
            datetime.now(timezone.utc).isoformat() if status == "complete" else None
        )
        self._repository.save_reply(
            session_id,
            text,
            interviewer_text,
            facts,
            status=status,
            completed_at=completed_at,
        )
        return TurnResult(
            interviewer_text=interviewer_text,
            status=status,
            missing_fields=missing_fields,
            facts=all_facts,
        )

    @staticmethod
    def _clean_llm_text(value: object, name: str) -> str:
        if not isinstance(value, str):
            raise LLMResponseError(f"LLM {name} must be strings")
        value = value.strip()
        if not value:
            detail = "must not be blank" if name == "interviewer_text" else "must be nonblank strings"
            raise LLMResponseError(f"LLM {name} {detail}")
        if len(value) > MAX_TEXT_LENGTH:
            raise LLMResponseError(
                f"LLM {name} must be {MAX_TEXT_LENGTH} characters or fewer"
            )
        return value

    @staticmethod
    def _parse_response(response: str) -> dict[str, object]:
        try:
            parsed = json.loads(response)
        except (TypeError, json.JSONDecodeError) as error:
            raise LLMResponseError("LLM response must be valid JSON") from error
        if (
            not isinstance(parsed, dict)
            or not isinstance(parsed.get("facts"), dict)
            or not isinstance(parsed.get("interviewer_text"), str)
            or not isinstance(parsed.get("complete"), bool)
        ):
            raise LLMResponseError(
                "LLM response must contain facts, interviewer_text, and complete"
            )
        return parsed

    @staticmethod
    def _prompt(
        session: InterviewSession, exported: dict[str, object], text: str
    ) -> str:
        return (
            "TASK INSTRUCTIONS\n"
            "Return JSON only with facts (object), interviewer_text (string), and "
            "complete (boolean).\n\n"
            "UNTRUSTED INTERVIEW DATA\n"
            + json.dumps(
                {
                    "template": session.template.model_dump(mode="json"),
                    "current_facts": exported["facts"],
                    "history": exported["turns"],
                    "user_text": text,
                },
                ensure_ascii=False,
            )
        )
