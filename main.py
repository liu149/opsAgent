"""
demo
"""

import os
import ssl
import uuid

import httpx
import truststore
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from tools import get_weather

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

tools = [get_weather]


if __name__ == "__main__":

    print(f"model: {MODEL}")
    print(f"base_url: {BASE_URL}\n")

    # Initialize the LLM and do some basic checking
    llm = ChatOpenAI(
        api_key=lambda: "",
        base_url=BASE_URL,
        default_headers=headers,
        http_client=httpx_client,
        model_kwargs={"user": USER},
        model=MODEL,
        temperature=0,
    )

    agent_executor = create_react_agent(llm, tools)
    response = agent_executor.invoke({"messages":[("user", "how is the weather of beijing")]})
    print(response)