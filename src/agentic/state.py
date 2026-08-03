from pydantic import BaseModel, Field
from typing import Literal

from harpy.schema import build_output_model

NENHUM = "nenhum"

class FieldSpec(BaseModel):
    key: str
    question: str
    kind: Literal["text", "int", "image"]
    label: str

class AgentState(BaseModel):
    fields: list[FieldSpec]
    values: dict[str, str | int | list[str] | None] = {}
    midia_concluida: set[str] = Field(default_factory=set)
    done: bool = False
    turns: int = 0

class TurnResult(BaseModel):
    updates: dict[str, str | int | None] = {}
    campo_midia_indicado: str | None = None
    campo_midia_limpar: str | None = None
    avancar_midia: bool = False
    reply: str
    done: bool = False


def build_turn_model(state: AgentState):
    image_keys = [f.key for f in state.fields if f.kind == "image"]
    schema = {
        f.key: {
            "type": "string",
            "optional": True,
            "default": "",
            "description": f"valor para o campo '{f.label}', referente a '{f.question}'; vazio se esta mensagem não responder esse campo",
        }
        for f in state.fields if f.kind != "image"
    }
    schema["campo_midia_indicado"] = {
        "type": "string",
        "optional": True,
        "default": NENHUM,
        "literal": image_keys + [NENHUM],
        "description": f"nome exato do campo de imagem a que se referem as fotos aguardando identificação; '{NENHUM}' se a mensagem não tratar disso",
    }
    schema["campo_midia_limpar"] = {
        "type": "string",
        "optional": True,
        "default": NENHUM,
        "literal": image_keys + [NENHUM],
        "description": f"nome exato do campo de imagem cujas fotos o colaborador pediu para apagar/trocar/refazer; '{NENHUM}' se não houver esse pedido",
    }
    schema["avancar_midia"] = {
        "type": "bool",
        "optional": True,
        "default": False,
        "description": "true se o colaborador indicou que terminou de enviar as fotos do campo de imagem atual; false caso contrário",
    }
    schema["reply"] = {
        "type": "string",
        "description": "sua resposta ao colaborador, em português do Brasil",
    }
    schema["done"] = {
        "type": "bool",
        "optional": True,
        "default": False,
        "description": "true somente quando não houver campo pendente E o colaborador confirmar explicitamente que pode salvar",
    }
    return build_output_model(schema, name="TurnOutput")


def campo_resolvido(state: AgentState, f: FieldSpec) -> bool:
    if f.kind == "image":
        return f.key in state.midia_concluida
    return state.values.get(f.key) is not None


def campos_pendentes(state: AgentState) -> list[FieldSpec]:
    return [f for f in state.fields if not campo_resolvido(state, f)]


def campo_atual(state: AgentState) -> FieldSpec | None:
    pendentes = campos_pendentes(state)
    return pendentes[0] if pendentes else None
