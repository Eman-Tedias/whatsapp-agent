from pydantic import create_model, BaseModel, ConfigDict, Field
from copy import deepcopy
from typing import Literal

from lesson import _CAMPOS as campos, coleta_model

field_definitions = {c['campo']: (str, "") for c in campos}

BulkExtraction = create_model(
    'BulkExtraction',
    __config__=ConfigDict(coerce_numbers_to_str=True),
    **field_definitions
)

class Roteiro():

    SAUDACAO = "Olá! Vamos registrar a aula de hoje."
    ENCERRAMENTO = "Obrigado pelo registro! Os dados foram salvos."
    EDICAO = "Deseja incluir mais alguma edição?"
    COLETA = "Confirme os dados ou solicite alguma edição"

    @staticmethod
    def resumo(json_model: dict) -> str:
        labels = {c['campo']: c['label'] for c in campos}
        linhas = "\n".join([f"• {labels[campo]}: {valor}\n\n" for campo, valor in json_model.items()])
        return f"Aqui estão os dados coletados:\n\n{linhas}"
    
    @staticmethod
    def resumo_edicao(json_model: dict) -> str:
        return f"{Roteiro.resumo(json_model)}\n\n{Roteiro.EDICAO}"

    @staticmethod
    def resumo_coleta(json_model: dict) -> str:
        return f"{Roteiro.resumo(json_model)}\n\n{Roteiro.COLETA}"

class FallbackQuestion(BaseModel):
    pergunta: str

class Conversa(BaseModel):
    session_id: str
    text: str

class Session(BaseModel):
    session_id: str
    historico: list = Field(default_factory=list)
    json_model: dict = Field(default_factory=lambda: deepcopy(coleta_model))
    campo_index: int = 0
    tentativas: int = 0
    fase: Literal["coleta", "edicao"] = "coleta"
    historico_edicao: list = Field(default_factory=list)
    edicoes: int = 0
    sem_alteracao: int = 0
    done: bool = False

    async def _step_coleta(self, text: str) -> str:
        from conversation import mensagem_coleta
        return await mensagem_coleta(self, text)

    async def _step_edicao(self, text: str) -> str:
        from conversation import mensagem_edicao
        return await mensagem_edicao(self, text)

    async def step(self, text: str) -> str:
        if self.fase == "coleta":
            return await self._step_coleta(text)
        else:
            return await self._step_edicao(text)