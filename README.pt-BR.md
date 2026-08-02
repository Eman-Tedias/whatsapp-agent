🇺🇸 [English](README.md) | 🇧🇷 Português

# WhatsApp Agent - Registro de Aula

POC/MVP para um edital da **WeAlter** (ONG/OSC): um chatbot para registro de participação de colaboradores em projetos educacionais/sociais.

## O problema

Formulários rígidos são uma dor recorrente pra quem precisa registrar informações de campo. Exigem preenchimento estruturado, não toleram ambiguidade e não se adaptam ao contexto de cada projeto. Esse agente troca o formulário por uma conversa guiada: o colaborador conta o que aconteceu com as próprias palavras e o sistema extrai e valida os dados necessários por trás dos panos.

## Por que WhatsApp

O WhatsApp é praticamente universal no público-alvo do projeto. Não precisa instalar um app novo, aprender uma interface nova nem ter experiência com sistemas de coleta de dados. Isso ajuda bastante colaboradores com menos familiaridade digital, que já usam o WhatsApp no dia a dia, em vez de ter que se adaptar a um formulário ou painel.

## Duas arquiteturas de conversa: determinística e agentic

O fluxo começou como uma máquina de estados explícita (fases `coleta` → `edicao`, com controle de tentativas, índice de campo e histórico): o LLM só extrai/interpreta em pontos específicos, chamado com saída estruturada validada por schema, e quem decide o próximo passo é sempre código Python olhando pro estado da sessão — nunca o modelo. Isso dá:

- Flexibilidade pro usuário: as respostas podem vir em linguagem natural e fora de ordem, o LLM extrai o que conseguir identificar em cada mensagem.
- Controle e segurança pro sistema: cada campo tem tipo, validação e número de tentativas definidos.

Na prática, porém, cobrir à mão cada variação de comportamento real — confirmação de mídia, edição em paralelo à coleta, tom hostil, fotos sem contexto claro, limites de tentativa por etapa — significou mapear um número crescente de estados e exceções explícitas no código. Criamos então uma segunda implementação, **agentic**: uma única chamada estruturada por turno decide ao mesmo tempo extração de campo, estado de mídia e encerramento de sessão, ainda via saída validada por schema (não é um agente livre tipo ReAct, só concentra a decisão numa chamada em vez de várias etapas de código) — e está funcionando muito bem em teste.

As duas implementações coexistem no código (`src/deterministic/` e `src/agentic/`) e são intercambiáveis pela variável `ROUTER_MODE` (`deterministic` por padrão, ou `agentic`), o que permite comparar as duas em paralelo antes de decidir qual vai pra produção.

## Como funciona

```
Streamlit (app.py)  ──POST /message──▶  FastAPI (server.py)  ──▶  Session.step()
WhatsApp (webhook)  ──POST /webhook──▶
```

Cada conversa é uma `Session` (por `session_id`) com duas fases:

**1. Coleta**
- O agente pergunta os campos definidos no roteiro do projeto (hoje, em [src/lesson.py](src/lesson.py): descrição da aula e número de alunos).
- Cada mensagem passa por extração em lote (`run_bulk`): o LLM tenta identificar quantos campos conseguir na mesma mensagem.
- Se um campo não é identificado, o sistema gera uma pergunta de esclarecimento (`run_fallback`), até 3 tentativas por campo antes de seguir em branco.
- Quando todos os campos são preenchidos, mostra um resumo e passa pra fase de edição.

**2. Edição**
- O usuário pode pedir alterações em linguagem natural (`run_edit` aplica a instrução sobre o JSON atual).
- Digitando "ok", a sessão é confirmada e encerrada.
- Limites de segurança: no máximo 5 edições ou 3 mensagens seguidas sem alteração real. Nesses casos a sessão encerra automaticamente.

Os campos de cada projeto (perguntas, tipo, label) ficam em [src/lesson.py](src/lesson.py), então dá pra adaptar o roteiro a outros projetos/editais sem tocar na lógica de conversa.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend / API | FastAPI + Uvicorn |
| LLM / extração de dados | Gemini (principal) com fallback pro Groq, via [`harpy`](https://github.com/Eman-Tedias/harpy) — saída estruturada + guardrail |
| Transcrição de áudio | Whisper (`whisper-large-v3-turbo`, via Groq) |
| Interface de teste | Streamlit (simula uma UI de chat estilo WhatsApp) |
| Canal de produção (parcial) | WhatsApp Cloud API (webhook implementado, ainda não conectado a uma conta ativa) |

## Estrutura

```
app.py                      # Interface Streamlit (simulação de chat, uso local/teste)
src/
  server.py                 # API FastAPI: /message (Streamlit), /webhook e /audio (WhatsApp)
  config.py                 # Env vars e thresholds centralizados
  whatsapp_client.py        # Mecânica da WhatsApp Cloud API (token, envio, download de mídia)
  llm_client.py             # Cliente LLM via harpy (Gemini principal + Groq fallback)
  guardrail_prompt.py       # Prompt de guardrail, compartilhado pelos dois routers
  lesson.py                 # Definição dos campos coletados por projeto
  transcription.py          # Transcrição de áudio (Whisper via Groq)
  main.py                   # CLI simples para testar a conversa no terminal
  deterministic/            # Router como máquina de estados explícita
    schemas.py              # Session, Conversa, Roteiro (textos fixos)
    conversation.py         # Fases de coleta e edição
    extraction.py           # Chamadas ao LLM: extração em lote, edição, fallback, mídia
    prompts.py
  agentic/                  # Router de chamada única por turno (ver seção acima)
    schemas.py
    router.py
    state.py
    lesson_adapter.py
    prompts.py
vendor/
  harpy-0.1.0-py3-none-any.whl  # wheel local (fallback offline; requirements.txt instala do GitHub)
Dockerfile                  # Build do container (WORKDIR muda pra src/ antes de rodar uvicorn)
```

## Configuração

Crie um `.env` na raiz do projeto:

```bash
# Obrigatória. Chave de API do Gemini, modelo principal (via harpy)
GEMINI_API_KEY=

# Obrigatória. Chave de API da Groq, usada como fallback do Gemini e na transcrição de áudio (Whisper)
GROQ_API_KEY=

# Opcional (default gemini-3.5-flash-lite). Modelo Gemini usado como principal
GEMINI_MODEL=gemini-3.5-flash-lite

# Opcional (default openai/gpt-oss-120b). Modelo Groq usado como fallback do Gemini
GROQ_MODEL=openai/gpt-oss-120b

# Opcional (default deterministic). Escolhe a implementação do router: "deterministic"
# (máquina de estados explícita) ou "agentic" (uma chamada por turno decide tudo) -- ver
# "Duas arquiteturas de conversa" acima
ROUTER_MODE=deterministic

# Opcional (default false). Em teste manual: usa modelo/cota separados (TEST_MODEL) pra não
# consumir a cota de produção, e reinicia a sessão do zero a cada mensagem após encerrada
TEST_MODE=false

# Opcional (default gemini-3.1-flash-lite). Modelo usado só quando TEST_MODE=true
TEST_MODEL=gemini-3.1-flash-lite

# Opcional (default true). Liga/desliga a limpeza automática de fotos antigas ao iniciar o servidor
LIMPEZA_FOTOS_HABILITADA=true

# Opcional (default 30). Idade em dias a partir da qual uma foto é apagada pela limpeza automática
LIMPEZA_FOTOS_DIAS=30

# Variáveis abaixo só são necessárias pra integração com WhatsApp

# Token de verificação do webhook na WhatsApp Cloud API
WHATSAPP_VERIFY_TOKEN=

# ID do número de telefone configurado na WhatsApp Cloud API
WHATSAPP_PHONE_NUMBER_ID=

# Token de acesso pra envio de mensagens via WhatsApp Cloud API
WHATSAPP_TOKEN=
```

## Como rodar localmente

```bash
pip install -r requirements.txt
```

Suba a API:

```bash
uvicorn src.server:app --reload
```

Em outro terminal, suba a interface de teste:

```bash
streamlit run app.py
```

Ou teste pelo terminal, sem UI:

```bash
python src/main.py
```

### Integração com WhatsApp (opcional)

O `server.py` já expõe `/webhook` (verificação e recebimento de mensagens da WhatsApp Cloud API), mas essa integração ainda não está conectada a uma conta ativa. Hoje o fluxo é validado via Streamlit. Pra habilitar, configura as variáveis `WHATSAPP_*` listadas em [Configuração](#configuração).

## Status

Projeto em fase de POC/MVP, em desenvolvimento ativo. Já implementado: guardrail contra manipulação de prompt (bloqueia tentativa de exploit/troca de persona em toda chamada de LLM, ver [src/guardrail_prompt.py](src/guardrail_prompt.py)) e mensagens de edição/encerramento com motivo específico (tentativas restantes, razão exata do encerramento, em vez de aviso genérico). Pendente: validação semântica de campos numéricos -- hoje `student_count` é tratado como texto livre na implementação `deterministic`; a `agentic` já rejeita valores não numéricos (fica pendente em vez de gravar lixo), mas nenhuma das duas valida plausibilidade (ex: número negativo ou absurdamente alto).
