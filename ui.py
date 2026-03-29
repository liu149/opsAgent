"""
Streamlit chat UI for opsAgent.
"""

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
            with st.expander(f"🔧 Tools used: {', '.join(msg['tool_calls'])}"):
                for t in msg["tool_calls"]:
                    st.code(t)

# Chat input
if prompt := st.chat_input("Ask opsAgent..."):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call backend
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                resp = requests.post(
                    f"{BACKEND_URL}/chat",
                    json={"message": prompt},
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
                answer = data.get("message", "")
                tool_calls = data.get("tool_calls", [])
            except requests.exceptions.ConnectionError:
                answer = f"Cannot connect to backend at `{BACKEND_URL}`. Make sure the server is running."
                tool_calls = []
            except Exception as e:
                answer = f"Error: {e}"
                tool_calls = []

        st.markdown(answer)
        if tool_calls:
            with st.expander(f"🔧 Tools used: {', '.join(tool_calls)}"):
                for t in tool_calls:
                    st.code(t)

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "tool_calls": tool_calls,
    })
