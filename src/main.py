import json as json_lib
from langchain_core.messages import HumanMessage

from llm_client import bulk_llm, fallback_llm, edit_llm
from extraction import run_bulk, run_fallback, run_edit
from lesson import _CAMPOS as campos, json_model

CONFIRMACAO_HOOK = "ok"

def main():
    historico = []
    campos_desc = "\n".join([
        f"- {c['campo']} ({c['tipo']}): referente a '{c['pergunta']}'"
        for c in campos
    ])

    for campo in campos:
        if json_model[campo['campo']] is not None:
            continue

        print(campo['pergunta'])
        tentativa = 0

        while json_model[campo['campo']] is None and tentativa < 3:
            resposta = input("Você: ")
            historico.append(HumanMessage(content=resposta))

            run_bulk(bulk_llm, historico, campos_desc, campos, json_model)

            if json_model[campo['campo']] is None:
                tentativa += 1
                if tentativa < 3:
                    print(run_fallback(fallback_llm, campo, historico))

        if json_model[campo['campo']] is None:
            json_model[campo['campo']] = ""

    for campo in campos:
        if json_model[campo['campo']] is None:
            json_model[campo['campo']] = ""

    def exibir_dados():
        dados = {c['campo']: json_model[c['campo']] for c in campos}
        print("\nDados coletados:")
        print(json_lib.dumps(dados, indent=2, ensure_ascii=False))

    exibir_dados()

    MAX_EDICOES = 5
    sem_alteracao = 0
    edicao = 0
    historico_edicao = []
    while edicao < MAX_EDICOES and sem_alteracao < 3:
        if edicao == MAX_EDICOES - 1:
            print("\nEssa é a última solicitação de edição e as informações serão registradas.")
        confirmacao = input("\nOs dados estão corretos? Informe tudo que deve ser editado em um mesmo texto (ou 'ok' para confirmar): ").strip()
        if confirmacao.lower() == CONFIRMACAO_HOOK:
            break
        dados_antes = {c['campo']: json_model[c['campo']] for c in campos}
        run_edit(edit_llm, confirmacao, campos, json_model, historico_edicao)
        dados_depois = {c['campo']: json_model[c['campo']] for c in campos}
        if dados_antes == dados_depois:
            sem_alteracao += 1
        else:
            sem_alteracao = 0
            exibir_dados()
        edicao += 1

    if sem_alteracao >= 3:
        print("\nComo não há edição a ser realizada, os dados da aula serão enviados. Obrigado pelo registro!")

    print("\nJSON final:")
    print(json_lib.dumps(json_model, indent=2, ensure_ascii=False, default=str))

if __name__ == '__main__':
    main()

