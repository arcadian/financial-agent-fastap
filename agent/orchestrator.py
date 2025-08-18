from fastapi import HTTPException
import os
import math
import asyncio
from openai import AsyncOpenAI
from agent.classifier import classify_intent_and_create_plan
from agent.tools import tool_registry
from portfolio.management import working_portfolio_cache, SECTORS

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def run_financial_agent(query: str):
    try:
        plan, confidence = await classify_intent_and_create_plan(query)

        CONFIDENCE_THRESHOLD = 0.70
        if confidence < CONFIDENCE_THRESHOLD:
            return {"results": [{"tool_name": "Agent Error", "error": f"Confidence {confidence:.2%} is below threshold. Please rephrase."}]}
        
        if not plan:
            return {"results": [{"tool_name": "Agent Error", "error": "Could not create a valid plan from the request."}]}

        all_results = []
        previous_stage_results = None
        portfolio_id_for_logging = None

        for i, stage in enumerate(plan):
            print(f"--- Executing Stage {i+1}/{len(plan)} (Tasks: {len(stage)}) ---")
            
            async def run_single_tool_call(tool_call):
                nonlocal portfolio_id_for_logging
                tool_name = tool_call.get("tool_name")
                parameters = tool_call.get("parameters", {})
                if not portfolio_id_for_logging:
                    portfolio_id_for_logging = parameters.get("portfolio_id")

                for key, value in parameters.items():
                    if value == "$PREVIOUS_STAGE_OUTPUT":
                        if previous_stage_results and isinstance(previous_stage_results, list) and previous_stage_results[0].get("details"):
                            first_result_details = previous_stage_results[0]["details"]
                            parameters[key] = [item[0] for item in first_result_details]
                        else:
                            return {"tool_name": tool_name, "error": "Chained command failed: No valid output from previous stage."}

                tool_schema = tool_registry[tool_name]["schema"]
                required_params = tool_schema.get("required", [])
                if any(p not in parameters for p in required_params):
                    return {"tool_name": tool_name, "error": f"Missing required parameters."}

                print(f"[Agent] Concurrently Executing: {tool_name}")
                tool_function = tool_registry[tool_name]["function"]
                
                try:
                    result_data = await asyncio.to_thread(tool_function, **parameters)
                    return await _format_result(tool_name, tool_call, result_data)
                except Exception as e:
                    return {"tool_name": tool_name, "error": str(e)}

            stage_results = await asyncio.gather(*[run_single_tool_call(tc) for tc in stage])
            
            all_results.extend(stage_results)
            previous_stage_results = stage_results

            if portfolio_id_for_logging:
                if any(tool_registry[tc["tool_name"]]["schema"].get("type") == "write" for tc in stage):
                    log_portfolio_state_summary(portfolio_id_for_logging)
                    check_portfolio_invariant(portfolio_id_for_logging)

        return {"results": all_results}

    except Exception as e:
        print(f"[DEBUG] An error occurred in the agent: {str(e)}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

async def _format_result(tool_name, tool_call, result_data):
    if tool_name == "adjust_sector_exposure":
        summary = await _summarize_adjustment(tool_call.get("parameters"), result_data["changed_assets"], result_data["final_target_weight"])
        return {"tool_name": tool_name, "summary": summary, "details": result_data["changed_assets"][:5]}
    elif tool_name == "move_weight":
        summary = f"Successfully moved {result_data['amount']:.2%} from {result_data['from_sector']} to {[t['sector'] for t in result_data['to_sectors']]}."
        return {"tool_name": tool_name, "summary": summary}
    elif tool_name == "lookup_sectors":
        summary = "Sector lookup results:"
        details_list = list(result_data.items())
        return {"tool_name": tool_name, "summary": summary, "details": details_list}
    elif tool_name == "lookup_prices":
        summary = "Price lookup results:"
        details_list = list(result_data.items())
        return {"tool_name": tool_name, "summary": summary, "details": details_list}
    elif tool_name == "show_top_constituents":
        params = tool_call.get("parameters", {})
        summary = f"Top {params.get('n', 20)} constituents by weight for portfolio {params.get('portfolio_id')}"
        if params.get("sector"):
            summary += f" in the {params.get('sector')} sector:"
        return {"tool_name": tool_name, "summary": summary, "details": result_data}
    elif tool_name in ["reset_portfolio", "batch_adjust_sectors"]:
        return {"tool_name": tool_name, "summary": result_data["message"]}
    else:
        return {"tool_name": tool_name, "details": result_data}

async def _summarize_adjustment(parameters, changed_assets, final_target_weight):
    no_change = all(abs(c['new_weight'] - c['old_weight']) < 1e-6 for c in changed_assets)
    if no_change:
        return "No changes were made to the portfolio as it already meets the specified target."
    summary_prompt_data = "\n".join([f"- {c['asset_id']}: Weight changed from {c['old_weight']:.4f} to {c['new_weight']:.4f}" for c in changed_assets])
    summary_completion = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0,
        logprobs=True,
        messages=[
            {"role": "system", "content": "You are a financial analyst..."},
            {"role": "user", "content": f"Sector: {parameters.get('sector')}\nFinal Target Weight: {final_target_weight:.2%}\n\nAssets Re-allocated:\n{summary_prompt_data}"}
        ]
    )
    return summary_completion.choices[0].message.content

def log_portfolio_state_summary(portfolio_id: str):
    """Prints a debug summary of the top 2 constituents per sector."""
    print(f"\n--- DEBUG STATE LOG: Portfolio '{portfolio_id}' ---")
    if portfolio_id not in working_portfolio_cache:
        print("  Portfolio not found in cache.")
        return

    portfolio = working_portfolio_cache[portfolio_id]
    for sector in SECTORS:
        sector_assets = sorted(
            [item for item in portfolio.items() if item[1]["sector"] == sector],
            key=lambda item: item[1]["weight"], 
            reverse=True
        )
        print(f"  Sector: {sector} (Top 2)")
        if not sector_assets:
            print("    - No assets in this sector.")
            continue
        for asset_id, data in sector_assets[:2]:
            print(f"    - {asset_id}: {(data['weight'] * 100):.4f}%")
    print("---------------------------------------\n")

def check_portfolio_invariant(portfolio_id: str):
    """Checks that the total portfolio weight sums to 1.0."""
    if portfolio_id not in working_portfolio_cache:
        return # Nothing to check
    
    total_weight = sum(data["weight"] for data in working_portfolio_cache[portfolio_id].values())
    print(f"[INVARIANT CHECK] Total portfolio weight for '{portfolio_id}' is: {total_weight:.6%}")

    if abs(total_weight - 1.0) > 1e-9:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! ERROR: PORTFOLIO INVARIANT VIOLATED !!!")
        print(f"!!! Total weight is {total_weight}, not 1.0 !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")