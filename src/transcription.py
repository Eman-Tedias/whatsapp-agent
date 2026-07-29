import os
import asyncio
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
_client = Groq(api_key=groq_api_key)

async def transcribe(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    def _call():
        return _client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model="whisper-large-v3-turbo",
            language="pt",
            response_format="text",
        )
    texto = await asyncio.to_thread(_call)
    print(f"[LLM:whisper] entrada={len(audio_bytes)} bytes ({filename}) saida={texto!r}")
    return texto