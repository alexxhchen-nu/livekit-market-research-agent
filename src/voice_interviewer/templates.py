from .models import InterviewField, InterviewTemplate


_FIELDS = (
    ("context", "使用背景", "了解受访者的使用场景"),
    ("current_behavior", "当前行为", "了解受访者目前的做法"),
    ("needs", "需求", "了解受访者想解决的问题"),
    ("alternatives", "替代方案", "了解受访者考虑或使用过的替代方案"),
    ("decision_criteria", "决策标准", "了解受访者的选择标准"),
    ("barriers", "阻碍因素", "了解受访者未采取行动的原因"),
)


def default_template(language: str = "zh-CN") -> InterviewTemplate:
    return InterviewTemplate(
        title="通用市场研究访谈",
        language=language,
        objective="了解受访者的背景、当前行为、需求、替代方案、决策标准和阻碍因素。",
        fields=[
            InterviewField(id=field_id, label=label, purpose=purpose)
            for field_id, label, purpose in _FIELDS
        ],
    )
