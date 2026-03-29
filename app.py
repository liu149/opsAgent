"""
FastAPI wrapper for the opsAgent demo.
"""

import json
import os
import ssl
import uuid
from pathlib import Path
from typing import Any

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

# All available tools by name — register new tools here
_ALL_TOOLS = {
    "get_weather": get_weather,
    "review_pr": review_pr,
    "search_code_symbol": search_code_symbol,
    "get_file_content": get_file_content,
}


def _load_behavior_tools(behavior: str) -> list:
    cfg = _BEHAVIORS_DIR / f"{behavior}.json"
    if not cfg.exists():
        return []
    names = json.loads(cfg.read_text()).get("tools", [])
    return [_ALL_TOOLS[n] for n in names if n in _ALL_TOOLS]


# Pre-create one specialized agent per behavior at startup
_AGENTS: dict[str, Any] = {}
for _cfg in _BEHAVIORS_DIR.glob("*.json"):
    _b = _cfg.stem
    if _b == "default":
        continue
    _tools = _load_behavior_tools(_b)
    if _tools:
        _AGENTS[_b] = create_react_agent(llm, _tools)

_DEFAULT_AGENT = create_react_agent(llm, _load_behavior_tools("default") or [get_weather])


def load_system_prompt(behavior: str | None, focus: str = "") -> str:
    base = (_PROMPTS_DIR / "system.md").read_text()
    prompt = base
    if behavior:
        md = _BEHAVIORS_DIR / f"{behavior}.md"
        if md.exists():
            prompt += "\n\n" + md.read_text()
    if focus:
        prompt += f"\n\n## Current Task Focus\n{focus}"
    return prompt


def plan_subtasks(message: str) -> list[dict]:
    available = [f.stem for f in _BEHAVIORS_DIR.glob("*.md")]
    decompose_prompt = (_PROMPTS_DIR / "decompose.md").read_text().format(
        available_behaviors=available
    )
    resp = llm.invoke([SystemMessage(content=decompose_prompt), HumanMessage(content=message)])
    try:
        return json.loads(resp.content)["subtasks"]
    except Exception:
        return [{"behavior": None, "focus": message}]


def run_subtask(original_message: str, subtask: dict, context: str = "") -> tuple[str, list[str]]:
    behavior = subtask.get("behavior")
    focus = subtask.get("focus", "")
    agent = _AGENTS.get(behavior, _DEFAULT_AGENT) if behavior else _DEFAULT_AGENT
    system_prompt = load_system_prompt(behavior, focus)
    user_message = original_message
    if context:
        user_message += f"\n\n---\nPrevious analysis:\n{context}"

    response = agent.invoke({
        "messages": [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    })
    messages = response.get("messages", [])

    tool_calls = []
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(tc.get("name", ""))

    final = messages[-1].content if messages else ""
    return final, tool_calls


def synthesize(original_message: str, results: list[dict]) -> str:
    combined = "\n\n".join(f"## {r['behavior']}\n{r['result']}" for r in results)
    resp = llm.invoke([
        SystemMessage(content="Combine the following analysis results into a single coherent ops report."),
        HumanMessage(content=f"Original question: {original_message}\n\n{combined}"),
    ])
    return resp.content


app = FastAPI(title="opsAgent", description="OpsAgent demo API")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    message: str
    tool_calls: list[str] = []


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    subtasks = plan_subtasks(req.message)
    results = []
    all_tool_calls: list[str] = []
    context_so_far = ""

    for subtask in subtasks:
        result, tool_calls = run_subtask(req.message, subtask, context=context_so_far)
        results.append({"behavior": subtask.get("behavior", "none"), "result": result})
        all_tool_calls.extend(tool_calls)
        context_so_far += f"\n### {subtask.get('behavior')} result\n{result}\n"

    if len(results) == 1:
        return ChatResponse(message=results[0]["result"], tool_calls=all_tool_calls)

    return ChatResponse(message=synthesize(req.message, results), tool_calls=all_tool_calls)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}
