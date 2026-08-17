import os

from dotenv import load_dotenv

load_dotenv()

ROUTER_MODE = os.getenv("ROUTER_MODE", "deterministic")

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

LIMPEZA_FOTOS_HABILITADA = os.getenv("LIMPEZA_FOTOS_HABILITADA", "true").lower() == "true"
LIMPEZA_FOTOS_DIAS = int(os.getenv("LIMPEZA_FOTOS_DIAS", "30"))

TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
TEST_MODEL = os.getenv("TEST_MODEL", "gemini-3.5-flash-lite")

MAX_EDICOES = 5
MAX_SEM_ALTERACAO = 3
MAX_TENTATIVAS_MIDIA = 3
MAX_TENTATIVAS_GUARDRAIL = 3
MAX_TENTATIVAS_CAMPO = 3

TURNS_BY_FIELD = 4
