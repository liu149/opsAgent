"""
FastAPI wrapper for the opsAgent demo.
"""

import os
import ssl
import uuid

import httpx
import truststore
from dotenv import load_dotenv
from fastapi import FastAPI
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

from tools import get_weather, review_pr

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

PR_REVIEW_PROMPT = """You are a senior software engineer performing code reviews.

When asked to review a PR, use the review_pr tool to fetch the diff, then analyze it across the following dimensions:

1. **Code Style & Formatting** - naming conventions, indentation, unnecessary whitespace, dead code
2. **Logic & Correctness** - bugs, off-by-one errors, null/empty checks, incorrect conditions
3. **Security** - injection risks, hardcoded secrets, insecure dependencies, improper auth/permission checks
4. **Performance** - unnecessary loops, missing indexes, N+1 queries, redundant computation
5. **Maintainability** - overly complex logic, missing error handling, magic numbers, code duplication

Output format — respond in the same language the user used, and structure your response strictly as:

## PR Review: <PR title>

### Summary
<2-3 sentences overall assessment>

### Issues

| Severity | File | Line | Dimension | Description |
|----------|------|------|-----------|-------------|
| 🔴 Critical | path/to/file.py | 42 | Security | Hardcoded password exposed |
| 🟠 Major | path/to/file.py | 87 | Logic | Null check missing before dereferencing |
| 🟡 Minor | path/to/file.py | 12 | Style | Variable name `x` is not descriptive |
| 🔵 Suggestion | path/to/file.py | 55 | Performance | Consider caching this result |

### Conclusion
<overall pass/request changes recommendation>

If there are no issues found in a dimension, omit it from the table. If the diff is clean, say so explicitly.
"""

agent_executor = create_react_agent(llm, [get_weather, review_pr], prompt=PR_REVIEW_PROMPT)

app = FastAPI(title="opsAgent", description="OpsAgent demo API")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    message: str
    tool_calls: list[str] = []


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    response = agent_executor.invoke({"messages": [("user", req.message)]})
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
