from dotenv import load_dotenv
import os

load_dotenv()

from harpy import text

from guardrail_prompt import SYSTEM_GUARDRAIL_PROMPT

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
# GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
TEST_MODEL = os.getenv("TEST_MODEL", "gemini-3.1-flash-lite")


def new_call():
    if TEST_MODE:
        # Cada mensagem gasta 2 chamadas (guardrail + principal) e o free tier do
        # gemini-3.5-flash-lite libera só 15/min -- em teste manual isso estoura
        # rápido e cada 429 ainda dispara retries/backoff no harpy, deixando a
        # resposta lenta o suficiente pra Meta reentregar o mesmo webhook. Um modelo
        # separado (cota própria) em TEST_MODE evita tocar na cota do modelo de produção.
        return (
            text.gemini(model=TEST_MODEL)
            .guardrail(model=f"gemini/{TEST_MODEL}", prompt=SYSTEM_GUARDRAIL_PROMPT)
        )
    return (
        text.gemini(model=GEMINI_MODEL)
        # Lista, não string -- se o Gemini falhar por instabilidade (não por bloqueio
        # real) nessa checagem, o harpy tenta o Groq a seguir em vez de abortar a
        # mensagem inteira antes mesmo de chegar na chamada principal.
        .guardrail(model=[f"gemini/{GEMINI_MODEL}", f"groq/{GROQ_FALLBACK_MODEL}"], prompt=SYSTEM_GUARDRAIL_PROMPT)
        .fallback(model=f"groq/{GROQ_FALLBACK_MODEL}")
    )