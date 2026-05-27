import json
from langchain_core.messages import SystemMessage, HumanMessage
from prompts import SYSTEM_BULK_PROMPT, SYSTEM_FALLBACK_PROMPT, SYSTEM_EDIT_PROMPT

def run_bulk(bulk_llm, historico, campos_desc, campos, json_model):
    json_template = json.dumps({c['campo']: "" for c in campos}, ensure_ascii=False)
    bulk = bulk_llm.invoke([
        SystemMessage(content=SYSTEM_BULK_PROMPT.format(campos_desc=campos_desc, json_template=json_template)),
        *historico
    ])
    for c in campos:
        if json_model[c['campo']] is None:
            valor = getattr(bulk, c['campo'])
            if valor:
                json_model[c['campo']] = valor

def run_edit(edit_llm, instrucao, campos, json_model, historico_edicao):
    json_template = json.dumps({c['campo']: "" for c in campos}, ensure_ascii=False)
    json_atual = json.dumps({c['campo']: json_model[c['campo']] for c in campos}, ensure_ascii=False)
    historico_edicao.append(HumanMessage(content=instrucao))
    result = edit_llm.invoke([
        SystemMessage(content=SYSTEM_EDIT_PROMPT.format(json_atual=json_atual, json_template=json_template)),
        *historico_edicao
    ])
    for c in campos:
        json_model[c['campo']] = getattr(result, c['campo'])

def run_fallback(fallback_llm, campo, historico) -> str:
    fallback = fallback_llm.invoke([
        SystemMessage(content=SYSTEM_FALLBACK_PROMPT.format(
            campo=campo['campo'],
            tipo=campo['tipo'],
            pergunta=campo['pergunta']
        )),
        *historico
    ])
    return fallback.pergunta
