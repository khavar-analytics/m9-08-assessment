# Trip Concierge Agent
A hand-rolled ReAct-style agent that plans a 3-day trip to Porto under a given
budget.  The agent decides its own tool-call order — there is no hardwired script.

---

## Scenario & Tools
**Scenario:** Trip concierge  
**Goal:** _"Plan a 3-day trip to Porto under €600 and give me the total."_

| Tool | What it does | Why it's needed |
|---|---|---|
| `search_flights` | Searches mock flight data for routes to OPO, filtered by origin and optional price cap | The agent needs real (mock) pricing to pick the cheapest flight |
| `search_hotels` | Searches mock hotel data in Porto, filtered by nightly rate and star rating, and computes `total_eur` per stay | Hotels must be chosen within whatever budget remains after the flight |
| `calculate` | Evaluates an arithmetic expression using a whitelist parser (no `eval`) | The agent must add up flight + hotel + daily expenses to verify the total fits the budget |

The three tools together mirror a real planner's workflow: _find transport → find accommodation → verify the maths_.



## Running the agent

```bash
# 1. Clone & enter the repo
git clone <repo-url>
cd trip-agent

# 2. Install test dependencies
pip install -r requirements.txt

# 3. Set your Anthropic API key  (never commit this)
export ANTHROPIC_API_KEY="sk-ant-..."

# 4. Run the agent
python trip_agent.py

# 5. Run unit tests
python -m pytest tests/ -v
```

---

## Reliability Note — Step Limit & Graceful Failure

`MAX_STEPS = 10` is enforced at the top of the ReAct loop in `trip_agent.py`.

```python
while step < MAX_STEPS:
    step += 1
    ...
```

**What this protects against:**  
If the model gets confused and keeps calling tools in circles — for example, repeatedly calling `calculate` with no progress toward a final answer — the loop exits after 10 iterations, sets `result.success = False`, records the `failure_reason`, and returns the partial `AgentResult` to the caller.  The caller always gets a well-structured object back, never an infinite hang.

**Tool-level failures** are handled the same way.  Every tool returns `{"ok": false, "error": "..."}` rather than raising an exception.  The agent sees the error in the tool-result message and can try a different approach.  If the API itself fails (network error, quota exceeded), `run_agent` catches the `RuntimeError` and populates `result.failure_reason` — it never propagates the exception to the caller.

---

## Safety Note — Whitelist Arithmetic Parser

**Mitigation implemented:** `tools/calculate.py` uses a hand-written recursive-descent parser instead of Python's `eval()`.

**How it works:**

1. A regex whitelist rejects any character that isn't a digit, decimal point, operator (`+ - * /`), or parenthesis:

   ```python
   _ALLOWED = re.compile(r"^[\d\s\+\-\*/\.\(\)]+$")
   if not _ALLOWED.match(expr):
       return {"ok": False, ..., "error": "disallowed characters ..."}
   ```

2. The expression is then tokenised and parsed with correct operator precedence (`*` / `/` before `+ -`) — no `eval`, no `exec`, no `compile`.

3. Expression length is capped at 200 characters to prevent DoS via extremely large inputs.

**What attack it defends against:**  
If a malicious or hallucinating model passes something like `"__import__('os').system('rm -rf /')"` as the `expression` argument, the whitelist check catches the letters immediately and returns an error.  Without this guard, a naive `eval(expression)` implementation would execute arbitrary Python code with the agent process's full privileges.  This is a prompt-injection / tool-argument injection attack: the model (or upstream data that influenced the model) supplies a crafted argument to gain code execution on the host.

**Input validation in all tools:**  
`search_flights` and `search_hotels` also validate every argument before touching the data files — e.g. IATA codes are checked against a whitelist, price caps must be positive numbers, and nights must be in `[1, 30]`.  Bad arguments return an `{"ok": false, ...}` dict rather than allowing a malformed query to hit the filesystem.

---

## Captured Run

The agent chose to call:

1. `search_flights(origin="LHR", destination="OPO")` — fetches all available flights, sorted cheapest first.
2. `search_hotels(nights=2, max_price_per_night=150)` — fetches hotels within a per-night cap that leaves room for flight + daily costs.
3. `calculate("89 + 196 + 50 * 3")` — verifies flight (€89) + hotel (€196) + daily expenses (€50 × 3 days = €150) = €435.

Final structured result (see `captured_run.txt` for full output):

```json
{
  "flight": {
    "airline": "Ryanair",
    "flight_id": "FR-001",
    "origin": "LHR",
    "destination": "OPO",
    "price_eur": 89
  },
  "hotel": {
    "name": "Hotel Eurostars Das Artes",
    "stars": 4,
    "nights": 2,
    "price_per_night_eur": 98,
    "total_eur": 196
  },
  "daily_budget_eur": 50,
  "days": 3,
  "cost_breakdown": {
    "flight_eur": 89,
    "hotel_eur": 196,
    "daily_expenses_eur": 150,
    "total_eur": 435
  },
  "within_budget": true
}
```

**€435 total — €165 under the €600 budget. ✓**

The agent made 3 tool calls and finished in 3 steps (well under the 10-step limit).  The output is valid JSON that any downstream program can parse and consume.

---

## Grading Checklist

| Requirement | Where it is |
|---|---|
| Three tools | `tools/search_flights.py`, `tools/search_hotels.py`, `tools/calculate.py` |
| Multi-step goal solved by agent's own choices | `trip_agent.py` — ReAct loop, no hardwired order |
| Structured output | JSON schema in `SYSTEM_PROMPT`; `AgentResult.itinerary` |
| Step limit | `MAX_STEPS = 10` in `trip_agent.py` |
| Safety mitigation | Whitelist parser in `calculate.py`; argument validation in all tools |
| README | This file |
| Captured run | `captured_run.txt` |
| No API key in repo | `ANTHROPIC_API_KEY` read from environment only |
