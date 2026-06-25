from fastapi import FastAPI, Form, UploadFile, File, Request, Response
from schemas import Conversa, Session
from transcription import transcribe
import time
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

app = FastAPI()

sessions: dict[str, Session] = {}


def _get_session(session_id: str) -> Session:
    if session_id not in sessions:
        sessions[session_id] = Session(session_id=session_id)
    return sessions[session_id]


async def whatsapp_send_text(to: str, text: str) -> None:
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    async with httpx.AsyncClient() as client:
        r = await client.post(WHATSAPP_API_URL, json=payload, headers=headers, timeout=15)
        r.raise_for_status()


async def _download_whatsapp_media(media_id: str) -> bytes:
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient() as client:
        # Step 1: resolve media URL
        r = await client.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers=headers, timeout=10,
        )
        r.raise_for_status()
        media_url = r.json()["url"]

        # Step 2: download binary
        r2 = await client.get(media_url, headers=headers, timeout=30)
        r2.raise_for_status()
        return r2.content


# ── WhatsApp webhook ──────────────────────────────────────────────────────────

@app.get("/webhook")
async def webhook_verify(request: Request):
    params = dict(request.query_params)
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN
    ):
        return Response(content=params["hub.challenge"], media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def webhook_receive(request: Request):
    body = await request.json()

    try:
        entry = body["entry"][0]["changes"][0]["value"]
        messages = entry.get("messages")
        if not messages:
            return {"status": "no_messages"}

        msg = messages[0]
        sender = msg["from"]
        msg_type = msg["type"]
        print(f"[WA] from={sender} type={msg_type}")

        session = _get_session(sender)

        if msg_type == "text":
            text = msg["text"]["body"]
            reply = await session.step(text)

        elif msg_type == "audio":
            media_id = msg["audio"]["id"]
            audio_bytes = await _download_whatsapp_media(media_id)
            text = await transcribe(audio_bytes, filename="audio.ogg")
            print(f"[WA/transcript] {repr(text[:80])}")
            reply = await session.step(text)

        else:
            reply = "Por enquanto só processo texto e áudio. Por favor envie uma mensagem de texto."

        await whatsapp_send_text(sender, reply)

    except Exception as e:
        print(f"[WA/ERROR] {e}")

    return {"status": "ok"}


# ── UI/test endpoints ─────────────────────────────────────────────────────────

@app.post("/message")
async def message(req: Conversa):
    print(f"[REQ] session={req.session_id[:8]} text={repr(req.text)}")
    t0 = time.time()
    session = _get_session(req.session_id)
    reply = await session.step(req.text)
    print(f"[RES] {time.time() - t0:.1f}s reply={repr(reply[:60])}")
    return {"reply": reply}


@app.post("/audio")
async def audio(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
):
    print(f"[REQ/audio] session={session_id[:8]} file={audio.filename}")
    t0 = time.time()

    audio_bytes = await audio.read()
    transcript = await transcribe(audio_bytes, filename=audio.filename or "audio.ogg")
    print(f"[TRANSCRIPT] {repr(transcript[:80])}")

    session = _get_session(session_id)
    reply = await session.step(transcript)

    print(f"[RES/audio] {time.time() - t0:.1f}s reply={repr(reply[:60])}")
    return {"reply": reply, "transcript": transcript}
