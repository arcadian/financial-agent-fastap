from fastapi import HTTPException
import os
import math
from openai import OpenAI
from agent.classifier import classify_intent_and_extract_params
from agent.tools import tool_registry

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def run_financial_agent(query: str):
    try:
        # Step 1: Classify intent and get confidence score
        tool_calls, confidence = classify_intent_and_extract_params(query)

        # Step 2: Check confidence before proceeding
        CONFIDENCE_THRESHOLD = 0.70 # 70%
        if confidence < CONFIDENCE_THRESHOLD:
            print(f"[Agent Halting] Confidence score {confidence:.2%} is below threshold of {CONFIDENCE_THRESHOLD:.0%}.")
            # Return the error in the format the frontend expects
            return {"results": [{"tool_name": "Agent Error", "error": f"I am not confident enough in my understanding of your request (confidence: {confidence:.2%}). Please try rephrasing it clearly."}]}
        
        if not tool_calls:
            # Return the error in the format the frontend expects
            return {"results": [{"tool_name": "Agent Error", "error": "I am not sure how to interpret your request. I could not identify a valid command or action. Please try rephrasing."}]}

        results = []
        previous_step_result = None
        # Step 3: Execute each tool call sequentially
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool_name")
            parameters = tool_call.get("parameters")

            if tool_name not in tool_registry:
                results.append({"tool_name": tool_name, "error": f"Unknown tool: {tool_name}"})
                continue

            # --- Placeholder Substitution ---
            for key, value in parameters.items():
                if value == "$PREVIOUS_STEP_OUTPUT":
                    # Extract asset IDs from the previous step's result
                    if previous_step_result and isinstance(previous_step_result, list):
                        # Result from show_top_constituents is a list of tuples: (asset_id, {data})
                        parameters[key] = [item[0] for item in previous_step_result]
                    else:
                        raise HTTPException(status_code=400, detail="Could not find valid output from previous step to chain command.")

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
            previous_step_result = result_data # Store result for the next step

            # Step 4: Post-process and append the result of the current tool call
            if tool_name == "adjust_sector_exposure":
                print("[Agent Step 3] Summarizing adjustment results...")
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
            elif tool_name == "lookup_sectors":
                summary = "Sector lookup results:"
                # Convert dict to list of tuples for display
                details_list = list(result_data.items())
                results.append({"tool_name": tool_name, "summary": summary, "details": details_list})
            else:
                results.append({"tool_name": tool_name, "details": result_data})

        # Step 5: Return the list of all results
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
        ],
        logprobs=True,
        top_logprobs=3,
        max_completion_tokens=100
    )
    # Log token usage
    usage = summary_completion.usage
    print(f"[Token Usage - Summarizer] Input: {usage.prompt_tokens}, Output: {usage.completion_tokens}, Total: {usage.total_tokens}")

    # --- Logprobs Analysis ---
    if summary_completion.choices[0].logprobs:
        logprobs_content = summary_completion.choices[0].logprobs.content
        sum_of_logprobs = sum(lp.logprob for lp in logprobs_content)
        num_tokens = len(logprobs_content)
        avg_logprob = sum_of_logprobs / num_tokens
        overall_prob = math.exp(sum_of_logprobs)
        avg_confidence = math.exp(avg_logprob)

        print("[Logprobs Analysis - Summarizer]")
        print(f"  - OVverall Confidence: {overall_prob:.2%}")
        print(f"  - Average Per-Token Confidence: {avg_confidence:.2%}")

    return summary_completion.choices[0].message.content