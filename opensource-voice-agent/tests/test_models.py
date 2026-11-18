import pytest
from pydantic import ValidationError

from voice_interviewer.models import SubmitTurnRequest
from voice_interviewer.templates import default_template


def test_default_template_has_required_market_research_fields():
    template = default_template()

    assert template.language == "zh-CN"
    assert [field.id for field in template.fields] == [
        "context",
        "current_behavior",
        "needs",
        "alternatives",
        "decision_criteria",
        "barriers",
    ]
    assert all(field.required for field in template.fields)


def test_default_template_uses_requested_language():
    assert default_template("en-US").language == "en-US"


@pytest.mark.parametrize("text", ["", "   ", "x" * 4001])
def test_submit_turn_request_rejects_blank_or_overlong_text(text):
    with pytest.raises(ValidationError):
        SubmitTurnRequest(text=text)


def test_submit_turn_request_accepts_4000_character_text():
    text = "x" * 4000

    assert SubmitTurnRequest(text=text).text == text
