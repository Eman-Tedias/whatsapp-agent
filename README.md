🇺🇸 English | 🇧🇷 [Português](README.pt-BR.md)

# WhatsApp Agent - Lesson Registration

POC/MVP built for a grant application from **WeAlter** (nonprofit organization): a chatbot for registering collaborator participation in educational/social projects.

## The problem

Rigid forms are a recurring pain point for anyone who needs to log field information. They require structured input, don't tolerate ambiguity, and don't adapt to each project's context. This agent replaces the form with a guided conversation: the collaborator describes what happened in their own words, while the system extracts and validates the required data behind the scenes.

## Why WhatsApp

WhatsApp is nearly universal among the project's target users. No need to install a new app, learn a new interface, or have any experience with data collection systems. This lowers the barrier especially for collaborators with less digital familiarity, who already use WhatsApp daily, instead of having to adapt to a new form or dashboard.

## Two conversation architectures: deterministic and agentic

The flow started as an explicit state machine (phases `coleta` → `edicao`, with attempt tracking, field index, and history): the LLM only extracts/interprets at specific points, called with schema-validated structured output, and the next step is always decided by Python code looking at the session state — never by the model. This gives:

- Flexibility for the user: answers can come in natural language and out of order, the LLM extracts whatever it can identify in each message.
- Control and safety for the system: each field has a defined type, validation, and retry limit.

In practice, though, hand-covering every real behavior variation — media confirmation, editing in parallel with collection, hostile tone, photos with no clear context, per-step retry limits — meant mapping a growing number of explicit states and exceptions in code. We built a second implementation, **agentic**: a single structured call per turn decides field extraction, media state, and session closing all at once, still via schema-validated output (not a free-form ReAct agent, just concentrating the decision into one call instead of several code steps) — and it's working very well in testing.

Both implementations coexist in the code (`src/deterministic/` and `src/agentic/`) and are interchangeable via the `ROUTER_MODE` variable (`deterministic` by default, or `agentic`), which lets us compare the two side by side before deciding which goes to production.

## How it works

```
Streamlit (app.py)  ──POST /message──▶  FastAPI (server.py)  ──▶  Session.step()
WhatsApp (webhook)  ──POST /webhook──▶
```

Each conversation is a `Session` (keyed by `session_id`) with two phases:

**1. Collection**
- The agent asks the fields defined in the project's script (today, in [src/lesson.py](src/lesson.py): lesson description and student count).
- Each message goes through bulk extraction (`run_bulk`): the LLM tries to identify as many fields as it can from the same message.
- If a field isn't identified, the system generates a clarifying question (`run_fallback`), up to 3 attempts per field before leaving it blank.
- Once all fields are filled, it shows a summary and moves to the editing phase.

**2. Editing**
- The user can request changes in natural language (`run_edit` applies the instruction to the current JSON).
- Typing "ok" confirms and closes the session.
- Safety limits: at most 5 edits or 3 consecutive messages with no real change. In those cases the session closes automatically.

Each project's fields (questions, type, label) live in [src/lesson.py](src/lesson.py), so the script can be adapted to other projects/grants without touching the conversation logic.

## Stack

| Layer | Technology |
|---|---|
| Backend / API | FastAPI + Uvicorn |
| LLM / data extraction | Gemini (primary) with Groq fallback, via [`harpy`](https://github.com/Eman-Tedias/harpy) — structured output + guardrail |
| Audio transcription | Whisper (`whisper-large-v3-turbo`, via Groq) |
| Test interface | Streamlit (simulates a WhatsApp-style chat UI) |
| Production channel (partial) | WhatsApp Cloud API (webhook implemented, not yet connected to an active account) |

## Structure

```
app.py                      # Streamlit interface (chat simulation, local/test use)
src/
  server.py                 # FastAPI API: /message (Streamlit), /webhook and /audio (WhatsApp)
  config.py                 # Centralized env vars and thresholds
  whatsapp_client.py        # WhatsApp Cloud API mechanics (token, sending, media download)
  llm_client.py             # LLM client via harpy (Gemini primary + Groq fallback)
  guardrail_prompt.py       # Guardrail prompt, shared by both routers
  lesson.py                 # Fields collected per project
  transcription.py          # Audio transcription (Whisper via Groq)
  main.py                   # Simple CLI to test the conversation in the terminal
  deterministic/            # Explicit state-machine router
    schemas.py              # Session, Conversa, Roteiro (fixed copy)
    conversation.py         # Collection and editing phases
    extraction.py           # LLM calls: bulk extraction, editing, fallback, media
    prompts.py
  agentic/                  # Single-call-per-turn router (see section above)
    schemas.py
    router.py
    state.py
    lesson_adapter.py
    prompts.py
vendor/
  harpy-0.1.0-py3-none-any.whl  # local wheel (offline fallback; requirements.txt installs from GitHub)
Dockerfile                  # Container build (WORKDIR switches to src/ before running uvicorn)
```

## Configuration

Create a `.env` file at the project root:

```bash
# Required. Gemini API key, the primary model (via harpy)
GEMINI_API_KEY=

# Required. Groq API key, used as Gemini's fallback and for audio transcription (Whisper)
GROQ_API_KEY=

# Optional (default gemini-3.5-flash-lite). Gemini model used as primary
GEMINI_MODEL=gemini-3.5-flash-lite

# Optional (default openai/gpt-oss-120b). Groq model used as Gemini's fallback
GROQ_MODEL=openai/gpt-oss-120b

# Optional (default deterministic). Chooses the router implementation: "deterministic"
# (explicit state machine) or "agentic" (a single call per turn decides everything) --
# see "Two conversation architectures" above
ROUTER_MODE=deterministic

# Optional (default false). In manual testing: uses a separate model/quota (TEST_MODEL) to
# avoid burning the production quota, and restarts the session from scratch after it closes
TEST_MODE=false

# Optional (default gemini-3.1-flash-lite). Model used only when TEST_MODE=true
TEST_MODEL=gemini-3.1-flash-lite

# Optional (default true). Toggles automatic cleanup of old photos on server startup
LIMPEZA_FOTOS_HABILITADA=true

# Optional (default 30). Age in days after which a photo gets deleted by the automatic cleanup
LIMPEZA_FOTOS_DIAS=30

# The variables below are only needed for the WhatsApp integration

# Webhook verification token for the WhatsApp Cloud API
WHATSAPP_VERIFY_TOKEN=

# Phone number ID configured on the WhatsApp Cloud API
WHATSAPP_PHONE_NUMBER_ID=

# Access token for sending messages via the WhatsApp Cloud API
WHATSAPP_TOKEN=
```

## Running locally

```bash
pip install -r requirements.txt
```

Start the API:

```bash
uvicorn src.server:app --reload
```

In another terminal, start the test interface:

```bash
streamlit run app.py
```

Or test it from the terminal, no UI:

```bash
python src/main.py
```

### WhatsApp integration (optional)

`server.py` already exposes `/webhook` (verification and message receiving for the WhatsApp Cloud API), but this integration isn't connected to an active account yet. The flow is currently validated via Streamlit. To enable it, set the `WHATSAPP_*` variables listed in [Configuration](#configuration).

## Status

Project in POC/MVP stage, under active development. Already implemented: a guardrail against prompt manipulation (blocks exploit/persona-switch attempts on every LLM call, see [src/guardrail_prompt.py](src/guardrail_prompt.py)) and edit/session-closing messages with a specific reason (remaining attempts, exact closing reason, instead of a generic notice). Still pending: semantic validation of numeric fields -- today `student_count` is treated as free text in the `deterministic` implementation; `agentic` already rejects non-numeric values (left pending instead of storing garbage), but neither validates plausibility (e.g., a negative or absurdly high number).
