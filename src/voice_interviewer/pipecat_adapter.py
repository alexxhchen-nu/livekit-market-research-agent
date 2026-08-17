from .service import InterviewService


def handle_transcript(
    service: InterviewService, session_id: str, transcript: str
) -> str:
    return service.reply(session_id, transcript).interviewer_text
