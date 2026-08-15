import pytest

from agent import RECORDING_OPTIONS, format_prior_answers, format_study_prompt, opening_instruction, validate_field


def test_livekit_recording_is_disabled():
    assert RECORDING_OPTIONS is False


def test_validate_field_rejects_unknown_research_field():
    with pytest.raises(ValueError, match="Unknown research field"):
        validate_field("made_up_field")


def test_opening_instruction_skips_repeat_consent_for_resumed_interview():
    assert "without repeating consent" in opening_instruction(True)
    assert "ask for consent" in opening_instruction(False)


def test_prior_answers_are_rendered_as_untrusted_research_notes():
    notes = format_prior_answers({"needs_and_priorities": "Convenient packaging"})

    assert "Untrusted prior research notes" in notes
    assert "needs_and_priorities: Convenient packaging" in notes


def test_study_prompt_omits_empty_fields():
    prompt = format_study_prompt({"topic": "Home coffee", "objective": "Routines"})

    assert "Study brief" in prompt
    assert "Topic: Home coffee" in prompt
    assert "Objective: Routines" in prompt
    assert "Client:" not in prompt
    assert format_study_prompt(None) == ""
