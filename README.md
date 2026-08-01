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
| Data extraction | LLM via Groq (Llama 3.1) with structured output (LangChain + Pydantic) |
| Audio transcription | Whisper (`whisper-large-v3-turbo`, via Groq) |
| Test interface | Streamlit (simulates a WhatsApp-style chat UI) |
| Production channel (partial) | WhatsApp Cloud API (webhook implemented, not yet connected to an active account) |

## Structure

```
app.py                  # Streamlit interface (chat simulation, local/test use)
src/
  server.py             # FastAPI API: /message (Streamlit), /webhook and /audio (WhatsApp)
  schemas.py            # Pydantic models: Session, Conversa, Roteiro (fixed copy)
  lesson.py             # Fields collected per project
  conversation.py       # State machine: collection and editing phases
  extraction.py         # LLM calls: bulk extraction, editing, and fallback
  llm_client.py         # LLM client setup (Groq)
  prompts.py            # System prompts used for extraction/editing/fallback
  transcription.py      # Audio transcription (Whisper via Groq)
  main.py               # Simple CLI to test the conversation in the terminal
```

## Configuration

Create a `.env` file at the project root:

```bash
# Required. Groq API key, used for data extraction (LLM) and audio transcription (Whisper)
GROQ_API_KEY=

# Optional (default llama3-8b-8192). Groq model used for data extraction
GROQ_MODEL=llama-3.1-8b-instant

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

Project in POC/MVP stage, under active development. Planned improvements include stronger safeguards against prompt manipulation, semantic validation of numeric fields, and more transparency in edit and session-closing messages.
