# LiveKit Market Research Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local bilingual LiveKit browser voice interviewer that saves consented structured research data.

**Architecture:** FastAPI serves the static browser client, mints short-lived LiveKit participant tokens, and persists data in SQLite. A LiveKit Agent uses a single authenticated tool to save answers and receives an interview ID from room metadata.

**Tech Stack:** Python, FastAPI, SQLite, LiveKit Agents, LiveKit API, LiveKit JavaScript client.

## Global Constraints

- Use Python 3.11 or newer and `uv`.
- Never expose `LIVEKIT_API_SECRET` or `RESEARCH_DATA_SECRET` to browser JavaScript.
- Persist only consented, study-relevant answers.
- Support Chinese and English voice output.
- Use local SQLite until shared production storage is required.

---

### Task 1: Research API storage boundary

**Files:**
- Create: `app/api.py`
- Create: `app/__init__.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `POST /api/answers` with `X-Research-Secret`.
- Produces: `GET /api/interviews/{interview_id}` structured interview record.

- [ ] **Step 1: Run the failing consent test**

Run: `uv run pytest -q`
Expected: FAIL because `app.api` does not exist.

- [ ] **Step 2: Implement minimal SQLite-backed API**

Implement `create_app(database_path, research_secret)` with answer validation, consent gating, storage, and interview retrieval.

- [ ] **Step 3: Run storage tests**

Run: `uv run pytest -q`
Expected: PASS.

### Task 2: Room-token endpoint

**Files:**
- Modify: `app/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `POST /api/token` with optional `interview_id` and `language`.
- Produces: room URL, short-lived participant JWT, random interview ID.

- [ ] **Step 1: Add failing token contract test**

Assert a token response contains `token`, `url`, and `interview_id`, but no API secret.

- [ ] **Step 2: Generate JWT with LiveKit `AccessToken`**

Use room grant and encode the interview ID in participant metadata.

- [ ] **Step 3: Run tests**

Run: `uv run pytest -q`
Expected: PASS.

### Task 3: LiveKit research interviewer

**Files:**
- Create: `agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: room metadata and `RESEARCH_API_URL` / `RESEARCH_DATA_SECRET`.
- Produces: `save_research_answer(field, value, consent_status)` agent tool.

- [ ] **Step 1: Add failing pure-function validation test**

Test valid research fields are accepted and unknown fields rejected.

- [ ] **Step 2: Implement prompt, tool, and LiveKit session**

Use multilingual STT, concise TTS-oriented instructions, tool persistence, and a greeting.

- [ ] **Step 3: Run tests**

Run: `uv run pytest -q`
Expected: PASS.

### Task 4: Browser voice interview client

**Files:**
- Create: `web/index.html`
- Create: `web/app.js`
- Create: `web/styles.css`
- Modify: `app/api.py`

**Interfaces:**
- Consumes: `/api/token`.
- Produces: microphone-published LiveKit connection with remote audio playback and interview ID UI.

- [ ] **Step 1: Serve static web files from FastAPI**

- [ ] **Step 2: Implement one-button voice start and end controls**

- [ ] **Step 3: Verify backend tests and browser JavaScript syntax**

Run: `uv run pytest -q && node --check web/app.js`
Expected: PASS.

### Task 5: Local operations

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Create: `README.md`

**Interfaces:**
- Consumes: LiveKit credentials and local environment variables.
- Produces: reproducible local run instructions.

- [ ] **Step 1: Add configuration placeholders**

- [ ] **Step 2: Run full verification**

Run: `uv sync && uv run pytest -q && node --check web/app.js`
Expected: PASS.
