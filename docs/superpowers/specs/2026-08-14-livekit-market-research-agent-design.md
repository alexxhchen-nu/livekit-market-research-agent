# LiveKit Market Research Agent Design

## Goal

Provide a bilingual Chinese and English browser voice interview for market research. The agent gathers only consented, study-relevant information and persists a structured local record that can resume in a future session.

## Scope

- A Python LiveKit Agent for voice conversation.
- A FastAPI local service that mints browser room tokens and stores interview answers in SQLite.
- A static browser client that connects to a LiveKit room with microphone audio and plays the agent's audio.
- A shared-secret boundary between the LiveKit Agent and the local API.
- Interview fields: consent status, language, interview status, age eligibility, needs, behavior, criteria, barriers, price sensitivity, channels, quotes, unanswered questions, and summary.

## Non-goals

- Telephone, user accounts, cloud database, analytics dashboard, outbound follow-up, or raw-audio recording.
- Cross-call identity matching. A later call resumes only when an `interview_id` is supplied.

## Architecture

Browser -> FastAPI `/api/token` -> LiveKit room -> LiveKit Agent.

The agent receives an `interview_id` in dispatch metadata. Its `save_research_answer` tool sends a structured answer to FastAPI `/api/answers` with a shared secret. FastAPI validates consent, field names, request size, and secret before writing to SQLite. The browser can request `GET /api/interviews/{id}` for a prior summary.

## Security

Do not expose LiveKit API secrets or the agent's data secret to the browser. The browser receives only a short-lived room token. The API stores no payment information, government IDs, exact addresses, passwords, or raw audio. Restricted-category eligibility is boolean only.

## Verification

Automated tests prove unconsented answers are rejected, consented answers persist and are readable, unknown fields are rejected, agent requests require the secret, and browser token output excludes secrets.
