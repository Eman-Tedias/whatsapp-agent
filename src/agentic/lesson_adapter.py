from lesson import _CAMPOS as campos
from agentic.state import FieldSpec, AgentState

_KIND_BY_TIPO = {
    "texto livre": "text",
    "número inteiro": "int",
    "imagem": "image",
}

def fields_from_lesson() -> list[FieldSpec]:
    return [
        FieldSpec(key=c["campo"], question=c["pergunta"], kind=_KIND_BY_TIPO[c["tipo"]], label=c["label"])
        for c in campos
    ]

def new_state_from_lesson() -> AgentState:
    return AgentState(fields=fields_from_lesson())