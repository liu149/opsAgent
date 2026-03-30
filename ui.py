"""
Streamlit chat UI for opsAgent.
"""

import json
import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="opsAgent", page_icon="🤖", layout="centered")
st.title("opsAgent")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("tool_calls"):
            with st.expander(f"Tools used: {', '.join(msg['tool_calls'])}"):
                for t in msg["tool_calls"]:
                    st.code(t)

# Chat input
if prompt := st.chat_input("Ask opsAgent..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        status = st.empty()
        answer_placeholder = st.empty()
        answer = ""
        tool_calls = []

        try:
            with requests.post(
                f"{BACKEND_URL}/chat/stream",
                json={"message": prompt},
                stream=True,
                timeout=1200,
            ) as resp:
                resp.raise_for_status()
                heartbeat_count = 0
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith(b": heartbeat"):
                        # Nudge Streamlit UI to keep the WebSocket alive
                        heartbeat_count += 1
                        dots = "." * (heartbeat_count % 4)
                        status.info(f"Processing{dots}")
                        continue
                    if not line.startswith(b"data: "):
                        continue
                    data_str = line[6:].decode()
                    if data_str == "[DONE]":
                        break
                    event = json.loads(data_str)
                    if event["type"] == "status":
                        status.info(event["content"])
                    elif event["type"] == "error":
                        status.error(event["content"])
                    elif event["type"] == "result":
                        status.empty()
                        answer = event["content"]
                        tool_calls = event.get("tool_calls", [])
                        answer_placeholder.markdown(answer)

        except requests.exceptions.ConnectionError:
            answer = f"Cannot connect to backend at `{BACKEND_URL}`. Make sure the server is running."
            answer_placeholder.error(answer)
        except Exception as e:
            answer = f"Error: {e}"
            answer_placeholder.error(answer)

        if tool_calls:
            with st.expander(f"Tools used: {', '.join(tool_calls)}"):
                for t in tool_calls:
                    st.code(t)

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "tool_calls": tool_calls,
    })
