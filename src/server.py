import asyncio
import httpx
import os
import time

from collections import deque

from dotenv import load_dotenv
from fastapi import FastAPI, Form, UploadFile, File, Request, Response
from transcription import transcribe

load_dotenv()

# Duas implementações do router coexistem (mesma interface pública: Session.step(text)
# e Session.registrar_imagem(...)) -- essa env var escolhe qual entra em produção sem
# precisar mexer no resto do server.py.
ROUTER_MODE = os.getenv("ROUTER_MODE", "deterministic")
if ROUTER_MODE == "agentic":
    from agentic.schemas import Conversa, Roteiro, Session
else:
    from deterministic.schemas import Conversa, Roteiro, Session

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

# Higiene básica de disco -- só apaga por idade, não sabe se a foto já foi "entregue"
# de verdade (isso depende da arquitetura de callback com o client, ainda não
# decidida; ver BACKLOG_FUTURO.md). Fácil desligar via env var se algo não bater.
LIMPEZA_FOTOS_HABILITADA = os.getenv("LIMPEZA_FOTOS_HABILITADA", "true").lower() == "true"
LIMPEZA_FOTOS_DIAS = int(os.getenv("LIMPEZA_FOTOS_DIAS", "30"))

# Sem um trigger externo de sessão (calendário/client -- ver BACKLOG_FUTURO.md), uma
# sessão encerrada em produção fica travada pro mesmo número até reiniciar o servidor
# (proposital). Em TEST_MODE, recomeça do zero na próxima mensagem pra facilitar teste manual.
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/heic": ".heic",
    "image/heif": ".heif",
}

def get_token() -> str:
    load_dotenv(override=True)
    return os.getenv("WHATSAPP_TOKEN", "")


def limpar_fotos_antigas() -> None:
    if not LIMPEZA_FOTOS_HABILITADA:
        return
    limite = time.time() - LIMPEZA_FOTOS_DIAS * 86400
    removidas = 0
    for nome in os.listdir(IMAGES_DIR):
        caminho = os.path.join(IMAGES_DIR, nome)
        try:
            if os.path.isfile(caminho) and os.path.getmtime(caminho) < limite:
                os.remove(caminho)
                removidas += 1
        except OSError as e:
            print(f"[LIMPEZA] erro ao remover {caminho}: {e}")
    if removidas:
        print(f"[LIMPEZA] {removidas} foto(s) com mais de {LIMPEZA_FOTOS_DIAS} dias removida(s)")

app = FastAPI()


@app.on_event("startup")
async def _limpeza_ao_iniciar():
    limpar_fotos_antigas()

sessions: dict[str, Session] = {}
# Um lock por sessão -- garante que duas mensagens quase simultâneas do mesmo número
# (comum no WhatsApp: texto + correção rápida, ou duas fotos em sequência) sejam
# processadas uma depois da outra, nunca em paralelo. Sem isso, as duas podiam ler o
# mesmo estado antes de qualquer uma escrever, perdendo dado ou avançando campo_index
# duas vezes. Seguro criar sem lock de proteção própria: não há nenhum `await` entre a
# checagem e a criação, então o event loop não intercala outra tarefa nesse meio tempo.
_session_locks: dict[str, asyncio.Lock] = {}

# A Meta reentrega o mesmo webhook se não receber um 200 rápido o bastante --
# comum quando o processamento demora (retry/backoff de LLM, rate limit, etc.).
# Sem isso, cada reentrega era tratada como mensagem nova e gerava resposta duplicada.
# Bound simples pra não crescer pra sempre; não precisa sobreviver a restart.
_MENSAGENS_PROCESSADAS_MAX = 500
_mensagens_processadas: set[str] = set()
_mensagens_processadas_ordem: deque[str] = deque()


def _reentrega(message_id: str | None) -> bool:
    if not message_id:
        return False
    if message_id in _mensagens_processadas:
        return True
    _mensagens_processadas.add(message_id)
    _mensagens_processadas_ordem.append(message_id)
    if len(_mensagens_processadas_ordem) > _MENSAGENS_PROCESSADAS_MAX:
        antigo = _mensagens_processadas_ordem.popleft()
        _mensagens_processadas.discard(antigo)
    return False


def _get_session(session_id: str, nome: str | None = None) -> Session:
    if session_id not in sessions or (TEST_MODE and sessions[session_id].done):
        sessions[session_id] = Session(session_id=session_id, nome=nome)
    elif nome and not sessions[session_id].nome:
        sessions[session_id].nome = nome
    return sessions[session_id]


def _get_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_locks:
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]

async def whatsapp_send_text(to: str, text: str, tentativas: int = 3) -> bool:
    headers = {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}

    }
    for tentativa in range(1, tentativas + 1):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(WHATSAPP_API_URL, json=payload, headers=headers, timeout=15)
            if r.status_code < 400:
                print(f"[WA/SENT] to={to}")
                return True
            print(f"[WA/SEND ERROR] tentativa {tentativa}/{tentativas} -- {r.status_code} → {r.text}")
            if r.status_code < 500:
                # Erro do lado do cliente (token inválido, payload errado, número
                # bloqueado...) -- tentar de novo não vai mudar o resultado.
                return False
        except httpx.RequestError as e:
            print(f"[WA/SEND ERROR] tentativa {tentativa}/{tentativas} -- {e}")
        if tentativa < tentativas:
            await asyncio.sleep(2 ** (tentativa - 1))

    print(f"[WA/SEND FAILED] não consegui enviar mensagem pra {to} após {tentativas} tentativas")
    return False

async def _processar_imagem(session: Session, sender: str, media_id: str, mime_type: str, sha256: str | None, legenda: str | None = None) -> str | None:
    """Baixa e registra uma imagem, seja ela recebida como foto ou como documento
    (WhatsApp manda o mesmo .jpg/.png por qualquer um dos dois caminhos, dependendo
    de qual botão o usuário tocou no app). Retorna None se já foi processada antes."""
    ext = MIME_TO_EXT.get(mime_type, ".jpg")
    filename = f"{sender}_{media_id}{ext}"
    filepath = os.path.join(IMAGES_DIR, filename)
    if os.path.exists(filepath):
        print(f"[WA/image] media_id {media_id} já processado, ignorando reentrega")
        return None
    image_bytes = await _download_whatsapp_media(media_id)
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    print(f"[WA/image] salvo em {filepath} (mime_type={mime_type!r})")
    return await session.registrar_imagem(filepath, sha256=sha256, media_id=media_id, legenda=legenda)


async def _download_whatsapp_media(media_id: str) -> bytes:
    headers = {"Authorization": f"Bearer {get_token()}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        media_url = r.json()["url"]

        r2 = await client.get(media_url, headers=headers, timeout=30)
        r2.raise_for_status()
        return r2.content

@app.get("/webhook")
async def webhook_verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return Response(content=params["hub.challenge"], media_type="text/plain")
    return Response(status_code=403)

@app.post('/webhook')
async def webhook_receive(request: Request):
    body = await request.json()
    sender = None
    nome = None
    try:
        entry = body["entry"][0]["changes"][0]["value"]
        messages = entry.get("messages")
        if not messages:
            return {"status": "no_messages"}

        msg = messages[0]
        sender = msg["from"]
        msg_type = msg["type"]
        contacts = entry.get("contacts")
        if contacts:
            nome = contacts[0].get("profile", {}).get("name")
        print(f"[WA] from={sender} type={msg_type} id={msg.get('id')!r} nome={nome!r}")

        if _reentrega(msg.get("id")):
            print(f"[WA] mensagem {msg.get('id')} já processada, ignorando reentrega")
            return {"status": "duplicate"}

        async with _get_lock(sender):
            session = _get_session(sender, nome=nome)

            if session.done:
                despedida = session.resposta_se_encerrada()
                if despedida is not None:
                    await whatsapp_send_text(sender, despedida)
                return {"status": "ok"}

            if msg_type == "text":
                text = msg["text"]["body"]
                reply = await session.step(text)

            elif msg_type == "audio":
                media_id = msg["audio"]["id"]
                audio_bytes = await _download_whatsapp_media(media_id)
                text = await transcribe(audio_bytes, filename="audio.ogg")
                print(f"[WA/transcript] {repr(text[:80])}")
                reply = await session.step(text)

            elif msg_type == "image":
                media_id = msg["image"]["id"]
                mime_type = msg["image"].get("mime_type", "image/jpeg")
                sha256 = msg["image"].get("sha256")
                legenda = msg["image"].get("caption")
                reply = await _processar_imagem(session, sender, media_id, mime_type, sha256, legenda=legenda)
                if reply is None:
                    return {"status": "duplicate"}

            elif msg_type == "document" and msg["document"].get("mime_type", "").startswith("image/"):
                # WhatsApp manda como "document" (não "image") quando o usuário escolhe
                # o arquivo pelo seletor de Documentos em vez da galeria/câmera -- mesmo
                # sendo um .jpg/.png de verdade.
                media_id = msg["document"]["id"]
                mime_type = msg["document"]["mime_type"]
                sha256 = msg["document"].get("sha256")
                legenda = msg["document"].get("caption")
                reply = await _processar_imagem(session, sender, media_id, mime_type, sha256, legenda=legenda)
                if reply is None:
                    return {"status": "duplicate"}

            elif msg_type == "unsupported" and any(e.get("code") == 131051 for e in msg.get("errors", [])):
                # Evento vazio que a Meta manda ao lado de um envio em lote/álbum -- não
                # carrega nenhuma mídia própria (sem media_id/mime_type), as fotos reais do
                # lote chegam certinho como mensagens "image" separadas. Responder aqui só
                # confundiria o usuário, já que as fotos de verdade já foram registradas
                # silenciosamente. Só loga, sem avisar nada.
                print(f"[WA/unsupported] evento vazio de lote/álbum, ignorando -- payload={msg!r}")
                reply = ""

            else:
                # Outro tipo que o WhatsApp não conseguiu classificar (motivo diferente do
                # caso acima) -- loga o payload cru pra investigar caso vire um padrão.
                print(f"[WA/unsupported] payload={msg!r}")
                reply = "No momento só consigo processar mensagens de texto, áudio 🎤 ou foto 📸. Pode reenviar nesse formato?"

            if reply:
                await whatsapp_send_text(sender, reply)

    except Exception as e:
        print(f"[WA/ERROR] {e}")
        if sender:
            try:
                await whatsapp_send_text(sender, Roteiro.erro_tecnico(nome))
            except Exception as e2:
                print(f"[WA/ERROR ao avisar usuário] {e2}")

    return {"status": "ok"}

@app.post("/message")
async def message(req: Conversa):
    print(f"[REQ] session={req.session_id[:8]} text={repr(req.text)}")
    t0 = time.time()
    try:
        async with _get_lock(req.session_id):
            session = _get_session(req.session_id)

            if session.done:
                return {"reply": session.resposta_se_encerrada()}

            reply = await session.step(req.text)
        print(f"[RES] {time.time() - t0:.1f}s reply={repr(reply[:60])}")
        return {"reply": reply}
    except Exception as e:
        print(f"[REQ/ERROR] {e}")
        return {"reply": Roteiro.erro_tecnico(_get_session(req.session_id).nome)}


@app.post("/audio")
async def audio(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
):
    print(f"[REQ/audio] session={session_id[:8]} file={audio.filename}")
    t0 = time.time()
    try:
        async with _get_lock(session_id):
            session = _get_session(session_id)

            if session.done:
                return {"reply": session.resposta_se_encerrada(), "transcript": None}

            audio_bytes = await audio.read()
            transcript = await transcribe(audio_bytes, filename=audio.filename or "audio.ogg")
            print(f"[TRANSCRIPT] {repr(transcript[:80])}")
            reply = await session.step(transcript)
        print(f"[RES/audio] {time.time() - t0:.1f}s reply={repr(reply[:60])}")
        return {"reply": reply, "transcript": transcript}
    except Exception as e:
        print(f"[REQ/audio/ERROR] {e}")
        return {"reply": Roteiro.erro_tecnico(_get_session(session_id).nome), "transcript": None}
