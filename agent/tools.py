from fastapi import HTTPException
from portfolio.management import working_portfolio_cache, original_portfolio_cache, SECTORS, asset_sector_map

# --- Core Tool/Function Logic ---
def _adjust_portfolio_sector(portfolio_id: str, sector: str, set_weight: float = None, increase_by_weight: float = None, decrease_by_weight: float = None):
    # --- Parameter Validation ---
    if len([p for p in [set_weight, increase_by_weight, decrease_by_weight] if p is not None]) != 1:
        raise HTTPException(status_code=400, detail="Must provide exactly one of: set_weight, increase_by_weight, or decrease_by_weight.")

    if portfolio_id not in working_portfolio_cache:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")
    if sector not in SECTORS:
        raise HTTPException(status_code=400, detail=f"Invalid sector. Use one of: {SECTORS}")

    # --- Calculate Target Weight ---
    original_composition = working_portfolio_cache[portfolio_id]
    current_sector_weight = sum(c["weight"] for c in original_composition.values() if c["sector"] == sector)
    target_weight = 0

    if set_weight is not None:
        target_weight = set_weight
    elif increase_by_weight is not None:
        target_weight = current_sector_weight + increase_by_weight
    elif decrease_by_weight is not None:
        target_weight = current_sector_weight - decrease_by_weight

    if not 0.0 <= target_weight <= 1.0:
        raise HTTPException(status_code=400, detail=f"The requested change results in an invalid target weight of {target_weight:.2%}. Must be between 0% and 100%.")

    # --- Perform Adjustment ---
    new_composition = {k: v.copy() for k, v in original_composition.items()}
    sector_constituents = {k: v for k, v in new_composition.items() if v["sector"] == sector}
    if not sector_constituents:
        raise HTTPException(status_code=400, detail=f"No assets from sector '{sector}' in portfolio.")

    weight_adjustment = target_weight - current_sector_weight

    # --- Bug Fix for Zero-Weight Edge Cases ---
    # Case 1: Target sector has 0 weight and we are adding to it.
    if current_sector_weight == 0 and weight_adjustment > 0:
        # Distribute new weight equally, not pro-rata.
        equal_weight_add = target_weight / len(sector_constituents)
        for asset_id in sector_constituents:
            new_composition[asset_id]["weight"] = equal_weight_add
        # Adjust other assets downwards
        other_constituents = {k: v for k, v in new_composition.items() if v["sector"] != sector}
        for asset_id in other_constituents:
            new_composition[asset_id]["weight"] *= (1 - target_weight)

    # Case 2: Target sector is 100% and we are reducing it.
    elif current_sector_weight == 1.0 and weight_adjustment < 0:
        # Reduce target sector weights pro-rata
        for asset_id in sector_constituents:
            new_composition[asset_id]["weight"] *= target_weight
        # Distribute freed-up weight equally to all other assets
        other_assets = [k for k, v in original_composition.items() if v["sector"] != sector]
        if other_assets:
            equal_weight_add = (1 - target_weight) / len(other_assets)
            for asset_id in other_assets:
                new_composition[asset_id]["weight"] = equal_weight_add
    # --- Original Logic for Normal Cases ---
    else:
        current_other_weight = 1.0 - current_sector_weight
        # Defensively check for zero weights inside the loop
        if current_sector_weight <= 0 or current_other_weight <= 0:
            # This case should ideally not be hit due to outer logic, but as a safeguard:
            # If we need to adjust but one side is zero, an equal distribution is more stable.
            # This part of logic would need more detailed specs, so we raise an error for now.
            raise HTTPException(status_code=500, detail="Cannot perform pro-rata adjustment on a zero-weight portfolio slice.")

        for asset_id, data in new_composition.items():
            if data["sector"] == sector:
                pro_rata_factor = data["weight"] / current_sector_weight
                new_composition[asset_id]["weight"] += weight_adjustment * pro_rata_factor
            else:
                pro_rata_factor = data["weight"] / current_other_weight
                new_composition[asset_id]["weight"] -= weight_adjustment * pro_rata_factor

    # --- Create list of changes for the response ---
    sector_assets_with_changes = []
    for asset_id, data in new_composition.items():
        if data["sector"] == sector:
            sector_assets_with_changes.append({
                "asset_id": asset_id,
                "new_weight": data["weight"],
                "old_weight": original_composition[asset_id]["weight"]
            })
    
    working_portfolio_cache[portfolio_id] = new_composition
    sector_assets_with_changes.sort(key=lambda x: x["new_weight"], reverse=True)
    
    # Return a dictionary including the final calculated target weight for the summary
    return {
        "changed_assets": sector_assets_with_changes,
        "final_target_weight": target_weight
    }

def _show_top_constituents(portfolio_id: str, n: int = 20, sector: str = None):
    if portfolio_id not in working_portfolio_cache:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")

    composition = working_portfolio_cache[portfolio_id]
    
    # Filter by sector if provided
    if sector:
        if sector not in SECTORS:
            raise HTTPException(status_code=400, detail=f"Invalid sector: {sector}. Use one of: {SECTORS}")
        constituents_to_sort = {k: v for k, v in composition.items() if v["sector"] == sector}
    else:
        constituents_to_sort = composition

    if not constituents_to_sort:
        return []

    # Sort by weight descending
    sorted_constituents = sorted(constituents_to_sort.items(), key=lambda item: item[1]["weight"], reverse=True)
    
    # Return the top N
    return sorted_constituents[:n]

def _move_weight(portfolio_id: str, from_sector: str, to_sectors: list):
    if portfolio_id not in working_portfolio_cache:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")

    # --- Validation ---
    if from_sector not in SECTORS:
        raise HTTPException(status_code=400, detail=f"Invalid source sector: '{from_sector}'.")
    for t in to_sectors:
        if t["sector"] not in SECTORS:
            raise HTTPException(status_code=400, detail=f"Invalid destination sector: '{t['sector']}'.")

    total_weight_to_move = sum(t["weight_to_add"] for t in to_sectors)
    if total_weight_to_move <= 0:
        raise HTTPException(status_code=400, detail="Total weight to move must be positive.")

    original_composition = working_portfolio_cache[portfolio_id]
    current_from_weight = sum(c["weight"] for c in original_composition.values() if c["sector"] == from_sector)

    if current_from_weight <= 0:
        raise HTTPException(status_code=400, detail=f"Cannot move weight from {from_sector} as it has no weight in the portfolio.")

    if current_from_weight < total_weight_to_move:
        raise HTTPException(status_code=400, detail=f"Cannot move {total_weight_to_move:.2%} from {from_sector} as it only has {current_from_weight:.2%}.")

    # --- Perform Adjustment ---
    new_composition = {k: v.copy() for k, v in original_composition.items()}

    # Decrease weight from the source sector, pro-rata
    reduction_factor = 1 - (total_weight_to_move / current_from_weight)
    for asset_id, data in new_composition.items():
        if data["sector"] == from_sector:
            data["weight"] *= reduction_factor

    # Increase weight in destination sectors
    for to_instruction in to_sectors:
        dest_sector = to_instruction["sector"]
        weight_to_add = to_instruction["weight_to_add"]
        
        dest_constituents = {k: v for k, v in original_composition.items() if v["sector"] == dest_sector}
        current_dest_weight = sum(c["weight"] for c in dest_constituents.values())

        if current_dest_weight > 0:
            # Increase pro-rata
            increase_factor = weight_to_add / current_dest_weight
            for asset_id, data in new_composition.items():
                if data["sector"] == dest_sector:
                    data["weight"] *= (1 + increase_factor)
        else:
            # Distribute equally if destination sector has 0 weight
            equal_share = weight_to_add / len(dest_constituents)
            for asset_id in dest_constituents:
                new_composition[asset_id]["weight"] = equal_share

    working_portfolio_cache[portfolio_id] = new_composition
    # For this tool, we can just return a success message as the details are complex
    return {"from_sector": from_sector, "to_sectors": to_sectors, "amount": total_weight_to_move}

def _reset_portfolio(portfolio_id: str):
    if portfolio_id not in original_portfolio_cache:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} has no original state to reset to.")
    
    # Copy the original state back into the working state
    working_portfolio_cache[portfolio_id] = {k: v.copy() for k, v in original_portfolio_cache[portfolio_id].items()}
    return {"message": f"Portfolio {portfolio_id} has been successfully reset to its original composition."}

def _lookup_sectors(asset_ids: list[str]):
    """Internal function to look up sectors for a list of asset IDs."""
    return {
        asset_id: asset_sector_map.get(asset_id, "Not Found")
        for asset_id in asset_ids
    }

def _batch_adjust_sectors(portfolio_id: str, adjustments: list):
    if portfolio_id not in working_portfolio_cache:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")

    # --- Validation and Net Change Calculation ---
    net_weight_change = 0
    mentioned_sectors = set()
    for adj in adjustments:
        sector = adj.get("sector")
        if sector not in SECTORS:
            raise HTTPException(status_code=400, detail=f"Invalid sector in batch adjustments: '{sector}'.")
        mentioned_sectors.add(sector)
        
        increase = adj.get("increase_by_weight", 0)
        decrease = adj.get("decrease_by_weight", 0)
        net_weight_change += increase - decrease

    # --- Perform Adjustments ---
    original_composition = working_portfolio_cache[portfolio_id]
    new_composition = {k: v.copy() for k, v in original_composition.items()}

    # First, fund the net change from all unmentioned sectors pro-rata
    unmentioned_weight = sum(v["weight"] for k, v in original_composition.items() if v["sector"] not in mentioned_sectors)
    
    # Safeguard against division by zero if unmentioned sectors have no weight to give/take
    if unmentioned_weight <= 0 and net_weight_change != 0:
        raise HTTPException(status_code=400, detail="Cannot perform adjustment as there is no weight in unmentioned sectors to source from or allocate to.")

    funding_factor = 1 - (net_weight_change / unmentioned_weight) if unmentioned_weight > 0 else 1
    for asset_id, data in new_composition.items():
        if data["sector"] not in mentioned_sectors:
            data["weight"] *= funding_factor

    # Second, apply the specific adjustments to each mentioned sector
    for adj in adjustments:
        sector_to_change = adj.get("sector")
        change = adj.get("increase_by_weight", 0) - adj.get("decrease_by_weight", 0)
        
        current_sector_weight = sum(v["weight"] for k, v in original_composition.items() if v["sector"] == sector_to_change)
        if current_sector_weight > 0:
            sector_increase_factor = 1 + (change / current_sector_weight)
            for asset_id, data in new_composition.items():
                if data["sector"] == sector_to_change:
                    data["weight"] *= sector_increase_factor
        elif change > 0:
            # Handle adding to a zero-weight sector
            constituents = [k for k, v in original_composition.items() if v["sector"] == sector_to_change]
            if constituents:
                equal_share = change / len(constituents)
                for asset_id in constituents:
                    new_composition[asset_id]["weight"] += equal_share

    working_portfolio_cache[portfolio_id] = new_composition
    return {"message": "Batch adjustments applied successfully.", "adjustments": adjustments}

# --- Tool Registry ---
tool_registry = {
    "adjust_sector_exposure": {
        "function": _adjust_portfolio_sector,
        "schema": {
            "name": "adjust_sector_exposure",
            "description": "Adjusts the weight of a specific sector by setting an absolute target, or increasing/decreasing by a relative amount.",
            "parameters": {
                "portfolio_id": {"type": "string", "description": "The ID of the portfolio to modify (e.g., \"P1\")."},
                "sector": {"type": "string", "description": f"The sector to adjust. Available sectors are {SECTORS}."},
                "set_weight": {"type": "float", "description": "The absolute target weight for the sector (e.g., 0.25 for 25%)."},
                "increase_by_weight": {"type": "float", "description": "The relative amount to increase the sector's weight by (e.g., 0.05 for 5%)."},
                "decrease_by_weight": {"type": "float", "description": "The relative amount to decrease the sector's weight by (e.g., 0.05 for 5%)."}
            },
            "required": ["portfolio_id", "sector"]
        }
    },
    "show_top_constituents": {
        "function": _show_top_constituents,
        "schema": {
            "name": "show_top_constituents",
            "description": "Shows the top N constituents of a portfolio, sorted by weight. Can be filtered by sector.",
            "parameters": {
                "portfolio_id": {"type": "string", "description": "The ID of the portfolio to view (e.g., \"P1\")."},
                "n": {"type": "integer", "description": "The number of top constituents to show. Defaults to 20."}, 
                "sector": {"type": "string", "description": f"Optional: The specific sector to view. If omitted, shows top constituents from the entire portfolio."} 
            },
            "required": ["portfolio_id"]
        }
    },
    "move_weight": {
        "function": _move_weight,
        "schema": {
            "name": "move_weight",
            "description": "Moves a specified percentage of weight from a single source sector to one or more destination sectors.",
            "parameters": {
                "portfolio_id": {"type": "string", "description": "The ID of the portfolio to modify (e.g., \"P1\")."},
                "from_sector": {"type": "string", "description": "The single sector from which to move weight.",},
                "to_sectors": {"type": "array", "description": "A list of destination sectors and the absolute weight to add to each.", "items": {"type": "object", "properties": {"sector": {"type": "string"}, "weight_to_add": {"type": "float"}}}}
            },
            "required": ["portfolio_id", "from_sector", "to_sectors"]
        }
    },
    "reset_portfolio": {
        "function": _reset_portfolio,
        "schema": {
            "name": "reset_portfolio",
            "description": "Resets a portfolio to its original composition from the start of the session.",
            "parameters": {
                "portfolio_id": {"type": "string", "description": "The ID of the portfolio to reset (e.g., \"P1\")."}
            },
            "required": ["portfolio_id"]
        }
    },
    "batch_adjust_sectors": {
        "function": _batch_adjust_sectors,
        "schema": {
            "name": "batch_adjust_sectors",
            "description": "Applies a batch of adjustments to multiple sectors in a single, balanced transaction.",
            "parameters": {
                "portfolio_id": {"type": "string", "description": "The ID of the portfolio to modify (e.g., \"P1\")."},
                "adjustments": {"type": "array", "description": "A list of adjustments to perform.", "items": {"type": "object", "properties": {"sector": {"type": "string"}, "increase_by_weight": {"type": "float"}, "decrease_by_weight": {"type": "float"}}}}
            },
            "required": ["portfolio_id", "adjustments"]
        }
    },
    "lookup_sectors": {
        "function": _lookup_sectors,
        "schema": {
            "name": "lookup_sectors",
            "description": "Looks up the sector for a given list of asset IDs.",
            "parameters": {
                "asset_ids": {"type": "array", "description": "A list of asset IDs to look up.", "items": {"type": "string"}}
            },
            "required": ["asset_ids"]
        }
    }
}
