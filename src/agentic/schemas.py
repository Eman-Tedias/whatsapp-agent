from pydantic import BaseModel, Field

from deterministic.schemas import Conversa
from agentic.state import AgentState, campo_atual
from agentic.lesson_adapter import new_state_from_lesson
from agentic.router import router_turn
from config import MAX_TENTATIVAS_GUARDRAIL

_GUARDRAIL_BLOQUEADO_MARCADOR = "Guardrail blocked the input"


def _e_bloqueio_guardrail(e: Exception) -> bool:
    return isinstance(e, ValueError) and _GUARDRAIL_BLOQUEADO_MARCADOR in str(e)


class Roteiro:
    @staticmethod
    def erro_tecnico(nome: str | None = None) -> str:
        pedido = "Pode tentar me mandar essa mensagem de novo em alguns minutos?"
        if nome:
            primeiro_nome = nome.split()[0]
            return f"Oi, {primeiro_nome}! Tive um problema técnico agora. {pedido}"
        return f"Tive um problema técnico agora. {pedido}"

    @staticmethod
    def encerramento(motivo: str | None = None) -> str:
        if motivo:
            return f"{motivo}\n\nOs dados foram salvos."
        return "Os dados foram salvos."


class Session(BaseModel):
    session_id: str
    nome: str | None = None
    state: AgentState = Field(default_factory=new_state_from_lesson)
    despedida_enviada: bool = False
    imagens: dict[str, list[str]] = Field(default_factory=dict)
    hashes_recebidos: set = Field(default_factory=set)
    fotos_pendentes: list[dict] = Field(default_factory=list)
    tentativas_guardrail: int = 0

    @property
    def done(self) -> bool:
        return self.state.done

    def _resposta_guardrail_bloqueado(self) -> str:
        self.tentativas_guardrail += 1
        base = "Infelizmente não posso ajudar com isso. Por favor, responda apenas as questões referentes ao registro da atividade."
        if self.tentativas_guardrail >= MAX_TENTATIVAS_GUARDRAIL:
            self.state.done = True
            return Roteiro.encerramento("Como não conseguimos seguir com o registro dessa forma, vou salvar os dados como estão até agora.")
        if self.tentativas_guardrail == MAX_TENTATIVAS_GUARDRAIL - 1:
            return f"{base}\n\nInfelizmente vou ter que encerrar o registro caso a conversa mude de foco dessa forma mais uma vez."
        return base

    def resposta_se_encerrada(self) -> str | None:
        if not self.done:
            return None
        if self.despedida_enviada:
            return None
        self.despedida_enviada = True
        return "Até a próxima! 👋"

    def _aplicar_campo_midia_limpar(self, campo_key: str | None) -> None:
        if not campo_key:
            return
        if campo_key not in {f.key for f in self._campos_imagem()}:
            return
        self.imagens[campo_key] = []
        self.state.values[campo_key] = []
        self.state.midia_concluida.discard(campo_key)

    def _campos_imagem(self) -> list:
        return [f for f in self.state.fields if f.kind == "image"]

    async def _resolver_fotos_pendentes(self, mensagem_indicando_campo: str) -> str:
        mensagem = f"[O colaborador está indicando a qual campo pertencem {len(self.fotos_pendentes)} foto(s) pendente(s) de identificação.] {mensagem_indicando_campo}"
        try:
            result = await router_turn(self.state, mensagem, permitir_done=False)
        except Exception as e:
            if _e_bloqueio_guardrail(e):
                return self._resposta_guardrail_bloqueado()
            raise
        self._aplicar_campo_midia_limpar(result.campo_midia_limpar)
        valid_image_keys = {f.key for f in self._campos_imagem()}
        campo_key = result.campo_midia_indicado if result.campo_midia_indicado in valid_image_keys else None
        if campo_key is None:
            opcoes = " ou ".join(f'"{f.label}"' for f in self._campos_imagem())
            return f"Ainda não entendi -- as fotos que você mandou são pra {opcoes}?"
        for foto in self.fotos_pendentes:
            self.state.values.setdefault(campo_key, [])
            self.state.values[campo_key].append(foto["media_id"])
            self.imagens.setdefault(campo_key, []).append(foto["caminho"])
        self.fotos_pendentes = []
        return result.reply

    async def step(self, text: str) -> str:
        if self.fotos_pendentes:
            return await self._resolver_fotos_pendentes(text)

        if not text:
            campo = campo_atual(self.state)
            return campo.question if campo else ""

        try:
            result = await router_turn(self.state, text)
        except Exception as e:
            if _e_bloqueio_guardrail(e):
                return self._resposta_guardrail_bloqueado()
            raise
        self._aplicar_campo_midia_limpar(result.campo_midia_limpar)
        return result.reply

    async def registrar_imagem(
        self, caminho: str, sha256: str | None = None, media_id: str | None = None, legenda: str | None = None
    ) -> str:
        if sha256 and sha256 in self.hashes_recebidos:
            return "Essa foto parece igual a uma que você já enviou, então não contei ela de novo."
        if sha256:
            self.hashes_recebidos.add(sha256)

        campo = campo_atual(self.state)
        if campo is not None and campo.kind == "image":
            self.state.values.setdefault(campo.key, [])
            self.state.values[campo.key].append(media_id)
            self.imagens.setdefault(campo.key, []).append(caminho)
            return await self.step(legenda) if legenda else ""

        self.fotos_pendentes.append({"caminho": caminho, "sha256": sha256, "media_id": media_id})
        if legenda:
            return await self._resolver_fotos_pendentes(legenda)

        opcoes = " ou ".join(f'"{f.label}"' for f in self._campos_imagem())
        return f"Recebi sua foto! Ela é pra {opcoes}?"
