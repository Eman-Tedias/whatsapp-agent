from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os

from schemas import FallbackQuestion, BulkExtraction

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")

llm = ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY)
bulk_llm = llm.with_structured_output(BulkExtraction, method="json_mode")
fallback_llm = llm.with_structured_output(FallbackQuestion, method="json_mode")
edit_llm = llm.with_structured_output(BulkExtraction, method="json_mode")