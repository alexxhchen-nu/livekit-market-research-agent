# LiveKit Market Research Agent

Bilingual Chinese and English browser voice interviewer for consented market research.

## Included

- LiveKit browser voice client at `http://127.0.0.1:8010`.
- LiveKit Python Agent with concise interview instructions and interruption support.
- Structured answer tool, shared-secret protected API, SQLite persistence.
- Resumable interviews: pass the displayed interview ID to `POST /api/token` as `interview_id` from a trusted internal client. The browser stores the scoped resume token locally.
- Per-interview JSON and CSV download buttons. Results are stored locally in `data/research.db`.
- No raw audio recording, user login, phone support, cloud database, or analytics dashboard.

## Setup

1. Create LiveKit Cloud project. Copy its WebSocket URL, API key, API secret. Enable the inference models configured below, or replace model values with models available in the project.
2. Create `.env` from `.env.example`. Set both secrets to different random values of at least 32 characters.
3. Install dependencies:

```sh
uv sync --all-groups
```

4. Run API and web frontend in one terminal:

```sh
uv run uvicorn app.api:app --host 127.0.0.1 --port 8010
```

5. Run the LiveKit agent in another terminal:

```sh
uv run python agent.py dev
```

6. Open `http://127.0.0.1:8010`. Configure the study topic, client, audience, objective, and optional questions. Select language. Start interview. Grant microphone permission.

## Data flow

The browser requests a short-lived LiveKit participant token from `/api/token`. The token dispatches `market-research-agent` when the participant enters the room. The Agent alone has `RESEARCH_DATA_SECRET`, so it can store confirmed responses at `/api/answers`. The browser never receives either secret.

SQLite data is stored at `data/research.db`. The browser receives a per-interview download token, not the server research secret. After starting an interview, use `Download JSON` or `Download CSV`. Trusted operators can inspect an interview from a terminal with the server secret:

```sh
curl -H "X-Research-Secret: $RESEARCH_DATA_SECRET" \
  http://127.0.0.1:8010/api/interviews/INTERVIEW_ID
```

## Verify

```sh
uv run pytest -q
uv run python -m py_compile agent.py app/api.py
node --check web/app.js
```

## Required from you

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- Confirmation that your LiveKit project can use your selected STT, LLM, and TTS models.
- Open-ended study configuration: topic, client context, target audience, objective, optional custom questions.

Do not paste credentials into chat. Put them in `.env` locally.
