from voice_interviewer.models import TurnResult
from voice_interviewer.pipecat_adapter import handle_transcript


class FakeService:
    def __init__(self):
        self.received = []

    def reply(self, session_id: str, text: str) -> TurnResult:
        self.received.append((session_id, text))
        return TurnResult(
            interviewer_text="下一题是什么？",
            status="active",
            missing_fields=[],
        )


def test_pipecat_adapter_returns_only_spoken_interviewer_text():
    service = FakeService()

    assert handle_transcript(service, "session-1", "我的回答") == "下一题是什么？"
    assert service.received == [("session-1", "我的回答")]
