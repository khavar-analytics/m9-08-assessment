"""
trip_agent.py
=============
A hand-rolled ReAct-style agent that plans a 3-day trip to Porto
under a given budget.  It decides which tools to call and in which
order — no hardwired script.

Architecture
------------
* Three tools: search_flights, search_hotels, calculate
* ReAct loop: Thought → Action → Observation (repeat)
* Step limit: MAX_STEPS (default 10) — the loop exits gracefully if
  the model hasn't finished by then
* Safety mitigation: calculate() uses a whitelist parser (no eval).
  Additionally, all tool arguments supplied by the model are validated
  inside each tool before any data access occurs.
"""

from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tools import calculate, search_flights, search_hotels

# ── Constants ────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
MAX_STEPS = 10          # reliability: agent cannot loop forever
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# ── Tool registry ────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, callable] = {
    "search_flights": search_flights,
    "search_hotels": search_hotels,
    "calculate": calculate,
}

TOOL_SCHEMAS = [
    {
        "name": "search_flights",
        "description": (
            "Search for one-way flights to Porto (OPO). "
            "Returns a list of available flights sorted by price. "
            "Use max_price to cap results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "IATA code of departure airport, e.g. 'LHR'",
                },
                "destination": {
                    "type": "string",
                    "description": "IATA code of arrival airport, e.g. 'OPO'",
                },
                "max_price": {
                    "type": "number",
                    "description": "Optional maximum price in EUR",
                },
            },
            "required": ["origin", "destination"],
        },
    },
    {
        "name": "search_hotels",
        "description": (
            "Search for hotels in Porto. "
            "Returns hotels with a computed total_eur for the stay. "
            "Filter by max_price_per_night and/or min_stars."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nights": {
                    "type": "integer",
                    "description": "Number of nights",
                },
                "max_price_per_night": {
                    "type": "number",
                    "description": "Optional cap on nightly rate in EUR",
                },
                "min_stars": {
                    "type": "integer",
                    "description": "Optional minimum star rating (1–5)",
                },
            },
            "required": ["nights"],
        },
    },
    {
        "name": "calculate",
        "description": (
            "Evaluate a safe arithmetic expression and return the numeric result. "
            "Supports +, -, *, / and parentheses. "
            "Example: '89 + 68 * 2'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression to evaluate",
                },
            },
            "required": ["expression"],
        },
    },
]

# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class StepRecord:
    step: int
    thought: str
    tool_name: str
    tool_input: dict
    tool_result: dict

@dataclass
class AgentResult:
    goal: str
    budget_eur: float
    steps: list[StepRecord] = field(default_factory=list)
    itinerary: dict | None = None
    success: bool = False
    failure_reason: str | None = None
    total_cost_eur: float | None = None
    within_budget: bool | None = None
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

# ── Anthropic API call ───────────────────────────────────────────────────────

def _call_api(messages: list[dict], system: str) -> dict:
    """
    Call the Anthropic messages API.
    Raises RuntimeError on HTTP errors.
    """
    import urllib.request

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 1024,
        "system": system,
        "tools": TOOL_SCHEMAS,
        "messages": messages,
    }).encode()

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"API error {exc.code}: {body}") from exc

# ── Tool dispatch ────────────────────────────────────────────────────────────

def _dispatch(tool_name: str, tool_input: dict) -> dict:
    """
    Dispatch a tool call by name.  Unknown tools return an error dict
    rather than raising, so the agent can handle it gracefully.
    """
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return {"ok": False, "error": f"unknown tool '{tool_name}'"}
    try:
        return fn(**tool_input)
    except TypeError as exc:
        return {"ok": False, "error": f"bad arguments for '{tool_name}': {exc}"}

# ── ReAct loop ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""\
    You are a trip-planning agent. Your job is to plan a 3-day trip to Porto (OPO)
    within the user's budget in EUR.

    You have three tools:
    - search_flights: find flights to OPO
    - search_hotels: find hotels in Porto (use nights=2 for a 3-day trip)
    - calculate: evaluate arithmetic expressions

    Approach:
    1. Search for the cheapest available flight to OPO.
    2. Search for hotels that fit within the remaining budget.
    3. Use calculate to sum up all costs and verify the total is within budget.
    4. When you have all the information, output ONLY a JSON object (no markdown,
       no explanation) with exactly this shape:

    {
      "flight": {
        "airline": "...",
        "flight_id": "...",
        "origin": "...",
        "destination": "OPO",
        "price_eur": 0
      },
      "hotel": {
        "name": "...",
        "stars": 0,
        "nights": 2,
        "price_per_night_eur": 0,
        "total_eur": 0
      },
      "daily_budget_eur": 50,
      "days": 3,
      "cost_breakdown": {
        "flight_eur": 0,
        "hotel_eur": 0,
        "daily_expenses_eur": 0,
        "total_eur": 0
      },
      "within_budget": true
    }

    Rules:
    - daily_budget_eur is fixed at €50/day for food and activities.
    - within_budget is true only if total_eur <= the user's stated budget.
    - If you cannot find a combination within budget, still output the JSON but
      set within_budget to false and pick the closest option.
    - Never invent flight or hotel data — only use what the tools return.
""")


def run_agent(goal: str, budget_eur: float, origin: str = "LHR") -> AgentResult:
    """
    Run the trip-planning agent.

    Parameters
    ----------
    goal       : natural-language goal string (included in the first user message)
    budget_eur : maximum total spend in EUR
    origin     : IATA departure airport (default LHR)

    Returns
    -------
    AgentResult — always returns, never raises
    """
    result = AgentResult(goal=goal, budget_eur=budget_eur)
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"{goal}\n\n"
                f"Budget: €{budget_eur:.0f} total. "
                f"Departure airport: {origin}. "
                f"Trip length: 3 days (2 nights)."
            ),
        }
    ]

    step = 0
    while step < MAX_STEPS:
        step += 1
        print(f"\n── Step {step}/{MAX_STEPS} ──────────────────────────────")

        try:
            response = _call_api(messages, SYSTEM_PROMPT)
        except RuntimeError as exc:
            result.failure_reason = f"API call failed at step {step}: {exc}"
            result.success = False
            return result

        stop_reason = response.get("stop_reason")
        content_blocks = response.get("content", [])

        # ── Collect any text blocks ──────────────────────────────────────────
        text_blocks = [b for b in content_blocks if b.get("type") == "text"]
        tool_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]

        for tb in text_blocks:
            print(f"[Model text] {tb['text'][:300]}")

        # ── Tool-use turn ────────────────────────────────────────────────────
        if stop_reason == "tool_use" and tool_blocks:
            # Build the assistant message with all content blocks
            messages.append({"role": "assistant", "content": content_blocks})

            tool_results_for_api: list[dict] = []

            for tb in tool_blocks:
                tool_name = tb.get("name", "")
                tool_input = tb.get("input", {})
                tool_use_id = tb.get("id", "")

                print(f"[Tool call] {tool_name}({json.dumps(tool_input)})")
                tool_result = _dispatch(tool_name, tool_input)
                print(f"[Tool result] ok={tool_result.get('ok')}  "
                      f"{json.dumps(tool_result)[:200]}")

                # Record for our audit trail
                result.steps.append(StepRecord(
                    step=step,
                    thought=text_blocks[0]["text"] if text_blocks else "",
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_result=tool_result,
                ))

                tool_results_for_api.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(tool_result),
                })

            # Feed all tool results back in one user message
            messages.append({"role": "user", "content": tool_results_for_api})
            continue  # next ReAct step

        # ── End-turn: model returned its final answer ────────────────────────
        if stop_reason in ("end_turn", "stop_sequence") or not tool_blocks:
            final_text = " ".join(b.get("text", "") for b in text_blocks).strip()
            print(f"\n[Final answer]\n{final_text}\n")

            # Try to parse the JSON itinerary out of the response
            json_match = re.search(r"\{[\s\S]*\}", final_text)
            if json_match:
                try:
                    itinerary = json.loads(json_match.group())
                    result.itinerary = itinerary
                    total = itinerary.get("cost_breakdown", {}).get("total_eur")
                    result.total_cost_eur = total
                    result.within_budget = itinerary.get("within_budget")
                    result.success = True
                    return result
                except json.JSONDecodeError as exc:
                    result.failure_reason = f"Could not parse final JSON: {exc}\nRaw: {final_text[:300]}"
                    result.success = False
                    return result
            else:
                result.failure_reason = "Model did not return a JSON itinerary."
                result.success = False
                return result

    # ── Step limit reached ───────────────────────────────────────────────────
    result.failure_reason = (
        f"Agent reached the step limit ({MAX_STEPS}) without producing a final answer. "
        "Partial steps are recorded in result.steps."
    )
    result.success = False
    return result


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    goal = "Plan a 3-day trip to Porto under €600 and give me the total."
    budget = 600.0
    origin = "LHR"

    print("=" * 60)
    print("Trip Concierge Agent")
    print(f"Goal   : {goal}")
    print(f"Budget : €{budget}")
    print(f"Origin : {origin}")
    print("=" * 60)

    result = run_agent(goal, budget, origin)

    print("\n" + "=" * 60)
    print("STRUCTURED RESULT")
    print("=" * 60)
    print(json.dumps({
        "goal": result.goal,
        "budget_eur": result.budget_eur,
        "success": result.success,
        "failure_reason": result.failure_reason,
        "total_cost_eur": result.total_cost_eur,
        "within_budget": result.within_budget,
        "itinerary": result.itinerary,
        "steps_taken": len(result.steps),
        "generated_at": result.generated_at,
    }, indent=2))


if __name__ == "__main__":
    main()
