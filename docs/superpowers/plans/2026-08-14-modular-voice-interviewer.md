# 模块化语音访谈器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建可嵌入任意界面的浏览器语音市场访谈器，提供稳定 HTTP API、SQLite 持久化、OpenAI-compatible 推理与原生浏览器语音界面。

**Architecture:** `InterviewService` 是唯一业务入口，接受文本回合并返回下一句访谈回复。FastAPI 仅将 HTTP 转给该服务；SQLite 负责耐久状态；浏览器页既可文本交互也可用 Web Speech API 语音输入输出。Pipecat 被封装为可选语音适配器，不复制访谈状态或提示词。

**Tech Stack:** Python 3.12、FastAPI、Uvicorn、Pydantic、httpx、pytest、SQLite、HTML/CSS/JavaScript、Pipecat（可选额外安装）。

## Global Constraints

- 浏览器、Pipecat、未来 LiveKit 均通过 `InterviewService` 或四个 HTTP 端点复用访谈逻辑。
- `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 只存在服务器环境变量，绝不发给浏览器。
- 不加入 ORM、React、LangGraph 或供应商锁定代码。
- 默认模板语言为 `zh-CN`，并支持 `en-US`。
- 输入必须去除空白，限制为 4,000 字符；上游错误不得透传密钥或原始响应。
- 开发/测试没有 LLM 密钥时，`ScriptedLLM` 必须让整条文本访谈流程可运行。
- 每项业务逻辑先写一个失败测试、验证失败、写最小实现、验证通过。

---

## File Structure

- `pyproject.toml`：Python 包、运行和测试依赖。
- `.env.example`：不含真实密钥的服务配置。
- `.gitignore`：忽略环境、缓存、SQLite 数据及密钥。
- `src/voice_interviewer/models.py`：Pydantic 领域与 API 模型。
- `src/voice_interviewer/templates.py`：内置通用市场研究模板。
- `src/voice_interviewer/repository.py`：SQLite 读写，唯一 SQL 所在位置。
- `src/voice_interviewer/llm.py`：`InterviewLLM` 协议、真实 OpenAI-compatible HTTP 客户端、可预测测试客户端。
- `src/voice_interviewer/service.py`：提示词、LLM JSON 验证、访谈状态转移。
- `src/voice_interviewer/api.py`：FastAPI app 和四个 HTTP 端点。
- `src/voice_interviewer/pipecat_adapter.py`：可选 Pipecat 转写/语音适配边界。
- `web/index.html`、`web/app.js`、`web/styles.css`：无框架浏览器体验。
- `tests/test_service.py`：服务状态转移测试。
- `tests/test_api.py`：端到端 HTTP 契约测试。
- `tests/test_repository.py`：SQLite 持久化测试。

### Task 1: Project Foundation And Domain Models

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/voice_interviewer/__init__.py`
- Create: `src/voice_interviewer/models.py`
- Create: `src/voice_interviewer/templates.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces `InterviewField`, `InterviewTemplate`, `InterviewSession`, `TurnResult`, `CreateSessionRequest`, `SubmitTurnRequest`.
- Produces `default_template(language: str = "zh-CN") -> InterviewTemplate`.

- [ ] **Step 1: Write the failing model/template test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py::test_default_template_has_required_market_research_fields -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'voice_interviewer'`.

- [ ] **Step 3: Add minimal project and models implementation**

```toml
[project]
name = "opensource-voice-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastapi>=0.115", "httpx>=0.28", "pydantic>=2.10", "uvicorn>=0.34"]

[dependency-groups]
dev = ["pytest>=8.3", "pytest-asyncio>=0.25"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

```python
from pydantic import BaseModel, Field

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py::test_default_template_has_required_market_research_fields -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore .env.example src/voice_interviewer tests/test_models.py
git commit -m "feat: add interview domain models"
```

### Task 2: SQLite Repository

**Files:**
- Create: `src/voice_interviewer/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes `InterviewSession`, `InterviewTemplate` from `models.py`.
- Produces `SQLiteInterviewRepository(path: str)`, `create_session(session)`, `get_session(session_id)`, `add_turn(session_id, user_text, interviewer_text)`, `save_facts(session_id, facts)`, `export_session(session_id)`.

- [ ] **Step 1: Write the failing persistence test**

```python
from voice_interviewer.models import InterviewSession
from voice_interviewer.repository import SQLiteInterviewRepository
from voice_interviewer.templates import default_template


def test_repository_exports_session_turns_and_facts(tmp_path):
    repository = SQLiteInterviewRepository(tmp_path / "interviews.sqlite3")
    session = InterviewSession(
        id="session-1", template=default_template(), language="zh-CN",
        created_at="2026-08-14T00:00:00+00:00",
    )
    repository.create_session(session)
    repository.add_turn("session-1", "我每周购买一次", "您通常购买什么？")
    repository.save_facts("session-1", {"current_behavior": "每周购买一次"})

    exported = repository.export_session("session-1")

    assert exported["session"]["id"] == "session-1"
    assert exported["turns"][0]["user_text"] == "我每周购买一次"
    assert exported["facts"] == {"current_behavior": "每周购买一次"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repository.py::test_repository_exports_session_turns_and_facts -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'voice_interviewer.repository'`.

- [ ] **Step 3: Implement the smallest SQLite repository**

Create tables `sessions`, `turns`, `facts` with `sqlite3`. Store templates as JSON. Use parameterized SQL only. Return `None` for a missing session, append turns in sequence order, and replace facts with `INSERT ... ON CONFLICT(session_id, field_id) DO UPDATE`.

```python
class SQLiteInterviewRepository:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._initialize()

    def export_session(self, session_id: str) -> dict[str, object] | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        return {
            "session": session.model_dump(mode="json"),
            "turns": self.get_turns(session_id),
            "facts": self.get_facts(session_id),
        }
```

- [ ] **Step 4: Run repository tests**

Run: `uv run pytest tests/test_repository.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/voice_interviewer/repository.py tests/test_repository.py
git commit -m "feat: persist interview sessions in sqlite"
```

### Task 3: Interview LLM Boundary And Service

**Files:**
- Create: `src/voice_interviewer/llm.py`
- Create: `src/voice_interviewer/service.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes `SQLiteInterviewRepository`, template, session and facts models.
- Produces `InterviewLLM.complete(prompt: str) -> str`.
- Produces `ScriptedLLM(responses: list[str])`.
- Produces `OpenAICompatibleLLM(base_url: str, api_key: str, model: str)`.
- Produces `InterviewService(repository, llm)`, `start(language: str) -> tuple[InterviewSession, TurnResult]`, `reply(session_id: str, text: str) -> TurnResult`.

- [ ] **Step 1: Write the failing adaptive follow-up test**

```python
import json

from voice_interviewer.llm import ScriptedLLM
from voice_interviewer.repository import SQLiteInterviewRepository
from voice_interviewer.service import InterviewService


def test_reply_saves_known_facts_and_asks_for_missing_field(tmp_path):
    llm = ScriptedLLM([
        json.dumps({
            "facts": {"context": "为家人购买咖啡"},
            "interviewer_text": "您通常多久购买一次咖啡？",
            "complete": False,
        }),
    ])
    service = InterviewService(SQLiteInterviewRepository(tmp_path / "db.sqlite3"), llm)
    session, _ = service.start("zh-CN")

    result = service.reply(session.id, "我主要给家人买咖啡")

    assert result.facts == {"context": "为家人购买咖啡"}
    assert result.missing_fields[0] == "current_behavior"
    assert result.interviewer_text == "您通常多久购买一次咖啡？"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_service.py::test_reply_saves_known_facts_and_asks_for_missing_field -v`

Expected: FAIL with `ModuleNotFoundError` for `voice_interviewer.llm` or `service`.

- [ ] **Step 3: Implement service, validation, and clients**

The service must:

```python
MAX_TEXT_LENGTH = 4000

def _clean_text(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("text must not be blank")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError("text must be 4000 characters or fewer")
    return text
```

- Build a prompt that tells the LLM to respond with JSON matching `facts`, `interviewer_text`, `complete`.
- Parse JSON. If parsing/type validation fails, raise `LLMResponseError` without writing facts or a turn.
- Ignore LLM facts whose keys are not present in the active template.
- Compute `missing_fields` locally from required template fields, never trust LLM completion alone.
- In `start`, persist a new UUID session and return an opening question for the first missing field.
- In `reply`, persist user and interviewer texts plus validated facts atomically in repository methods.
- `OpenAICompatibleLLM` POSTs `{base_url.rstrip('/')}/chat/completions` with Bearer authentication; catches `httpx.HTTPError` and raises a redacted `LLMUnavailableError`.
- `ScriptedLLM` returns queued JSON strings and raises a clear error after the queue is exhausted.

- [ ] **Step 4: Add and run edge-case tests**

Add tests proving unknown LLM fields are ignored and invalid JSON leaves `facts` and `turns` unchanged.

Run: `uv run pytest tests/test_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/voice_interviewer/llm.py src/voice_interviewer/service.py tests/test_service.py
git commit -m "feat: add adaptive interview service"
```

### Task 4: FastAPI Integration Boundary

**Files:**
- Create: `src/voice_interviewer/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes `InterviewService`.
- Produces `create_app(service: InterviewService | None = None) -> FastAPI`.
- Exposes `POST /sessions`, `POST /sessions/{session_id}/turns`, `GET /sessions/{session_id}`, `GET /sessions/{session_id}/export`.

- [ ] **Step 1: Write the failing HTTP contract test**

```python
from fastapi.testclient import TestClient

from voice_interviewer.api import create_app
from voice_interviewer.llm import ScriptedLLM
from voice_interviewer.repository import SQLiteInterviewRepository
from voice_interviewer.service import InterviewService


def test_api_creates_submits_reads_and_exports_session(tmp_path):
    service = InterviewService(
        SQLiteInterviewRepository(tmp_path / "db.sqlite3"),
        ScriptedLLM(['{"facts": {"context": "个人使用"}, "interviewer_text": "您多久购买一次？", "complete": false}']),
    )
    client = TestClient(create_app(service))

    created = client.post("/sessions", json={"language": "zh-CN"})
    session_id = created.json()["session_id"]
    replied = client.post(f"/sessions/{session_id}/turns", json={"text": "我为自己购买"})
    exported = client.get(f"/sessions/{session_id}/export")

    assert created.status_code == 201
    assert replied.status_code == 200
    assert exported.json()["facts"] == {"context": "个人使用"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py::test_api_creates_submits_reads_and_exports_session -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'voice_interviewer.api'`.

- [ ] **Step 3: Implement minimal API and app factory**

```python
app = FastAPI(title="Open Source Voice Interviewer")

@app.post("/sessions", status_code=201)
def create_session(request: CreateSessionRequest):
    session, result = service.start(request.language)
    return {"session_id": session.id, **result.model_dump()}
```

Map blank/too-long input to HTTP 422, missing session to 404, malformed/upstream LLM output to HTTP 502 with a short public message, and never use server exception text as response content. Mount `web/` as static files with `/` serving `index.html`.

- [ ] **Step 4: Run API tests**

Run: `uv run pytest tests/test_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/voice_interviewer/api.py tests/test_api.py
git commit -m "feat: expose interview HTTP API"
```

### Task 5: Browser Text And Speech Interface

**Files:**
- Create: `web/index.html`
- Create: `web/app.js`
- Create: `web/styles.css`
- Modify: `src/voice_interviewer/api.py`

**Interfaces:**
- Consumes `POST /sessions`, `POST /sessions/{session_id}/turns`.
- Produces a single-page interface that starts sessions, renders transcripts, submits text, starts/stops browser speech recognition when available, and speaks agent replies.

- [ ] **Step 1: Write a failing browser contract test**

Create `tests/test_web.py`:

```python
from pathlib import Path


def test_web_client_uses_documented_session_endpoints():
    script = Path("web/app.js").read_text()

    assert 'fetch("/sessions"' in script
    assert 'SpeechRecognition' in script or 'webkitSpeechRecognition' in script
    assert "speechSynthesis.speak" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_web.py::test_web_client_uses_documented_session_endpoints -v`

Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Implement the minimal accessible webpage**

- Use visible buttons for start, microphone start/stop, and submit. Every icon-less command has clear text.
- Set output transcript to `aria-live="polite"`.
- Create session on Start; disable input until creation succeeds.
- Submit the trimmed text; render user and interviewer turns safely with `textContent`, never `innerHTML`.
- Set `SpeechRecognition.lang` from selected language. On final result, put transcript in text input; user explicitly submits it.
- If speech recognition is unsupported, hide/disable microphone control and preserve text flow.
- On an interviewer result, call `speechSynthesis.cancel()` then speak with `SpeechSynthesisUtterance` using selected language.
- Surface network/API errors in an `aria-live` status element.

- [ ] **Step 4: Run web and full test suite**

Run: `uv run pytest -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web src/voice_interviewer/api.py tests/test_web.py
git commit -m "feat: add browser voice interview interface"
```

### Task 6: Optional Pipecat Adapter And Operations Guide

**Files:**
- Create: `src/voice_interviewer/pipecat_adapter.py`
- Create: `README.md`
- Modify: `pyproject.toml`
- Test: `tests/test_pipecat_adapter.py`

**Interfaces:**
- Consumes `InterviewService.reply(session_id: str, text: str) -> TurnResult`.
- Produces `handle_transcript(service, session_id, transcript) -> str`.
- Documents a Pipecat pipeline where transcript input invokes `handle_transcript` and output feeds TTS.

- [ ] **Step 1: Write the failing adapter test**

```python
from voice_interviewer.pipecat_adapter import handle_transcript


def test_pipecat_adapter_returns_only_spoken_interviewer_text(fake_service):
    assert handle_transcript(fake_service, "session-1", "我的回答") == "下一题是什么？"
    assert fake_service.received == [("session-1", "我的回答")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipecat_adapter.py::test_pipecat_adapter_returns_only_spoken_interviewer_text -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'voice_interviewer.pipecat_adapter'`.

- [ ] **Step 3: Implement adapter and docs**

```python
def handle_transcript(service: InterviewService, session_id: str, transcript: str) -> str:
    return service.reply(session_id, transcript).interviewer_text
```

Add `pipecat-ai` as optional dependency group, not default runtime dependency. Document exact `uv` commands for:

```bash
uv sync --all-groups
uv run uvicorn voice_interviewer.api:app --factory --reload
```

Document environment variables, text fallback, Web Speech browser support caveat, HTTP integration examples, SQLite export endpoint, and a Pipecat pseudocode pipeline. State explicitly that the Pipecat adapter remains optional until STT/TTS provider configuration exists.

- [ ] **Step 4: Run full verification**

Run: `uv run pytest -v && uv run python -m compileall src`

Expected: all tests PASS; compilation succeeds.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/voice_interviewer/pipecat_adapter.py README.md tests/test_pipecat_adapter.py
git commit -m "docs: add Pipecat integration guide"
```

## Post-Implementation Manual Check

1. Copy `.env.example` to `.env`; configure an OpenAI-compatible model endpoint, key, model.
2. Run `uv sync --all-groups`.
3. Start `uv run uvicorn voice_interviewer.api:app --factory --reload`.
4. Open `http://127.0.0.1:8000`.
5. Start a Chinese session; complete an interview via typing, then via microphone when browser support exists.
6. Call `GET /sessions/{session_id}/export`; confirm every transcript turn and extracted fact persists.
7. Stop server. Reopen service. Call `GET /sessions/{session_id}`; confirm data survived restart.

## Self-Review

- Spec coverage: Tasks 1-3 implement templates, adaptive logic, local fact validation, SQLite and OpenAI-compatible calls. Task 4 provides all four endpoint contracts. Task 5 delivers browser text/voice fallback and accessibility. Task 6 defines optional Pipecat boundary and operations documentation.
- Placeholder scan: no `TBD`, `TODO`, generic validation steps, or undefined interfaces remain.
- Type consistency: `InterviewService.start(language)` and `InterviewService.reply(session_id, text)` are used consistently; `TurnResult` provides `interviewer_text`, `status`, `missing_fields`, and `facts` across service/API/interface.
