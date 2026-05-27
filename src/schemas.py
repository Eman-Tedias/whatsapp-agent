from pydantic import create_model, BaseModel, ConfigDict

from lesson import _CAMPOS as campos

field_definitions = {c['campo']: (str, "") for c in campos}

BulkExtraction = create_model(
    'BulkExtraction',
    __config__=ConfigDict(coerce_numbers_to_str=True),
    **field_definitions
)

class FallbackQuestion(BaseModel):
    pergunta: str
