import json
import os
import math
from openai import AsyncOpenAI
from agent.tools import tool_registry

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def classify_intent_and_create_plan(query: str):
    print(f"[Agent Step 1] Creating execution plan for query: '{query}'")
    
    tool_schemas = [tool["schema"] for tool in tool_registry.values()]
    
    system_prompt = f'''You are a financial assistant agent that functions as an expert planner. Your job is to translate a user's query into a staged execution plan. The plan will be a list of stages, and each stage will be a list of one or more tool calls that can be executed in parallel.

**Rules for Planning:**
1.  A tool's `type` is either "read" (retrieves data) or "write" (changes data).
2.  Multiple "read" tasks can be placed in the same stage to be run in parallel, as long as they are independent.
3.  A "write" task must be in a stage by itself.
4.  Any task that depends on a "write" task must be in a subsequent stage.

**Available Tools:**
{json.dumps(tool_schemas, indent=2)}

Your response MUST be a JSON object with a single key "plan", which is a list of stages. Each stage is a list of tool calls.

**Example 1: Parallel Reads**
User: "what are the sectors for BBID1 and BBID3 and what are the top 3 energy names for P1?"
Your response:
{{
  "plan": [
    [
      {{
        "tool_name": "lookup_sectors",
        "parameters": {{ "asset_ids": ["BBID1", "BBID3"] }}
      }},
      {{
        "tool_name": "show_top_constituents",
        "parameters": {{ "portfolio_id": "P1", "n": 3, "sector": "Energy" }}
      }}
    ]
  ]
}}

**Example 2: Write and then Read (Dependency)**
User: "set energy to 15% in P1 and then show me the top 6 names in that sector"
Your response:
{{
  "plan": [
    [
      {{
        "tool_name": "adjust_sector_exposure",
        "parameters": {{ "portfolio_id": "P1", "sector": "Energy", "set_weight": 0.15 }}
      }}
    ],
    [
      {{
        "tool_name": "show_top_constituents",
        "parameters": {{ "portfolio_id": "P1", "n": 6, "sector": "Energy" }}
      }}
    ]
  ]
}}

**Example 3: Simple, Rich Query**
User: "show the top 3 constituents in P1 with their sectors and prices"
Your response:
{{
  "plan": [
    [
      {{
        "tool_name": "show_top_constituents",
        "parameters": {{
          "portfolio_id": "P1",
          "n": 3
        }}
      }}
    ]
  ]
}}

**Example 4: Complex Mixed Command**
User: "revert P1, add 1% textiles in P1, move 6% from banking to financials and energy splitting it evenly, then show the top 3 names in textiles and the top 3 names in energy"
Your response:
{{
  "plan": [
    [{{"tool_name": "reset_portfolio", "parameters": {{"portfolio_id": "P1"}} }}],
    [{{"tool_name": "batch_adjust_sectors", "parameters": {{"portfolio_id": "P1", "adjustments": [{{"sector": "Textiles", "increase_by_weight": 0.01}}]}} }}],
    [{{"tool_name": "move_weight", "parameters": {{"portfolio_id": "P1", "from_sector": "Banking", "to_sectors": [{{ "sector": "Financials", "weight_to_add": 0.03 }}, {{ "sector": "Energy", "weight_to_add": 0.03 }}]}} }}],
    [
      {{"tool_name": "show_top_constituents", "parameters": {{"portfolio_id": "P1", "n": 3, "sector": "Textiles"}} }},
      {{"tool_name": "show_top_constituents", "parameters": {{"portfolio_id": "P1", "n": 3, "sector": "Energy"}} }}
    ]
  ]
}}'''

    completion = await client.chat.completions.create(
        model="gpt-4-turbo-preview",
        response_format={ "type": "json_object" },
        temperature=0,
        logprobs=True,
        top_logprobs=2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
    )
    response_text = completion.choices[0].message.content
    print(f"[DEBUG] LLM raw plan response:\n{response_text}")

    # ... (rest of the function is the same)
    usage = completion.usage
    print(f"[Token Usage - Planner] Input: {usage.prompt_tokens}, Output: {usage.completion_tokens}, Total: {usage.total_tokens}")
    avg_confidence = 0.0
    if completion.choices[0].logprobs:
        logprobs_content = completion.choices[0].logprobs.content
        if logprobs_content:
            sum_of_logprobs = sum(lp.logprob for lp in logprobs_content)
            num_tokens = len(logprobs_content)
            avg_logprob = sum_of_logprobs / num_tokens
            avg_confidence = math.exp(avg_logprob)
            print("\n[Logprobs Analysis]")
            print(f"  - Average Per-Token Confidence: {avg_confidence:.2%}")
            print("  [Top 5 Token Details]")
            for i, top_logprob in enumerate(logprobs_content[:5]):
                confidence = math.exp(top_logprob.logprob)
                print(f"  Token {i+1}: '{top_logprob.token}' (Confidence: {confidence:.2%})")
            print("\n")
    response_json = json.loads(response_text)
    plan = response_json.get("plan", [])
    return plan, avg_confidence