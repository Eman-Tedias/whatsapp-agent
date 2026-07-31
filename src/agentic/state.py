from pydantic import BaseModel, Field
from typing import Literal

from harpy.schema import build_output_model

# Sentinela pros campos "literal" (enum) -- o Gemini rejeita enum com valor de string
# vazia ("cannot be empty"), então "sem indicação" precisa de um valor não-vazio.
NENHUM = "nenhum"

class FieldSpec(BaseModel):
    key: str
    question: str
    kind: Literal["text", "int", "image"]
    label: str

class AgentState(BaseModel):
    fields: list[FieldSpec]
    # Campos "text"/"int" guardam o valor direto; campos "image" acumulam uma lista de
    # ids de foto (cada foto nova só ADICIONA a essa lista -- ver router.py).
    values: dict[str, str | int | list[str] | None] = {}
    # Keys de campo de imagem já concluídos -- diferente de "values" ter conteúdo,
    # porque um campo de imagem aceita várias fotos antes de ser considerado terminado
    # (só fecha quando o colaborador disser explicitamente que acabou).
    midia_concluida: set[str] = Field(default_factory=set)
    done: bool = False
    turns: int = 0

class TurnResult(BaseModel):
    """Resultado já normalizado de um turno -- montado em router.py a partir do modelo
    dinâmico devolvido pelo LLM (ver build_turn_model). Não é o schema mandado pro
    modelo: os valores de campo chegam como propriedades nomeadas e viram `updates`
    aqui, já sem os sentinelas "nenhum"."""
    updates: dict[str, str | int | None] = {}
    campo_midia_indicado: str | None = None
    campo_midia_limpar: str | None = None
    avancar_midia: bool = False
    reply: str
    done: bool = False


def build_turn_model(state: AgentState):
    """Monta em runtime o schema de saída da chamada do router, com uma propriedade
    NOMEADA por campo do formulário.

    Um `dict` de chaves livres não serve aqui: vira `additionalProperties` no JSON
    Schema, que a controlled generation do Gemini não suporta -- ela devolve o objeto
    vazio, sem erro, e nenhum valor chega no código."""
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
    """O campo que o formulário está "na vez de" preencher agora -- primeiro campo
    ainda não resolvido, na ordem de `fields`. Usado pra decidir a qual campo uma foto
    sem texto pertence: só é auto-atribuída se esse for um campo de imagem."""
    pendentes = campos_pendentes(state)
    return pendentes[0] if pendentes else None
