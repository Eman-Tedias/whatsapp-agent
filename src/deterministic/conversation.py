import time

from lesson import _CAMPOS as campos, _CAMPOS_TEXTO as campos_texto, _CAMPOS_IMAGEM as campos_imagem
from llm_client import new_call
from deterministic.extraction import run_bulk, run_edit, run_fallback, run_media_done, run_resolver_foto_pendente
from deterministic.schemas import Roteiro

MAX_EDICOES = 5
MAX_SEM_ALTERACAO = 3
MAX_TENTATIVAS_MIDIA = 3
MAX_TENTATIVAS_GUARDRAIL = 3
MAX_TENTATIVAS_CAMPO = 3

_AVISO_TOM_HOSTIL = "Ei, não precisa falar assim comigo -- só quero te ajudar. 😊\n\n"

_GUARDRAIL_BLOQUEADO_MARCADOR = "Guardrail blocked the input"


def _e_bloqueio_guardrail(e: Exception) -> bool:
    return isinstance(e, ValueError) and _GUARDRAIL_BLOQUEADO_MARCADOR in str(e)


def _resposta_guardrail_bloqueado(session) -> str:
    """Converte um bloqueio do guardrail numa resposta educada em vez de deixar o
    usuário sem nenhuma resposta. Reincidência repetida encerra a sessão e entrega
    os dados coletados até então, do jeito que estão."""
    session.tentativas_guardrail += 1
    if session.tentativas_guardrail >= MAX_TENTATIVAS_GUARDRAIL:
        session.done = True
        return Roteiro.encerramento("Como não conseguimos seguir com o registro dessa forma, vou salvar os dados como estão até agora.")
    restantes = MAX_TENTATIVAS_GUARDRAIL - session.tentativas_guardrail
    if restantes == 1:
        aviso = "Essa é sua última tentativa -- se insistir, vou encerrar o registro com os dados que já temos até agora."
    else:
        aviso = f"Você tem mais {restantes} tentativas antes de encerrarmos o registro com os dados atuais."
    return f"Infelizmente não posso ajudar com isso. Por favor, responda apenas as questões referentes ao registro da aula.\n\n{aviso}"


def _label_do_campo(campo_nome: str) -> str:
    return next((c["label"] for c in campos if c["campo"] == campo_nome), campo_nome)


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def _aviso_tentativas_edicao(session) -> str:
    restantes = MAX_EDICOES - session.edicoes
    if restantes > 2:
        return ""
    return f"\n\n⚠️ Restam {restantes} {_plural(restantes, 'tentativa de edição', 'tentativas de edição')} nesta sessão."


def _aviso_tentativas_midia(session) -> str:
    restantes = MAX_TENTATIVAS_MIDIA - session.tentativas_midia
    return f" (restam {restantes} {_plural(restantes, 'tentativa', 'tentativas')})"


def _campos_respondidos_desc(session) -> str:
    linhas = [f"- {c['campo']}: {c['label']} = {session.json_model[c['campo']]}" for c in campos_texto if session.json_model[c['campo']] is not None]
    return "\n".join(linhas) if linhas else "(nenhum campo de texto respondido ainda)"


def _aplicar_correcao(session, correcao_campo: str, correcao_valor: str, campo_atual: str | None = None) -> str:
    """Aplica uma correção a um campo de texto já respondido, detectada fora do fluxo
    normal (o usuário lembrou de algo enquanto respondia outra pergunta ou mandava
    fotos). Retorna um aviso pra prefixar na resposta, ou string vazia se não houve
    correção real (campo vazio ou é o próprio campo que está sendo respondido agora)."""
    if not correcao_campo or correcao_campo == campo_atual:
        return ""
    session.json_model[correcao_campo] = correcao_valor
    return f"Anotado! Corrigi \"{_label_do_campo(correcao_campo)}\" pra você.\n\n"


async def _tratar_confirmacao_avanco_midia(session, text: str, ao_confirmar) -> str:
    """Depois que o educador diz que terminou de mandar fotos, perguntamos se pode
    seguir antes de avançar de verdade -- proteção contra contagem errada (ex: ele
    quis dizer que terminou UM lote, não que não vai mandar mais nenhuma foto).
    `ao_confirmar` gera a resposta final (avançar campo ou mostrar resumo de edição),
    específica de cada fase, só quando a confirmação vem positiva."""
    campo_nome = session.confirmando_avanco_midia
    label = _label_do_campo(campo_nome)
    try:
        concluiu_envio, tom_hostil, pergunta_fora_escopo, correcao_campo, correcao_valor = await run_media_done(
            new_call, session.session_id, label, _campos_respondidos_desc(session), text
        )
    except Exception as e:
        if _e_bloqueio_guardrail(e):
            return _resposta_guardrail_bloqueado(session)
        raise
    prefixo = _aplicar_correcao(session, correcao_campo, correcao_valor)
    prefixo += f"{pergunta_fora_escopo}\n\n" if pergunta_fora_escopo else ""
    prefixo += _AVISO_TOM_HOSTIL if tom_hostil else ""
    session.confirmando_avanco_midia = None
    if concluiu_envio:
        return f"{prefixo}{ao_confirmar()}"
    return f"{prefixo}Sem problemas, pode continuar enviando fotos para \"{label}\". Me avise de novo quando terminar."


def _avancar_campo(session) -> str:
    session.campo_index += 1
    while session.campo_index < len(campos):
        proximo = campos[session.campo_index]
        if session.json_model[proximo["campo"]] is None:
            return proximo["pergunta"]
        session.campo_index += 1
    session.fase = "edicao"
    return Roteiro.resumo_coleta(session.json_model)


async def mensagem_coleta(session, text: str) -> str:
    if not text:
        return campos[0]["pergunta"]

    if session.confirmando_avanco_midia:
        return await _tratar_confirmacao_avanco_midia(session, text, lambda: _avancar_campo(session))

    pergunta = campos[session.campo_index]

    if pergunta["tipo"] == "imagem":
        try:
            concluiu_envio, tom_hostil, pergunta_fora_escopo, correcao_campo, correcao_valor = await run_media_done(
                new_call, session.session_id, pergunta["label"], _campos_respondidos_desc(session), text
            )
        except Exception as e:
            if _e_bloqueio_guardrail(e):
                return _resposta_guardrail_bloqueado(session)
            raise
        prefixo_midia = _aplicar_correcao(session, correcao_campo, correcao_valor)
        prefixo_midia += f"{pergunta_fora_escopo}\n\n" if pergunta_fora_escopo else ""
        prefixo_midia += _AVISO_TOM_HOSTIL if tom_hostil else ""
        if concluiu_envio:
            if not session.json_model[pergunta["campo"]]:
                return f"{prefixo_midia}Ainda não recebi nenhuma foto. Envie ao menos uma imagem antes de continuar."
            session.confirmando_avanco_midia = pergunta["campo"]
            return f"{prefixo_midia}{session.json_model[pergunta['campo']]} para \"{pergunta['label']}\". Podemos seguir?"
        return f"{prefixo_midia}Essa etapa é só para fotos. {pergunta['pergunta']}"

    campos_desc = "\n".join([
        f"- {c['campo']} ({c['tipo']}): referente a '{c['pergunta']}'"
        for c in campos_texto
    ])
    print(f"[BULK] campo_index={session.campo_index} campo={pergunta['campo']}")
    t0 = time.time()
    try:
        tom_hostil, correcao_campo, correcao_valor = await run_bulk(new_call, session.session_id, _campos_respondidos_desc(session), text, campos_desc, campos_texto, session.json_model)
    except Exception as e:
        if _e_bloqueio_guardrail(e):
            return _resposta_guardrail_bloqueado(session)
        raise
    print(f"[BULK] done em {time.time()-t0:.1f}s | json_model={session.json_model}")
    prefixo = _aplicar_correcao(session, correcao_campo, correcao_valor, campo_atual=pergunta["campo"])
    prefixo += _AVISO_TOM_HOSTIL if tom_hostil else ""
    valor = session.json_model[pergunta["campo"]]
    if not valor:
        session.tentativas += 1
        if session.tentativas >= MAX_TENTATIVAS_CAMPO:
            session.json_model[pergunta["campo"]] = ""
            session.tentativas = 0
            return f"{prefixo}Sem problemas, vou seguir com o registro sem essa informação por agora.\n\n{_avancar_campo(session)}"
        print(f"[FALLBACK] campo={pergunta['campo']} tentativa={session.tentativas}")
        t0 = time.time()
        try:
            resp = await run_fallback(new_call, session.session_id, pergunta, text)
        except Exception as e:
            if _e_bloqueio_guardrail(e):
                return _resposta_guardrail_bloqueado(session)
            raise
        print(f"[FALLBACK] done em {time.time()-t0:.1f}s")
        aviso = " Sem problemas se não conseguir agora! Se preferir, posso seguir com o registro sem essa informação por enquanto." if session.tentativas == MAX_TENTATIVAS_CAMPO - 1 else ""
        return f"{prefixo}{resp}{aviso}"
    session.tentativas = 0
    return f"{prefixo}{_avancar_campo(session)}"


async def mensagem_edicao(session, text: str) -> str:
    if session.confirmando_avanco_midia:
        return await _tratar_confirmacao_avanco_midia(session, text, lambda: Roteiro.resumo_edicao(session.json_model))

    if session.aguardando_midia:
        campo_nome = session.aguardando_midia
        tem_foto_nova = not session.midia_substituindo
        try:
            concluiu_envio, tom_hostil, pergunta_fora_escopo, correcao_campo, correcao_valor = await run_media_done(
                new_call, session.session_id, _label_do_campo(campo_nome), _campos_respondidos_desc(session), text
            )
        except Exception as e:
            if _e_bloqueio_guardrail(e):
                return _resposta_guardrail_bloqueado(session)
            raise
        prefixo_midia = _aplicar_correcao(session, correcao_campo, correcao_valor)
        prefixo_midia += f"{pergunta_fora_escopo}\n\n" if pergunta_fora_escopo else ""
        prefixo_midia += _AVISO_TOM_HOSTIL if tom_hostil else ""

        if concluiu_envio and tem_foto_nova:
            session.aguardando_midia = None
            session.tentativas_midia = 0
            session.confirmando_avanco_midia = campo_nome
            return f"{prefixo_midia}{session.json_model[campo_nome]} para \"{_label_do_campo(campo_nome)}\". Podemos seguir?"

        session.tentativas_midia += 1
        if session.tentativas_midia >= MAX_TENTATIVAS_MIDIA:
            session.aguardando_midia = None
            session.midia_substituindo = False
            session.tentativas_midia = 0
            aviso = "Combinado, mantive as fotos que já tinha" if not tem_foto_nova else "Combinado, considerei as fotos novas que já recebi"
            return f"{prefixo_midia}{aviso} para \"{_label_do_campo(campo_nome)}\".\n\n{Roteiro.resumo_edicao(session.json_model)}"

        if concluiu_envio:
            return f"{prefixo_midia}Ainda não recebi nenhuma foto nova. Envie ao menos uma imagem antes de continuar.{_aviso_tentativas_midia(session)}"
        return f"{prefixo_midia}Envie as novas fotos e me avise quando terminar.{_aviso_tentativas_midia(session)}"

    if session.fotos_pendentes:
        try:
            campo_midia, pergunta_fora_escopo = await run_resolver_foto_pendente(new_call, session.session_id, campos_imagem, text)
        except Exception as e:
            if _e_bloqueio_guardrail(e):
                return _resposta_guardrail_bloqueado(session)
            raise
        prefixo_pendente = f"{pergunta_fora_escopo}\n\n" if pergunta_fora_escopo else ""

        if campo_midia:
            return f"{prefixo_pendente}{session.resolver_fotos_pendentes(campo_midia)}"

        opcoes = " ou ".join(f'"{c["label"]}"' for c in campos_imagem)
        session.tentativas_foto_pendente += 1
        if session.tentativas_foto_pendente >= MAX_TENTATIVAS_MIDIA:
            n = len(session.fotos_pendentes)
            session.fotos_pendentes = []
            session.tentativas_foto_pendente = 0
            return f"{prefixo_pendente}Sem problemas, não consegui identificar pra qual campo eram as {n} foto(s) que você mandou, então vou descartá-las por agora. Se quiser, pode reenviar dizendo claramente se são pra {opcoes}."
        return f"{prefixo_pendente}Ainda não entendi -- as fotos que você mandou são pra {opcoes}?"

    dados_antes = session.json_model.copy()
    try:
        quer_finalizar, tom_hostil, pergunta_fora_escopo, campo_midia_refazer, campo_limpar = await run_edit(
            new_call, session.session_id, text, campos_texto, campos_imagem, session.json_model, session.changelog_edicao
        )
    except Exception as e:
        if _e_bloqueio_guardrail(e):
            return _resposta_guardrail_bloqueado(session)
        raise
    dados_depois = session.json_model.copy()
    # Log de "campo: antes -> depois" só pra quem realmente mudou -- vira o contexto
    # que a próxima chamada recebe no lugar da transcrição bruta, então só entra aqui
    # (depois de um run_edit bem-sucedido) o que de fato foi aplicado.
    for c in campos_texto:
        if dados_antes[c["campo"]] != dados_depois[c["campo"]]:
            session.changelog_edicao.append(f'{c["campo"]}: "{dados_antes[c["campo"]] or ""}" -> "{dados_depois[c["campo"]] or ""}"')
    prefixo = f"{pergunta_fora_escopo}\n\n" if pergunta_fora_escopo else ""
    prefixo += _AVISO_TOM_HOSTIL if tom_hostil else ""
    if campo_limpar:
        prefixo += f"Combinado, deixei \"{_label_do_campo(campo_limpar)}\" em branco por agora.\n\n"

    if campo_midia_refazer:
        session.aguardando_midia = campo_midia_refazer
        session.midia_substituindo = True
        session.tentativas_midia = 0
        session.edicoes += 1
        if session.edicoes >= MAX_EDICOES:
            session.done = True
            return f"{prefixo}{Roteiro.encerramento('Chegamos ao limite de edições desta conversa, então vou salvar os dados como estão.')}"
        return f"{prefixo}Combinado! As fotos que eu já tinha de \"{_label_do_campo(campo_midia_refazer)}\" serão substituídas -- envie de novo todas as fotos desse campo (não só as que faltavam) e me avise quando terminar.{_aviso_tentativas_edicao(session)}"

    if quer_finalizar:
        session.done = True
        if dados_antes != dados_depois:
            return f"{prefixo}{Roteiro.encerramento('Dado editado e enviado, obrigado!')}"
        return f"{prefixo}{Roteiro.encerramento()}"

    if dados_antes == dados_depois and not campo_limpar:
        session.sem_alteracao += 1
    else:
        session.sem_alteracao = 0
    session.edicoes += 1
    if session.sem_alteracao >= MAX_SEM_ALTERACAO:
        session.done = True
        return f"{prefixo}{Roteiro.encerramento('Não consegui identificar novas edições, então vou salvar os dados como estão agora.')}"
    if session.edicoes >= MAX_EDICOES:
        session.done = True
        return f"{prefixo}{Roteiro.encerramento('Chegamos ao limite de edições desta conversa, então vou salvar os dados como estão.')}"
    return f"{prefixo}{Roteiro.resumo_edicao(session.json_model)}{_aviso_tentativas_edicao(session)}"
