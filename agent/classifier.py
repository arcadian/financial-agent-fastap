import json
import os
from openai import OpenAI
from agent.tools import tool_registry

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def classify_intent_and_extract_params(query: str):
    print(f"[Agent Step 1] Classifying intent for query: '{query}'")
    
    tool_schemas = [tool["schema"] for tool in tool_registry.values()]
    
    system_prompt = f'''You are a financial assistant agent. Your job is to translate a user's natural language query into a list of one or more structured API calls. You must identify the correct tools and extract the necessary parameters from the list of available tools.

{json.dumps(tool_schemas, indent=2)}

Your response MUST be a JSON object containing a single key "tool_calls", which is a list of objects. Each object in the list must have two keys: "tool_name" and "parameters".

**CRITICAL RULE: You must extract all parameters, including `portfolio_id`, directly from the user's query. If a required parameter like `portfolio_id` is not present, do not invent one or assume a default. Omit it from the parameters object.**

Example of a multi-command query:
User: "in P1, set energy to 15% and then show me the top 10 constituents in that sector"
Your response:
{{
  "tool_calls": [
    {{
      "tool_name": "adjust_sector_exposure",
      "parameters": {{
        "portfolio_id": "P1",
        "sector": "Energy",
        "set_weight": 0.15
      }}
    }},
    {{
      "tool_name": "show_top_constituents",
      "parameters": {{
        "portfolio_id": "P1",
        "n": 10,
        "sector": "Energy"
      }}
    }}
  ]
}}

Example where portfolio_id is MISSING:
User: "increase textiles by 5%"
Your response:
{{
  "tool_calls": [
    {{
      "tool_name": "batch_adjust_sectors",
      "parameters": {{
        "adjustments": [
          {{ "sector": "Textiles", "increase_by_weight": 0.05 }}
        ]
      }}
    }}
  ]
}}

User: "shift 5% from financials to energy 2% and textiles 3% in P1"
Your response:
{{
  "tool_calls": [
    {{
      "tool_name": "move_weight",
      "parameters": {{
        "portfolio_id": "P1",
        "from_sector": "Financials",
        "to_sectors": [
          {{ "sector": "Energy", "weight_to_add": 0.02 }},
          {{ "sector": "Textiles", "weight_to_add": 0.03 }}
        ]
      }}
    }}
  ]
}}

User: "in P1, add 2% to energy and decrease financials by 1%"
Your response:
{{
  "tool_calls": [
    {{
      "tool_name": "batch_adjust_sectors",
      "parameters": {{
        "portfolio_id": "P1",
        "adjustments": [
          {{ "sector": "Energy", "increase_by_weight": 0.02 }},
          {{ "sector": "Financials", "decrease_by_weight": 0.01 }}
        ]
      }}
    }}
  ]
}}'''

    completion = client.chat.completions.create(
        model="gpt-4-turbo-preview", # Using a more advanced model for better multi-command parsing
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
    )
    response_text = completion.choices[0].message.content
    print(f"[DEBUG] LLM raw classification response:\n{response_text}")

    # Log token usage
    usage = completion.usage
    print(f"[Token Usage - Classifier] Input: {usage.prompt_tokens}, Output: {usage.completion_tokens}, Total: {usage.total_tokens}")

    response_json = json.loads(response_text)
    return response_json.get("tool_calls", [])