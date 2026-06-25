import uuid
import requests
import streamlit as st

API_URL = "http://localhost:8000/message"
AUDIO_URL = "http://localhost:8000/audio"

st.set_page_config(page_title="Registro de Aula", page_icon="📚", layout="centered")

st.markdown("""
<style>
[data-testid="stChatMessageContent"] p { font-size: 0.95rem; }
section.main { background-color: #ece5dd; }
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    flex-direction: row;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    flex-direction: row-reverse;
}
</style>
""", unsafe_allow_html=True)

st.title("Registro de Aula")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "started" not in st.session_state:
    st.session_state.started = False

def call_api(text: str) -> str:
    try:
        resp = requests.post(API_URL, json={
            "session_id": st.session_state.session_id,
            "text": text,
        }, timeout=30)
        resp.raise_for_status()
        return resp.json().get("reply", "")
    except requests.exceptions.ConnectionError:
        return "Servidor não encontrado. Certifique-se de que server.py está rodando em localhost:8000."
    except Exception as e:
        return f"Erro: {e}"

if not st.session_state.started:
    reply = call_api("")
    if reply:
        st.session_state.messages.append({"role": "assistant", "content": reply})
    st.session_state.started = True

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

def call_audio_api(audio_bytes: bytes) -> tuple[str, str]:
    try:
        resp = requests.post(
            AUDIO_URL,
            data={"session_id": st.session_state.session_id},
            files={"audio": ("audio.ogg", audio_bytes, "audio/ogg")},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("reply", ""), data.get("transcript", "")
    except requests.exceptions.ConnectionError:
        return "Servidor não encontrado. Certifique-se de que server.py está rodando em localhost:8000.", ""
    except Exception as e:
        return f"Erro: {e}", ""

if prompt := st.chat_input("Digite sua mensagem..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(""):
            reply = call_api(prompt)
        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})

audio_value = st.audio_input("Ou grave um áudio")
if audio_value is not None:
    audio_bytes = audio_value.read()
    with st.chat_message("user"):
        st.audio(audio_value)
    with st.chat_message("assistant"):
        with st.spinner(""):
            reply, transcript = call_audio_api(audio_bytes)
        if transcript:
            st.caption(f"_Transcrição: {transcript}_")
        st.markdown(reply)
    st.session_state.messages.append({"role": "user", "content": f"[Áudio] {transcript}"})
    st.session_state.messages.append({"role": "assistant", "content": reply})
