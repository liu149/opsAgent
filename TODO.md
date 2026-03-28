# TODO

## Complex Problem Decomposition & Multi-Behavior Orchestration

### Background

Current `detect_behavior` returns a single intent, unable to handle questions spanning multiple scenarios.
Example: "k8s pod crashed after merging this PR, help me diagnose" involves PR review + k8s diagnosis + log analysis simultaneously.

### Goal

Support automatic decomposition and serial execution of complex questions, without changing the behavior of the single-task path.

### New Files

```
prompts/
├── decompose.md               # Task decomposition LLM prompt
└── behaviors/
    └── k8s_diagnosis.md       # Extension example (placeholder)
```

**`prompts/decompose.md`** should:
- Inject `{available_behaviors}` list at runtime
- Require LLM to output JSON: `{"is_complex": bool, "subtasks": [{"behavior": str, "focus": str}]}`
- Rules: subtask order reflects dependencies; behavior must come from available list or "none"; fallback on parse failure

### Changes to `app.py`

**1. Replace `detect_behavior` with `plan_subtasks`**

```python
def plan_subtasks(message: str) -> list[dict]:
    available = [f.stem for f in _BEHAVIORS_DIR.glob("*.md")]
    decompose_prompt = (_PROMPTS_DIR / "decompose.md").read_text()
    decompose_prompt = decompose_prompt.format(available_behaviors=available)
    resp = llm.invoke([SystemMessage(content=decompose_prompt), HumanMessage(content=message)])
    try:
        return json.loads(resp.content)["subtasks"]
    except Exception:
        return [{"behavior": None, "focus": message}]  # fallback
```

**2. Add `focus` parameter to `load_system_prompt`**

```python
def load_system_prompt(behavior: str | None, focus: str = "") -> str:
    base = (_PROMPTS_DIR / "system.md").read_text()
    prompt = base
    if behavior:
        prompt += "\n\n" + (_BEHAVIORS_DIR / f"{behavior}.md").read_text()
    if focus:
        prompt += f"\n\n## Current Task Focus\n{focus}"
    return prompt
```

**3. Add `run_subtask` and `summarize_results`**

```python
def run_subtask(original_message: str, subtask: dict, context: str = "") -> str:
    system_prompt = load_system_prompt(subtask.get("behavior"), subtask.get("focus", ""))
    user_message = original_message
    if context:
        user_message += f"\n\n---\nPrevious analysis for context:\n{context}"
    response = agent_executor.invoke({
        "messages": [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    })
    messages = response.get("messages", [])
    return messages[-1].content if messages else ""

def summarize_results(original_message: str, results: list[dict]) -> str:
    combined = "\n\n".join(f"## {r['behavior']}\n{r['result']}" for r in results)
    resp = llm.invoke([
        SystemMessage(content="You are an ops assistant. Combine the following analysis results into a single coherent report."),
        HumanMessage(content=f"Original question: {original_message}\n\n{combined}")
    ])
    return resp.content
```

**4. Update `/chat` endpoint**

```python
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    subtasks = plan_subtasks(req.message)
    results = []
    context_so_far = ""
    for subtask in subtasks:
        result = run_subtask(req.message, subtask, context=context_so_far)
        results.append({"behavior": subtask.get("behavior", "none"), "result": result})
        context_so_far += f"\n### {subtask.get('behavior')} result\n{result}\n"
    if len(results) == 1:
        return ChatResponse(message=results[0]["result"])
    return ChatResponse(message=summarize_results(req.message, results))
```

### Flow

```
POST /chat
    ↓
plan_subtasks()  →  LLM + decompose.md  →  [{behavior, focus}, ...]
    ↓
Serial execution (each subtask carries previous results as context):
  subtask[0] → load_system_prompt + agent.invoke → result_0
  subtask[1] → load_system_prompt + agent.invoke(+context) → result_1
  subtask[2] → load_system_prompt + agent.invoke(+context) → result_2
    ↓
len==1 → return directly (single-task path unchanged)
len>1  → summarize_results() → final report
```

### How to Extend

Adding a new capability only requires:
1. Create `prompts/behaviors/xxx.md`
2. Register the corresponding tool in `tools.py`
3. Zero code changes — `plan_subtasks` discovers new behavior files automatically
