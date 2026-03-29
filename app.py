"""
FastAPI wrapper for the opsAgent demo.
"""

import os
import ssl
import uuid
from pathlib import Path

import httpx
import truststore
from dotenv import load_dotenv
from fastapi import FastAPI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

from tools import get_file_content, get_weather, review_pr, search_code_symbol

load_dotenv()
MODEL = os.getenv("AI_MODEL", "undefined")
BASE_URL = os.getenv("AI_BASE_URL", "undefined")
USER = os.getenv("AI_USER", "undefined")
AMTOKEN = os.getenv("AI_AMTOKEN", "undefined")

# HTTP Client Setup
ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
httpx_client = httpx.Client(http2=True, verify=False)

headers = {
    "x-correlation-id": str(uuid.uuid4()),
    "x-usersession-id": str(uuid.uuid4()),
    "Content-Type": "application/json",
    "Authorization": f"session {AMTOKEN}",  # auth method: S2B
}

llm = ChatOpenAI(
    api_key=lambda: "",
    base_url=BASE_URL,
    default_headers=headers,
    http_client=httpx_client,
    model_kwargs={"user": USER},
    model=MODEL,
    temperature=0,
)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_BEHAVIORS_DIR = _PROMPTS_DIR / "behaviors"

agent_executor = create_react_agent(llm, [get_weather, review_pr, search_code_symbol, get_file_content])


def detect_behavior(message: str) -> str | None:
    available = [f.stem for f in _BEHAVIORS_DIR.glob("*.md")]
    if not available:
        return None
    resp = llm.invoke(
        f"Classify the user's intent into one of: {available} or 'none'.\n"
        f"Reply with only the intent name, no explanation.\nUser: {message}"
    )
    result = resp.content.strip().lower()
    return result if result in available else None


def load_system_prompt(behavior: str | None) -> str:
    base = (_PROMPTS_DIR / "system.md").read_text()
    if behavior:
        return base + "\n\n" + (_BEHAVIORS_DIR / f"{behavior}.md").read_text()
    return base

app = FastAPI(title="opsAgent", description="OpsAgent demo API")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    message: str
    tool_calls: list[str] = []


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    behavior = detect_behavior(req.message)
    system_prompt = load_system_prompt(behavior)
    response = agent_executor.invoke({
        "messages": [
            SystemMessage(content=system_prompt),
            HumanMessage(content=req.message),
        ]
    })
    messages = response.get("messages", [])

    # Extract tool call names from intermediate messages
    tool_calls = []
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(tc.get("name", ""))

    # Last message is the final AI response
    final_message = messages[-1].content if messages else ""

    return ChatResponse(message=final_message, tool_calls=tool_calls)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}
