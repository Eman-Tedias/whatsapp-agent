from pydantic import BaseModel, Field
from copy import deepcopy
from typing import Literal

from lesson import _CAMPOS as campos, _CAMPOS_TEXTO as campos_texto, _CAMPOS_IMAGEM as campos_imagem, coleta_model

BULK_EXTRACTION_SCHEMA = {
    c['campo']: {"type": "string", "optional": True, "default": "", "description": f"referente a '{c['pergunta']}'"}
    for c in campos_texto
}
BULK_EXTRACTION_SCHEMA["tom_hostil"] = {
    "type": "bool",
    "optional": True,
    "default": False,
    "description": "true se a mensagem usa tom rude, ofensivo ou hostil dirigido ao assistente, mesmo que o pedido em si seja válido (dentro do escopo de registrar/editar a aula); false caso contrário",
}

FALLBACK_QUESTION_SCHEMA = {
    "pergunta": {"type": "string", "description": "pergunta de esclarecimento gerada para o educador"},
}

MEDIA_DONE_SCHEMA = {
    "concluiu_envio": {
        "type": "bool",
        "description": "true se a mensagem indica que o educador terminou de enviar as fotos e quer seguir adiante; false se pretende continuar enviando mais fotos ou a mensagem não trata disso",
    },
    "pergunta_fora_escopo": {
        "type": "string",
        "optional": True,
        "default": "",
        "description": "se a mensagem contém uma pergunta que o assistente não sabe responder ou que está fora de escopo, uma frase curta e honesta em português dizendo que não sabe/não pode ajudar; vazio caso contrário",
    },
    "tom_hostil": {
        "type": "bool",
        "optional": True,
        "default": False,
        "description": "true se a mensagem usa tom rude, ofensivo ou hostil dirigido ao assistente, mesmo que o pedido em si seja válido; false caso contrário",
    },
}

EDIT_SCHEMA = {
    **BULK_EXTRACTION_SCHEMA,
    "encerrar": {
        "type": "bool",
        "optional": True,
        "default": False,
        "description": "true se a mensagem expressa que o educador terminou e quer encerrar/confirmar os dados, mesmo sem usar a palavra exata 'ok'; false se for uma instrução de edição ou algo ambíguo/não relacionado",
    },
    "pergunta_fora_escopo": {
        "type": "string",
        "optional": True,
        "default": "",
        "description": "se a mensagem contém uma pergunta que o assistente não sabe responder ou que está fora do escopo de editar os dados da aula, uma frase curta e honesta em português dizendo que não sabe/não pode ajudar com isso; vazio caso contrário",
    },
    "campo_midia_refazer": {
        "type": "string",
        "optional": True,
        "default": "nenhum",
        # "nenhum" em vez de "" -- a API do Gemini rejeita enum com valor de string vazia
        # ("cannot be empty"), então precisa de um sentinela não-vazio pra "sem pedido".
        "literal": [c["campo"] for c in campos_imagem] + ["nenhum"],
        "description": "nome exato de um dos campos de mídia listados no prompt que o educador pediu para refazer/apagar/reenviar as fotos anteriores; 'nenhum' se não houver esse pedido",
    },
    "campo_limpar": {
        "type": "string",
        "optional": True,
        "default": "nenhum",
        "literal": [c["campo"] for c in campos_texto] + ["nenhum"],
        # Sinal separado e explícito pra "deixar em branco de propósito" (ex: "mandei
        # esse campo errado, deixa vazio que eu resolvo depois") -- sem isso, string
        # vazia no valor do próprio campo só significa "não mudei nada".
        "description": "nome exato de um campo de texto que o educador pediu explicitamente para deixar em branco/vazio por agora (não apenas 'não sei'/incerteza -- um pedido claro de limpar o campo); 'nenhum' se não houver esse pedido",
    },
}

# Adicionados depois de EDIT_SCHEMA (que já capturou o estado anterior de
# BULK_EXTRACTION_SCHEMA via spread) para não vazar pra lá -- na fase de edição a
# correção de texto já é livre por natureza, não precisa desse sinal à parte.
_CORRECAO_CAMPO_TEXTO = {
    "type": "string",
    "optional": True,
    "default": "nenhum",
    "literal": [c["campo"] for c in campos_texto] + ["nenhum"],
    "description": "nome exato de um campo de texto já respondido anteriormente na conversa que o educador quer corrigir agora, mesmo estando numa etapa diferente; 'nenhum' se não houver esse pedido",
}
_CORRECAO_VALOR = {
    "type": "string",
    "optional": True,
    "default": "",
    "description": "o novo valor corrigido para o campo indicado em correcao_campo; vazio caso contrário",
}
BULK_EXTRACTION_SCHEMA["correcao_campo"] = _CORRECAO_CAMPO_TEXTO
BULK_EXTRACTION_SCHEMA["correcao_valor"] = _CORRECAO_VALOR
MEDIA_DONE_SCHEMA["correcao_campo"] = _CORRECAO_CAMPO_TEXTO
MEDIA_DONE_SCHEMA["correcao_valor"] = _CORRECAO_VALOR

CAMPO_MIDIA_PENDENTE_SCHEMA = {
    "campo_midia": {
        "type": "string",
        "optional": True,
        "default": "indeterminado",
        "literal": [c["campo"] for c in campos_imagem] + ["indeterminado"],
        "description": "nome exato do campo de mídia que o educador indicou nesta resposta; 'indeterminado' se a resposta não esclarecer isso",
    },
    "pergunta_fora_escopo": {
        "type": "string",
        "optional": True,
        "default": "",
        "description": "se a mensagem contém uma pergunta fora de escopo que o assistente não sabe responder, uma frase curta e honesta em português; vazio caso contrário",
    },
}

class Roteiro():

    EDICAO = "Deseja incluir mais alguma edição?"
    COLETA = "Confirme os dados ou solicite alguma edição"

    @staticmethod
    def encerramento(motivo: str | None = None) -> str:
        if motivo:
            return f"{motivo}\n\nOs dados foram salvos."
        return "Obrigado pelo registro! Os dados foram salvos."

    @staticmethod
    def saudacao(nome: str | None = None) -> str:
        if nome:
            primeiro_nome = nome.split()[0]
            return f"Olá, {primeiro_nome}! Vamos registrar a aula de hoje."
        return "Olá! Vamos registrar a aula de hoje."

    @staticmethod
    def erro_tecnico(nome: str | None = None) -> str:
        pedido = "Pode tentar me mandar essa mensagem de novo em alguns minutos?"
        if nome:
            primeiro_nome = nome.split()[0]
            return f"Oi, {primeiro_nome}! Tive um problema técnico agora. {pedido}"
        return f"Tive um problema técnico agora. {pedido}"

    @staticmethod
    def resumo(json_model: dict) -> str:
        labels = {c['campo']: c['label'] for c in campos}
        linhas = "\n".join(f"• {labels[campo]}: {valor if valor is not None else '-'}" for campo, valor in json_model.items())
        return f"Aqui estão os dados coletados:\n\n{linhas}"

    @staticmethod
    def resumo_edicao(json_model: dict) -> str:
        return f"{Roteiro.resumo(json_model)}\n\n{Roteiro.EDICAO}"

    @staticmethod
    def resumo_coleta(json_model: dict) -> str:
        return f"{Roteiro.resumo(json_model)}\n\n{Roteiro.COLETA}"

class Conversa(BaseModel):
    session_id: str
    text: str

class Session(BaseModel):
    session_id: str
    nome: str | None = None
    json_model: dict = Field(default_factory=lambda: deepcopy(coleta_model))
    campo_index: int = 0
    tentativas: int = 0
    fase: Literal["coleta", "edicao"] = "coleta"
    # Log de mudanças de campo já aplicadas ("campo: 'antes' -> 'depois'"), não a
    # transcrição bruta da conversa -- evita dois problemas do design anterior: (1) uma
    # instrução antiga podia ser "re-derivada" como se fosse a mensagem atual, e (2) uma
    # mensagem bloqueada pelo guardrail nunca chegava a virar log (só aplicado após
    # sucesso), então não "envenenava" chamadas futuras como o texto bruto fazia.
    changelog_edicao: list = Field(default_factory=list)
    edicoes: int = 0
    sem_alteracao: int = 0
    done: bool = False
    despedida_enviada: bool = False
    # A saudação só deve aparecer uma vez, na primeira mensagem real da sessão -- não dá
    # pra depender de "texto vazio" pra detectar isso (a primeira mensagem de verdade do
    # WhatsApp já vem com conteúdo; só o CLI de teste em main.py chamava step("")).
    saudacao_enviada: bool = False
    imagens: dict = Field(default_factory=dict)
    # Hashes (sha256) das fotos já recebidas por campo -- detecta o educador mandando
    # a mesma foto de novo por engano/hábito, distinto da deduplicação de reentrega de
    # webhook por media_id (que já existe em server.py).
    imagens_hashes: dict = Field(default_factory=dict)
    aguardando_midia: str | None = None
    midia_substituindo: bool = False
    # Nome do campo de mídia (se algum) aguardando confirmação explícita do educador
    # pra avançar, depois que ele disse "pronto"/"terminei" -- em vez de avançar na
    # hora, perguntamos "podemos seguir?" primeiro (proteção contra contagem errada).
    confirmando_avanco_midia: str | None = None
    tentativas_midia: int = 0
    tentativas_guardrail: int = 0
    # Fotos recebidas na edição sem nenhum "refazer" em andamento -- ficam aqui até o
    # educador esclarecer pra qual campo de mídia elas são (ver Roteiro/conversation.py).
    fotos_pendentes: list = Field(default_factory=list)
    tentativas_foto_pendente: int = 0

    def _prefixo_saudacao(self) -> str:
        if self.saudacao_enviada:
            return ""
        self.saudacao_enviada = True
        return f"{Roteiro.saudacao(self.nome)}\n\n"

    def resposta_se_encerrada(self) -> str | None:
        """Se a sessão já terminou, retorna a despedida uma única vez (e None depois
        disso) -- pra parar de reprocessar/gastar LLM em mensagens após o encerramento."""
        if not self.done:
            return None
        if self.despedida_enviada:
            return None
        self.despedida_enviada = True
        return "Até a próxima! 👋"

    async def _step_coleta(self, text: str) -> str:
        from conversation import mensagem_coleta
        return await mensagem_coleta(self, text)

    async def _step_edicao(self, text: str) -> str:
        from conversation import mensagem_edicao
        return await mensagem_edicao(self, text)

    async def step(self, text: str) -> str:
        prefixo = self._prefixo_saudacao()
        if self.fase == "coleta":
            resposta = await self._step_coleta(text)
        else:
            resposta = await self._step_edicao(text)
        return f"{prefixo}{resposta}"

    def _adicionar_foto(self, campo_nome: str, caminho: str, sha256: str | None) -> tuple[int, bool]:
        """Registra a foto no campo dado. Retorna (contagem atual, era_duplicata)."""
        if campo_nome == self.aguardando_midia and self.midia_substituindo:
            self.imagens[campo_nome] = []
            self.imagens_hashes[campo_nome] = set()
            self.midia_substituindo = False
        self.tentativas_midia = 0

        if sha256 and sha256 in self.imagens_hashes.get(campo_nome, set()):
            return len(self.imagens.get(campo_nome, [])), True

        if sha256:
            self.imagens_hashes.setdefault(campo_nome, set()).add(sha256)
        self.imagens.setdefault(campo_nome, []).append(caminho)
        count = len(self.imagens[campo_nome])
        self.json_model[campo_nome] = f"{count} foto(s) recebida(s)"
        return count, False

    def registrar_imagem(self, caminho: str, sha256: str | None = None) -> str:
        prefixo = self._prefixo_saudacao()
        return f"{prefixo}{self._registrar_imagem_corpo(caminho, sha256)}"

    def _registrar_imagem_corpo(self, caminho: str, sha256: str | None) -> str:
        campo_nome = None
        if self.aguardando_midia:
            campo_nome = self.aguardando_midia
        elif (
            self.fase == "coleta"
            and self.campo_index < len(campos)
            and campos[self.campo_index]["tipo"] == "imagem"
        ):
            campo_nome = campos[self.campo_index]["campo"]

        if campo_nome is None:
            if self.fase == "coleta" and self.campo_index < len(campos):
                return f"No momento não estou esperando fotos.\n\n{campos[self.campo_index]['pergunta']}"
            if self.fase == "edicao":
                self.fotos_pendentes.append({"caminho": caminho, "sha256": sha256})
                opcoes = " ou ".join(f'"{c["label"]}"' for c in campos_imagem)
                if len(self.fotos_pendentes) == 1:
                    return f"Recebi sua foto! Ela é pra {opcoes}?"
                return f"Recebi mais uma foto ({len(self.fotos_pendentes)} no total). Ainda preciso saber: é pra {opcoes}?"
            return "No momento não estou esperando fotos. Se quiser reenviar alguma, me diga qual campo você quer refazer."

        count, duplicata = self._adicionar_foto(campo_nome, caminho, sha256)
        if duplicata:
            return f"Essa foto parece igual a uma que você já enviou pra esse campo, então não contei ela de novo. ({count} até agora)"
        # Sem resposta por foto -- só confirma quando o educador avisar que terminou
        # (ver confirmando_avanco_midia em conversation.py).
        return ""

    def resolver_fotos_pendentes(self, campo_nome: str) -> str:
        n = len(self.fotos_pendentes)
        count = 0
        duplicatas = 0
        for foto in self.fotos_pendentes:
            count, era_duplicata = self._adicionar_foto(campo_nome, foto["caminho"], foto["sha256"])
            duplicatas += 1 if era_duplicata else 0
        self.fotos_pendentes = []
        self.tentativas_foto_pendente = 0
        label = next((c["label"] for c in campos_imagem if c["campo"] == campo_nome), campo_nome)
        if duplicatas:
            return f"Combinado! Associei as fotos a \"{label}\" ({count} até agora -- {duplicatas} pareciam repetidas e não contei)."
        return f"Combinado! Associei {n} foto(s) a \"{label}\" ({count} até agora)."