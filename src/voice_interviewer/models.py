from pydantic import BaseModel, Field, field_validator


class InterviewField(BaseModel):
    id: str
    label: str
    purpose: str
    required: bool = True


class InterviewTemplate(BaseModel):
    id: str = "general-market-research"
    title: str
    language: str = "zh-CN"
    objective: str
    fields: list[InterviewField]


class InterviewSession(BaseModel):
    id: str
    template: InterviewTemplate
    language: str
    status: str = "active"
    created_at: str
    completed_at: str | None = None


class TurnResult(BaseModel):
    interviewer_text: str
    status: str
    missing_fields: list[str]
    facts: dict[str, str] = Field(default_factory=dict)


class CreateSessionRequest(BaseModel):
    language: str = "zh-CN"


class SubmitTurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value
