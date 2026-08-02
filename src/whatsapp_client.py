import asyncio
import os

import httpx
from dotenv import load_dotenv

from config import WHATSAPP_API_URL

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
