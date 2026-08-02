# Backlog futuro — Whatsapp-Agent

Itens mapeados mas fora do escopo atual, ou que dependem de decisões ainda não tomadas. Não implementar nada daqui sem alinhar antes.

## Arquitetura de sessão (bloqueador de várias coisas abaixo)

O plano de produção real: um client externo (calendário/agenda) vai disparar o registro ao final de cada aula/evento, chamando a aplicação com algo como "Olá fulano, vamos registrar as informações da aula/evento 'x'", e ao final a aplicação deve enviar os dados coletados de volta pro client. Cada sessão corresponde a exatamente um evento, sem continuidade esperada entre sessões.

**Isso ainda não foi decidido nem desenhado.** Não existe hoje:
- Endpoint pra o client iniciar uma sessão vinculada a um evento.
- Mecanismo de entrega do resultado final pro client (callback HTTP, polling, fila, etc.).
- Um identificador de sessão que não seja simplesmente o número de telefone.

Vários itens abaixo dependem dessa decisão pra serem resolvidos de verdade (não só paliativamente).

## Persistência

Hoje tudo vive em memória (`sessions: dict` em `server.py`) — reiniciar o processo perde qualquer sessão em andamento, sem aviso a ninguém. Provavelmente deve ser resolvido junto com a arquitetura de sessão acima (ex: se vai ter banco de dados, qual).

## Ciclo de vida das fotos

Implementamos uma limpeza simples por tempo (fotos com mais de N dias são apagadas), só como higiene de disco. O ciclo de vida correto — apagar a foto só depois de confirmar que ela foi efetivamente entregue/persistida em algum lugar permanente — depende da arquitetura de entrega ao client (ver seção acima). Hoje, se apagássemos no fim da sessão, arriscaríamos perder dado que nunca saiu da pasta local.

## Autenticação

- `/message` e `/audio` aceitam qualquer `session_id` sem token — qualquer um que descubra/adivinhe um `session_id` pode ler/escrever a sessão de outra pessoa.
- `/webhook` (POST) não valida a assinatura `X-Hub-Signature-256` da Meta — não há como confirmar que o payload realmente veio do WhatsApp.
- Decisão pendente: esses endpoints vão ficar expostos além de localhost? Se sim, isso é prioridade alta antes de ir pra produção.

## Validação de conteúdo de foto

Descartado por decisão explícita: mandar a foto pra um provedor de IA externo (Gemini) só para validar "isso parece ser uma folha de chamada?" significa enviar dado potencialmente sensível (rostos de menores, etc.) pra terceiros sem necessidade real. Não implementar sem repensar essa decisão de privacidade.

## Reenvio de fotos para confirmação visual

Decisão já tomada e mantida: o resumo mostra só contagem de fotos, não reenvia as fotos de volta pro usuário confirmar visualmente (o WhatsApp não tem preview leve, só reenviar a mensagem de imagem mesmo, com custo de API por envio). Aceito como trade-off pragmático diante da limitação da plataforma — revisitar só se isso virar problema real de confiança do usuário em uso real.

## Botões interativos do WhatsApp (Concluir/Editar)

Considerado como alternativa ao fluxo por linguagem natural para sinalizar "terminei"/"quero editar". Decidido não usar por ora (foco em PLN em vez de UI mockada). A API do WhatsApp Business suporta isso nativamente (reply buttons, sem necessidade de aprovação de template, já que é resposta dentro da janela de 24h) — revisitar se algum fluxo específico continuar sendo confuso por texto livre.

## "Agent router" para ambiguidade de mídia

Ideia mencionada como possível evolução futura: uma camada de agente mais inteligente para resolver casos de ambiguidade de roteamento de mídia de forma mais flexível do que o fluxo sequencial atual. Não agendada — revisitar se o fluxo sequencial (campo de mídia por vez) se mostrar limitante demais no uso real.

## Cota do Gemini free tier

Hoje configurado com `gemini-3.5-flash-lite` (500 requisições/dia no free tier desta conta, contra 20/dia do modelo anterior). Se o uso real crescer (múltiplas aulas/dia, múltiplos educadores), pode ser necessário reavaliar — seja mudando de modelo, seja fazendo upgrade de plano.

## Áudio longo ou com ruído

Ponto do brainstorm de baixa inclusão digital ainda não testado com material real (o usuário ia gerar um áudio de teste). Testamos português coloquial com sucesso via TTS sintético, mas não cobrimos ruído de fundo, gravação longa, ou qualidade de microfone ruim.

## Guardrail: tom hostil vs. intenção maliciosa

Ajustamos o guardrail pra distinguir grosseria (permitida, com pushback educado) de manipulação real (bloqueada). Validado com os casos que mapeamos, mas é uma área de julgamento fino da LLM que pode precisar de mais ajuste conforme surgirem casos reais de uso não previstos aqui.

## Chamada dedicada pra confirmação de finalização (`done`)

Ideia mencionada como possível evolução: hoje o `agentic/router.py` já veta boa parte do `done` por código (`campo_atual(state) is None`), mas o que sobra pro LLM — "essa mensagem do usuário significa confirmação pra terminar?" — ainda é decidido na mesma chamada que faz extração de campo, indicação de mídia etc. Já apareceu um caso real de vazamento (`done=True` falso durante a resolução de foto pendente, contido hoje com o parâmetro `permitir_done=False`), corrigido via ajuste de prompt. Não agendada — revisitar se esse tipo de vazamento voltar a aparecer depois do ajuste de prompt atual (ou seja, se o fix não generalizar sob teste). Diferente do tom hostil (julgamento fuzzy, baixo custo de erro), aqui o julgamento é mais estreito e o custo de errar é alto (sessão trava ou encerra errado), então uma call dedicada teria ganho real se a entrada só de prompt não segurar.
