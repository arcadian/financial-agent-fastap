import asyncio
import json
import os

import jmespath
import openai
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from openai import AsyncOpenAI

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------
# Mock Tool Implementations
# ---------------------------

SECTORS = ["Tech", "Health", "Finance"]

async def _adjust_portfolio_sector(portfolio_id, sector, set_weight=None, increase_by_weight=None, decrease_by_weight=None):
    print(f"[TOOL] Adjust sector {sector} in {portfolio_id}: set={set_weight}, +={increase_by_weight}, -={decrease_by_weight}")
    return {"portfolio": portfolio_id, "sector": sector, "set_weight": set_weight}

async def _show_top_constituents(portfolio_id, n=20, sector=None):
    print(f"[TOOL] Show top {n} constituents for {portfolio_id} (sector={sector})")
    return [
        {"symbol": "AAPL", "weight": 0.4, "sector": "Tech"},
        {"symbol": "MSFT", "weight": 0.35, "sector": "Tech"},
        {"symbol": "IBM", "weight": 0.25, "sector": "Tech"}
    ][:n]

async def _move_weight(portfolio_id, from_sector, to_sectors):
    print(f"[TOOL] Move weight from {from_sector} to {to_sectors} in {portfolio_id}")
    return {"portfolio": portfolio_id, "from_sector": from_sector, "to_sectors": to_sectors}

async def _reset_portfolio(portfolio_id):
    print(f"[TOOL] Reset portfolio {portfolio_id}")
    return {"portfolio": portfolio_id}

async def _batch_adjust_sectors(portfolio_id, adjustments):
    print(f"[TOOL] Batch adjust sectors in {portfolio_id}: {adjustments}")
    return {"portfolio": portfolio_id, "adjustments": adjustments}

async def _create_portfolio(portfolio_id, initial_composition):
    print(f"[TOOL] Create portfolio {portfolio_id} with {initial_composition}")
    return {"portfolio": portfolio_id, "composition": initial_composition}

async def _manage_assets_by_quantity(portfolio_id, operations):
    print(f"[TOOL] Manage assets in {portfolio_id}: {operations}")
    return {"portfolio": portfolio_id, "operations": operations}

async def _lookup_sectors(asset_ids):
    print(f"[TOOL] Lookup sectors for: {asset_ids}")
    return {a: "Tech" for a in asset_ids}

async def _lookup_prices(asset_ids):
    print(f"[TOOL] Lookup prices for: {asset_ids}")
    return {a: 100.0 for a in asset_ids}

# ---------------------------
# Tool Registry with Arguments
# ---------------------------

tool_registry = {
    "adjust_sector_exposure": {
        "function": _adjust_portfolio_sector,
        "schema": {
            "name": "adjust_sector_exposure",
            "description": "Adjusts the weight of a specific sector.",
            "type": "write",
            "parameters": {
                "portfolio_id": {"type": "string", "description": "Portfolio ID"},
                "sector": {"type": "string", "description": f"Sector ({SECTORS})"},
                "set_weight": {"type": "float", "description": "Absolute target weight"},
                "increase_by_weight": {"type": "float", "description": "Increase weight by"},
                "decrease_by_weight": {"type": "float", "description": "Decrease weight by"}
            },
            "required": ["portfolio_id", "sector"]
        }
    },
    "show_top_constituents": {
        "function": _show_top_constituents,
        "schema": {
            "name": "show_top_constituents",
            "description": "Shows top N constituents of a portfolio.",
            "type": "read",
            "parameters": {
                "portfolio_id": {"type": "string"},
                "n": {"type": "integer"},
                "sector": {"type": "string"}
            },
            "required": ["portfolio_id"]
        }
    },
    "move_weight": {
        "function": _move_weight,
        "schema": {
            "name": "move_weight",
            "description": "Move weight between sectors",
            "type": "write",
            "parameters": {
                "portfolio_id": {"type": "string"},
                "from_sector": {"type": "string"},
                "to_sectors": {"type": "array", "items": {"sector": {"type": "string"}, "weight_to_add": {"type": "float"}}}
            },
            "required": ["portfolio_id", "from_sector", "to_sectors"]
        }
    },
    "reset_portfolio": {
        "function": _reset_portfolio,
        "schema": {
            "name": "reset_portfolio",
            "description": "Resets a portfolio",
            "type": "write",
            "parameters": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"]
        }
    },
    "batch_adjust_sectors": {
        "function": _batch_adjust_sectors,
        "schema": {
            "name": "batch_adjust_sectors",
            "description": "Batch adjust sectors",
            "type": "write",
            "parameters": {
                "portfolio_id": {"type": "string"},
                "adjustments": {"type": "array"}
            },
            "required": ["portfolio_id", "adjustments"]
        }
    },
    "create_portfolio": {
        "function": _create_portfolio,
        "schema": {
            "name": "create_portfolio",
            "description": "Create new portfolio",
            "type": "write",
            "parameters": {
                "portfolio_id": {"type": "string"},
                "initial_composition": {"type": "array"}
            },
            "required": ["portfolio_id", "initial_composition"]
        }
    },
    "manage_assets_by_quantity": {
        "function": _manage_assets_by_quantity,
        "schema": {
            "name": "manage_assets_by_quantity",
            "description": "Adjust asset quantities",
            "type": "write",
            "parameters": {
                "portfolio_id": {"type": "string"},
                "operations": {"type": "array"}
            },
            "required": ["portfolio_id", "operations"]
        }
    },
    "lookup_sectors": {
        "function": _lookup_sectors,
        "schema": {
            "name": "lookup_sectors",
            "description": "Lookup sector for asset IDs",
            "type": "read",
            "parameters": {"asset_ids": {"type": "array"}}
        }
    },
    "lookup_prices": {
        "function": _lookup_prices,
        "schema": {
            "name": "lookup_prices",
            "description": "Lookup prices for asset IDs",
            "type": "read",
            "parameters": {"asset_ids": {"type": "array"}}
        }
    }
}

fn_map = {name: tool["function"] for name, tool in tool_registry.items()}

# ---------------------------
# Hybrid Argument Resolver
# ---------------------------

async def resolve_args(task, state, llm):
    args_resolved = {}
    # for k, v in task["args"].items():
    #     if isinstance(v, dict) and "from_task" in v:
    #         try:
    #             args_resolved[k] = jmespath.search(v.get("selector", ""), state[v["from_task"]])
    #         except Exception:
    #             args_resolved[k] = None
    #     else:
    #         args_resolved[k] = v

    prompt = f"""
You are a financial assistant agent and expert planner.
Current DAG state:
{json.dumps(state, indent=2)}

Task:
{json.dumps(task, indent=2)}

Deterministic arguments:
{json.dumps(args_resolved, indent=2)}

Return JSON: {{ "args": {{...}} }} fully resolved for execution.
"""
    llm_response = await llm(prompt)
    tid = task["id"]
    print(f"got execution of llm from {tid} with{llm_response}")
    args_final = llm_response.get("args", args_resolved)
    return args_final

# ---------------------------
# Node Factory
# ---------------------------

def make_node(task, llm, fn_map):
    async def node(state):
        args = await resolve_args(task, state, llm)
        print(f"[RUNNING] {task['id']} with args: {args} and state{state}")
        result = await fn_map[task["fn"]](**args)
        print(f"[finished RUNNING] {task['id']} with args: {args} and state{state} and result{result}")
        return {task["id"]: result}
    return node

# ---------------------------
# DAG Builder
# ---------------------------

def build_dag(task_spec, llm, fn_map):
    g = StateGraph(dict, merge_strategy="update")
    for t in task_spec:
        g.add_node(t["id"], make_node(t, llm, fn_map))

    deps = []
    leaders = []
    for t in task_spec:
        #for v in t["args"].values():
        if "depends" in t:
            for v in t["depends"]:
                #if isinstance(v, dict) and "from_task" in v:
                g.add_edge(v, t["id"])
                deps.append(t["id"])
                leaders.append(v)


    #entry_tasks = [t["id"] for t in task_spec if all(not isinstance(v, dict) for v in t["args"].values())]
    for t in task_spec:
        if t["id"] not in deps:
            g.set_entry_point(t["id"])

        if t["id"] not in leaders:
            g.add_edge(t["id"], END)

    # dependent_ids = {v["from_task"] for t in task_spec for v in t["args"].values() if isinstance(v, dict)}
    # for t in task_spec:
    #     if t["id"] not in dependent_ids:
    #         g.add_edge(t["id"], END)
    #return g
    return g.compile()

# ---------------------------
# Real OpenAI LLM Functions
# ---------------------------

async def llm_parse_user_input(user_input, tool_registry):
    prompt = f"""
You are a financial assistant agent and expert planner.
User instruction:
{user_input}

Tool registry schemas:
{json.dumps({k:v['schema'] for k,v in tool_registry.items()}, indent=2)}

Return ONLY valid JSON with double quotes. Do NOT add any explanations. {{ "tasks": [{{"id": "...", "fn": "...", "args": {{...}}}}] }}
Include dependencies: use {{ "from_task": "previous_task_id", "selector": "JMESPath" }}
Any lookup price sector or show constituents operation is a read operation and every other task is a write operation as it modifies 
the structure of the portfolio. if there's a write operation that precedes a read operation then both read and write cannot run in parallel.
in this case the read needs to wait for the write and it depends in a way on it even though it may not need output of write as part of args for read
for example: "add 100 shares of ibm to portfolio p1 and show top 2 weights of portfolio p1" should create a dependency of task 2 ie show top 2 weights
to the change of portfolio structure that adds ibm. if task2 depends on task1 and task3 but not for args just include another tag named depends and add all the task ids 
it depends on but not for args like depends: [id1, id2]. if task2 depends for say arg symbol to task1 encode the dependency inside the args as dictionary with key 
the arg name ie symbol and value the taskid it depends on here task1. 

Use the key depends  to signify dependencies between tasks
"""
    resp = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "system", "content": "You are an expert financial task planner."},
                  {"role": "user", "content": prompt}],
        temperature=0
    )
    text = resp.choices[0].message.content
    return json.loads(text)

async def llm_resolve_args(prompt):
    resp = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "system", "content": "You are an expert financial argument resolver."},
                  {"role": "user", "content": prompt}],
        temperature=0
    )
    text = resp.choices[0].message.content
    return json.loads(text)

# ---------------------------
# Agent Execution
# ---------------------------

async def agent_execute(user_input):
    parse_response = await llm_parse_user_input(user_input, tool_registry)
    task_spec = parse_response["tasks"]
    print(task for task in task_spec)
    graph = build_dag(task_spec, llm_resolve_args, fn_map)
    result = await graph.ainvoke({})
    print("\nFinal DAG State:")
    print(json.dumps(result, indent=2))
    return result

# ---------------------------
# Main
# ---------------------------

if __name__ == "__main__":
    user_input = "Add 100 shares of IBM to P1, show top 3 assets, print sectors of first 2"
    asyncio.run(agent_execute(user_input))
