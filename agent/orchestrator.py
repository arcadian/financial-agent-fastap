from fastapi import HTTPException
import os
from openai import OpenAI
from agent.classifier import classify_intent_and_extract_params
from agent.tools import tool_registry

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def run_financial_agent(query: str):
    try:
        # Step 1: Classify intent and extract parameters for one or more tool calls
        tool_calls = classify_intent_and_extract_params(query)
        
        if not tool_calls:
            return {"error": "Could not understand the request. Please try again."}

        results = []
        # Step 2: Execute each tool call sequentially
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool_name")
            parameters = tool_call.get("parameters")

            if tool_name not in tool_registry:
                results.append({"tool_name": tool_name, "error": f"Unknown tool: {tool_name}"})
                continue

            # --- Parameter Validation Step ---
            tool_schema = tool_registry[tool_name]["schema"]
            required_params = tool_schema.get("required", [])
            missing_params = [p for p in required_params if p not in parameters]
            if missing_params:
                error_message = f"Missing required parameters for tool '{tool_name}': {', '.join(missing_params)}"
                results.append({"tool_name": tool_name, "error": error_message})
                continue # Skip to the next tool call

            print(f"[Agent Step 2] Executing tool: '{tool_name}' with params: {parameters}")
            tool_function = tool_registry[tool_name]["function"]
            result_data = tool_function(**parameters)

            # Step 3: Post-process results (e.g., summarize adjustments)
            if tool_name == "adjust_sector_exposure":
                print("[Agent Step 3] Summarizing adjustment results...")
                # The tool now returns a dictionary with changed_assets and the final_target_weight
                summary = _summarize_adjustment(parameters, result_data["changed_assets"], result_data["final_target_weight"])
                results.append({"tool_name": tool_name, "summary": summary, "details": result_data["changed_assets"][:5]})
            elif tool_name == "move_weight":
                print("[Agent Step 3] Summarizing move results...")
                summary = f"Successfully moved {result_data['amount']:.2%} from {result_data['from_sector']} to {[t['sector'] for t in result_data['to_sectors']]}."
                results.append({"tool_name": tool_name, "summary": summary})
            elif tool_name == "reset_portfolio":
                results.append({"tool_name": tool_name, "summary": result_data["message"]})
            elif tool_name == "batch_adjust_sectors":
                results.append({"tool_name": tool_name, "summary": result_data["message"]})
            elif tool_name == "show_top_constituents":
                params = tool_call.get("parameters", {})
                n = params.get("n", 20)
                portfolio_id = params.get("portfolio_id")
                sector = params.get("sector")
                
                summary = f"Top {n} constituents by weight for portfolio {portfolio_id}"
                if sector:
                    summary += f" in the {sector} sector:"
                else:
                    summary += ":"
                results.append({"tool_name": tool_name, "summary": summary, "details": result_data})
            else:
                results.append({"tool_name": tool_name, "details": result_data})

        # Step 4: Return the list of results
        return {"results": results}

    except Exception as e:
        print(f"[DEBUG] An error occurred in the agent: {str(e)}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

def _summarize_adjustment(parameters, changed_assets, final_target_weight):
    no_change = all(abs(c['new_weight'] - c['old_weight']) < 1e-6 for c in changed_assets)
    if no_change:
        return "No changes were made to the portfolio as it already meets the specified target."

    summary_prompt_data = "\n".join([f"- {c['asset_id']}: Weight changed from {c['old_weight']:.4f} to {c['new_weight']:.4f}" for c in changed_assets])
    summary_completion = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a financial analyst..."}, # Abbreviated for brevity
            {"role": "user", "content": f"Sector: {parameters.get('sector')}\nFinal Target Weight: {final_target_weight:.2%}\n\nAssets Re-allocated:\n{summary_prompt_data}"}
        ]
    )
    # Log token usage
    usage = summary_completion.usage
    print(f"[Token Usage - Summarizer] Input: {usage.prompt_tokens}, Output: {usage.completion_tokens}, Total: {usage.total_tokens}")
    return summary_completion.choices[0].message.content
