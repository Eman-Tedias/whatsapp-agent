from dotenv import load_dotenv

load_dotenv()

from harpy import text

from guardrail_prompt import SYSTEM_GUARDRAIL_PROMPT
from config import GEMINI_MODEL, GROQ_FALLBACK_MODEL, TEST_MODE, TEST_MODEL


def new_call():
    if TEST_MODE:
        return (
            text.gemini(model=TEST_MODEL)
            .guardrail(model=f"gemini/{TEST_MODEL}", prompt=SYSTEM_GUARDRAIL_PROMPT)
        )
    return (
        text.gemini(model=GEMINI_MODEL)
        .guardrail(model=[f"gemini/{GEMINI_MODEL}", f"groq/{GROQ_FALLBACK_MODEL}"], prompt=SYSTEM_GUARDRAIL_PROMPT)
        .fallback(model=f"groq/{GROQ_FALLBACK_MODEL}")
    )