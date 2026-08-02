import logging
import re
import time

from agentic.state import AgentState, TurnResult, NENHUM, build_turn_model, campos_pendentes, campo_atual
from harpy import text
from agentic.prompts import ROUTER_SYSTEM_PROMPT, ROUTER_USER_TEMPLATE
from guardrail_prompt import SYSTEM_GUARDRAIL_PROMPT
from config import GEMINI_MODEL, GROQ_FALLBACK_MODEL, TURNS_BY_FIELD

logger = logging.getLogger(__name__)

# Padrões de PII a mascarar antes de logar texto livre (mensagem do usuário, reply do
# bot): e-mail, CPF, telefone/qualquer sequência longa de dígitos. Mantém o texto
# legível o suficiente pra validar a lógica da conversa sem expor dado pessoal.
_PADROES_PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"), "[cpf]"),
    (re.compile(r"\d{5,}"), "[numero]"),
]


def _anonimizar(texto: str | None) -> str | None:
    if not texto:
        return texto
    for padrao, marcador in _PADROES_PII:
        texto = padrao.sub(marcador, texto)
    return texto


def _sem_sentinela(valor: str | None) -> str | None:
    return None if not valor or valor == NENHUM else valor


def _valor_para_kind(kind: str, valor: str) -> str | int | None:
    """Coage o valor bruto vindo do LLM (sempre string, ver build_turn_model) pro tipo
    do campo. Campo "int" com valor não-numérico é descartado (fica pendente) em vez
    de guardar lixo num campo que consumidores downstream esperam ser inteiro."""
    if kind != "int":
        return valor
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


async def router_turn(state: AgentState, user_message: str, permitir_done: bool = True) -> TurnResult:
    """`permitir_done=False` é usado pela resolução de foto pendente (schemas.py) --
    essa chamada só identifica a qual campo uma foto pertence, não é um turno de
    conversa de verdade, então nunca pode encerrar a sessão sozinha (o modelo já
    inferiu `done=True` errado nesse ponto, sem confirmação explícita nenhuma, porque
    nesse turno "campos_pendentes" costuma estar vazio)."""
    state.turns += 1
    campo_atual_antes = campo_atual(state)
    pendentes = campos_pendentes(state)
    logger.info(
        "turno=%s campo_atual=%s mensagem=%r",
        state.turns, campo_atual_antes.key if campo_atual_antes else None, _anonimizar(user_message),
    )
    t0 = time.time()
    call = (
        text.gemini(model=GEMINI_MODEL)
        .prompts(system=ROUTER_SYSTEM_PROMPT, user=ROUTER_USER_TEMPLATE)
        .context(
            campos_pendentes="\n".join(f"- {f.key} ({f.kind}): {f.question}" for f in pendentes),
            valores_atuais=str(state.values),
            mensagem=user_message,
        )
        .output(build_turn_model(state))
        .guardrail(model=[f"gemini/{GEMINI_MODEL}"], prompt=SYSTEM_GUARDRAIL_PROMPT)
        .fallback(model=f"groq/{GROQ_FALLBACK_MODEL}")
    )
    saida = call.run()

    # Cada campo de texto é uma propriedade nomeada na saída (ver build_turn_model);
    # aqui elas voltam a virar o dict `updates`, já sem os vazios/sentinelas.
    updates = {
        f.key: valor
        for f in state.fields
        if f.kind != "image" and getattr(saida, f.key, None)
        for valor in [_valor_para_kind(f.kind, getattr(saida, f.key))]
        if valor is not None
    }
    result = TurnResult(
        updates=updates,
        campo_midia_indicado=_sem_sentinela(saida.campo_midia_indicado),
        campo_midia_limpar=_sem_sentinela(saida.campo_midia_limpar),
        # "optional" no schema dinâmico vira Optional[bool] pro Gemini -- às vezes ele
        # devolve null explícito em vez de false. bool(None) = False, então isso nunca
        # quebra a validação do TurnResult (que exige bool de verdade, não Optional).
        avancar_midia=bool(saida.avancar_midia),
        reply=saida.reply,
        done=bool(saida.done),
    )
    logger.info(
        "done em %.1fs | reply=%r campos_atualizados=%s campo_midia_indicado=%r campo_midia_limpar=%r avancar_midia=%s done=%s",
        time.time() - t0, _anonimizar(result.reply), list(result.updates.keys()),
        result.campo_midia_indicado, result.campo_midia_limpar, result.avancar_midia, result.done,
    )
    state.values.update(result.updates)

    if result.avancar_midia and campo_atual_antes is not None and campo_atual_antes.kind == "image":
        state.midia_concluida.add(campo_atual_antes.key)
        logger.info("campo de imagem concluído: %s", campo_atual_antes.key)

    campo_depois = campo_atual(state)
    logger.info("campo_atual_depois=%s", campo_depois.key if campo_depois else None)

    if not permitir_done:
        result.done = False
        return result

    limite = len(state.fields) * TURNS_BY_FIELD

    if state.turns == limite-1:
        result.reply = f"{result.reply}\n\nOlha, essa é a última oportunidade para você enviar ou editar informações. Por favor, envie todas na sequência. 😊"
    elif state.turns >= limite:
        state.done = True
        result.done = True
        result.reply = f"{result.reply}\n\nComo já se passaram muitas mensagens nessa conversa, vou salvar os dados como estão até agora."
    if campo_atual(state) is None and result.done:
        state.done = True
    return result
