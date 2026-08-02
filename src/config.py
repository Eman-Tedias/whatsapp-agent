import os

from dotenv import load_dotenv

load_dotenv()

ROUTER_MODE = os.getenv("ROUTER_MODE", "deterministic")

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

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
# GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
TEST_MODEL = os.getenv("TEST_MODEL", "gemini-3.1-flash-lite")

MAX_EDICOES = 5
MAX_SEM_ALTERACAO = 3
MAX_TENTATIVAS_MIDIA = 3
MAX_TENTATIVAS_GUARDRAIL = 3
MAX_TENTATIVAS_CAMPO = 3

TURNS_BY_FIELD = 4
