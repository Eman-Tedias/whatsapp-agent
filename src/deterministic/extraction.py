import asyncio
import json

from deterministic.prompts import SYSTEM_BULK_PROMPT, SYSTEM_FALLBACK_PROMPT, SYSTEM_EDIT_PROMPT, SYSTEM_MEDIA_DONE_PROMPT, SYSTEM_CAMPO_MIDIA_PENDENTE_PROMPT
from deterministic.schemas import BULK_EXTRACTION_SCHEMA, FALLBACK_QUESTION_SCHEMA, EDIT_SCHEMA, MEDIA_DONE_SCHEMA, CAMPO_MIDIA_PENDENTE_SCHEMA


def _log_llm(nome: str, session_id: str, entrada: str, saida) -> None:
    """Log de toda chamada de LLM pro stdout do container -- Langfuse é ótimo pra
    investigar depois, mas não dá pra ler no `docker logs` na hora."""
    print(f"[LLM:{nome}] session={session_id[:8]} entrada={entrada!r} saida={saida!r}")


async def run_bulk(new_call, session_id, campos_respondidos_desc, texto, campos_desc, campos, json_model) -> tuple[bool, str, str]:
    bulk = await asyncio.to_thread(
        new_call()
        .prompts(
            system=SYSTEM_BULK_PROMPT.format(campos_desc=campos_desc, campos_respondidos_desc=campos_respondidos_desc),
            user="{texto}",
        )
        .context(texto=texto)
        .output(BULK_EXTRACTION_SCHEMA)
        .trace(session_id=session_id, user_id=session_id, tags=["extraction", "bulk"])
        .run
    )
    _log_llm("bulk", session_id, texto, bulk)
    for c in campos:
        if json_model[c['campo']] is None:
            valor = getattr(bulk, c['campo'])
            if valor:
                json_model[c['campo']] = valor
    correcao_campo = bulk.correcao_campo if bulk.correcao_campo != "nenhum" else ""
    return bulk.tom_hostil, correcao_campo, bulk.correcao_valor

async def run_edit(new_call, session_id, instrucao, campos, campos_midia, json_model, changelog_edicao) -> tuple[bool, bool, str, str, str]:
    json_atual = json.dumps({c['campo']: json_model[c['campo']] for c in campos}, ensure_ascii=False)
    campos_midia_desc = "\n".join([f"- {c['campo']}: {c['label']}" for c in campos_midia])
    changelog_texto = "\n".join(changelog_edicao) if changelog_edicao else "(nenhuma edição ainda)"
    result = await asyncio.to_thread(
        new_call()
        .prompts(
            system=SYSTEM_EDIT_PROMPT.format(json_atual=json_atual, campos_midia_desc=campos_midia_desc, changelog=changelog_texto),
            user="{instrucao}",
        )
        .context(instrucao=instrucao)
        .output(EDIT_SCHEMA)
        .trace(session_id=session_id, user_id=session_id, tags=["extraction", "edit"])
        .run
    )
    _log_llm("edit", session_id, instrucao, result)
    for c in campos:
        # Vazio = "não alterei esse campo" (mesma convenção do resto do app), nunca
        # "esvazie o campo" -- protege contra o modelo esquecer de ecoar um valor que
        # não devia mudar. Camada extra além do prompt já pedir só o campo alterado.
        novo_valor = getattr(result, c['campo'])
        if novo_valor:
            json_model[c['campo']] = novo_valor

    campo_limpar = result.campo_limpar if result.campo_limpar != "nenhum" else ""
    if campo_limpar:
        json_model[campo_limpar] = ""

    campo_midia_refazer = result.campo_midia_refazer if result.campo_midia_refazer != "nenhum" else ""
    return result.encerrar, result.tom_hostil, result.pergunta_fora_escopo, campo_midia_refazer, campo_limpar

async def run_media_done(new_call, session_id, campo_label, campos_respondidos_desc, text) -> tuple[bool, bool, str, str, str]:
    result = await asyncio.to_thread(
        new_call()
        .prompts(
            system=SYSTEM_MEDIA_DONE_PROMPT.format(campo_label=campo_label, campos_respondidos_desc=campos_respondidos_desc),
            user="{texto}",
        )
        .context(texto=text)
        .output(MEDIA_DONE_SCHEMA)
        .trace(session_id=session_id, user_id=session_id, tags=["extraction", "media_done"])
        .run
    )
    _log_llm("media_done", session_id, text, result)
    correcao_campo = result.correcao_campo if result.correcao_campo != "nenhum" else ""
    return result.concluiu_envio, result.tom_hostil, result.pergunta_fora_escopo, correcao_campo, result.correcao_valor

async def run_resolver_foto_pendente(new_call, session_id, campos_midia, text) -> tuple[str, str]:
    campos_midia_desc = "\n".join([f"- {c['campo']}: {c['label']}" for c in campos_midia])
    result = await asyncio.to_thread(
        new_call()
        .prompts(
            system=SYSTEM_CAMPO_MIDIA_PENDENTE_PROMPT.format(campos_midia_desc=campos_midia_desc),
            user="{texto}",
        )
        .context(texto=text)
        .output(CAMPO_MIDIA_PENDENTE_SCHEMA)
        .trace(session_id=session_id, user_id=session_id, tags=["extraction", "foto_pendente"])
        .run
    )
    _log_llm("foto_pendente", session_id, text, result)
    campo_midia = result.campo_midia if result.campo_midia != "indeterminado" else ""
    return campo_midia, result.pergunta_fora_escopo

async def run_fallback(new_call, session_id, campo, texto) -> str:
    fallback = await asyncio.to_thread(
        new_call()
        .prompts(
            system=SYSTEM_FALLBACK_PROMPT.format(
                campo=campo['campo'],
                tipo=campo['tipo'],
                pergunta=campo['pergunta'],
            ),
            user="{texto}",
        )
        .context(texto=texto)
        .output(FALLBACK_QUESTION_SCHEMA)
        .trace(session_id=session_id, user_id=session_id, tags=["extraction", "fallback", campo['campo']])
        .run
    )
    _log_llm("fallback", session_id, texto, fallback)
    return fallback.pergunta
