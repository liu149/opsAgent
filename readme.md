# opsAgent

A demo ops agent built with LangGraph ReAct, exposed via FastAPI.

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the required environment variables:

```
AI_MODEL=
AI_BASE_URL=
AI_USER=
AI_AMTOKEN=
```

## Start

```bash
uvicorn app:app --reload
```

The API will be available at `http://localhost:8000`.

Interactive docs: `http://localhost:8000/docs`

## API

### POST /chat

Send a message to the agent.

**Request**
```json
{
  "message": "北京天气怎么样"
}
```

**Response**
```json
{
  "message": "北京天气晴，25℃",
  "tool_calls": ["get_weather"]
}
```

### GET /health

Returns service status and current model name.
