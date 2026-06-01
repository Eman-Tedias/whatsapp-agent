from langchain_core.messages import HumanMessage
import time

from lesson import _CAMPOS as campos
from llm_client import bulk_llm, fallback_llm, edit_llm
from extraction import run_bulk, run_edit, run_fallback
from schemas import Roteiro

MAX_EDICOES = 5
MAX_SEM_ALTERACAO = 3


async def mensagem_coleta(session, text: str) -> str:
    if not text:
        return f"{Roteiro.SAUDACAO}\n\n{campos[0]['pergunta']}"
    campos_desc = "\n".join([
        f"- {c['campo']} ({c['tipo']}): referente a '{c['pergunta']}'"
        for c in campos
    ])
    pergunta = campos[session.campo_index]
    print(f"[BULK] campo_index={session.campo_index} campo={pergunta['campo']}")
    session.historico.append(HumanMessage(content=text))
    t0 = time.time()
    await run_bulk(bulk_llm, session.historico, campos_desc, campos, session.json_model)
    print(f"[BULK] done em {time.time()-t0:.1f}s | json_model={session.json_model}")
    valor = session.json_model[pergunta["campo"]]
    if not valor:
        session.tentativas += 1
        if session.tentativas >= 3:
            session.json_model[pergunta["campo"]] = ""
            session.tentativas = 0
        else:
            print(f"[FALLBACK] campo={pergunta['campo']} tentativa={session.tentativas}")
            t0 = time.time()
            resp = await run_fallback(fallback_llm, pergunta, session.historico)
            print(f"[FALLBACK] done em {time.time()-t0:.1f}s")
            return resp
    session.campo_index += 1
    while session.campo_index < len(campos):
        proximo = campos[session.campo_index]
        if session.json_model[proximo["campo"]] is None:
            return proximo["pergunta"]
        session.campo_index += 1
    session.fase = "edicao"
    return Roteiro.resumo_coleta(session.json_model)


async def mensagem_edicao(session, text: str) -> str:
    if text == "ok":
        session.done = True
        return Roteiro.ENCERRAMENTO
    dados_antes = session.json_model.copy()
    await run_edit(edit_llm, text, campos, session.json_model, session.historico_edicao)
    dados_depois = session.json_model.copy()
    if dados_antes == dados_depois:
        session.sem_alteracao += 1
    else:
        session.sem_alteracao = 0
    session.edicoes += 1
    if session.sem_alteracao >= MAX_SEM_ALTERACAO or session.edicoes >= MAX_EDICOES:
        session.done = True
        return Roteiro.ENCERRAMENTO
    return Roteiro.resumo_edicao(session.json_model)
