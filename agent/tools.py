from fastapi import HTTPException
from portfolio.management import working_portfolio_cache, original_portfolio_cache, SECTORS, asset_sector_map, asset_price_map, recalculate_portfolio_weights

# --- Core Tool/Function Logic ---
def _adjust_portfolio_sector(portfolio_id: str, sector: str, set_weight: float = None, increase_by_weight: float = None, decrease_by_weight: float = None):
    # --- Parameter Validation ---
    if len([p for p in [set_weight, increase_by_weight, decrease_by_weight] if p is not None]) != 1:
        raise HTTPException(status_code=400, detail="Must provide exactly one of: set_weight, increase_by_weight, or decrease_by_weight.")

    if portfolio_id not in working_portfolio_cache:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")
    if sector not in SECTORS:
        raise HTTPException(status_code=400, detail=f"Invalid sector. Use one of: {SECTORS}")

    original_composition = working_portfolio_cache[portfolio_id]
    new_composition = {k: v.copy() for k, v in original_composition.items()}

    # Calculate current sector value based on quantities and prices
    current_sector_value = sum(data["quantity"] * data["price"] for data in original_composition.values() if data["sector"] == sector)
    total_portfolio_value = sum(data["quantity"] * data["price"] for data in original_composition.values())
    current_sector_weight = current_sector_value / total_portfolio_value if total_portfolio_value > 0 else 0

    target_weight = 0
    if set_weight is not None:
        target_weight = set_weight
    elif increase_by_weight is not None:
        target_weight = current_sector_weight + increase_by_weight
    elif decrease_by_weight is not None:
        target_weight = current_sector_weight - decrease_by_weight

    if not 0.0 <= target_weight <= 1.0:
        raise HTTPException(status_code=400, detail=f"The requested change results in an invalid target weight of {target_weight:.2%}. Must be between 0% and 100%.")

    # Calculate target sector value
    target_sector_value = target_weight * total_portfolio_value

    # Determine the value adjustment needed for the sector
    value_adjustment = target_sector_value - current_sector_value

    # --- Adjust quantities based on value adjustment ---
    sector_constituents = {k: v for k, v in new_composition.items() if v["sector"] == sector}
    if not sector_constituents:
        raise HTTPException(status_code=400, detail=f"No assets from sector '{sector}' in portfolio.")

    # Calculate current sector value based on quantities and prices
    current_sector_value_for_adjustment = sum(data["quantity"] * data["price"] for data in sector_constituents.values())

    # Case 1: Target sector has 0 value and we are adding to it.
    if current_sector_value_for_adjustment == 0 and value_adjustment > 0:
        # Distribute new value equally among constituents, then convert to quantity
        equal_value_add = value_adjustment / len(sector_constituents)
        for asset_id, data in sector_constituents.items():
            new_quantity = equal_value_add / data["price"]
            new_composition[asset_id]["quantity"] = round(new_quantity) # Round to nearest whole number

    # Case 2: Target sector is 100% and we are reducing it.
    elif current_sector_value_for_adjustment == total_portfolio_value and value_adjustment < 0:
        # Reduce quantities pro-rata based on value
        reduction_factor = 1 + (value_adjustment / current_sector_value_for_adjustment)
        for asset_id, data in sector_constituents.items():
            new_quantity = data["quantity"] * reduction_factor
            new_composition[asset_id]["quantity"] = round(new_quantity)

    # Normal case: Adjust quantities pro-rata based on value
    else:
        if current_sector_value_for_adjustment > 0:
            adjustment_factor = 1 + (value_adjustment / current_sector_value_for_adjustment)
            for asset_id, data in sector_constituents.items():
                new_quantity = data["quantity"] * adjustment_factor
                new_composition[asset_id]["quantity"] = round(new_quantity)

    # Recalculate weights for the entire portfolio after quantity changes
    recalculate_portfolio_weights(new_composition)

    # Create list of changes for the response
    sector_assets_with_changes = []
    for asset_id, data in new_composition.items():
        if data["sector"] == sector:
            sector_assets_with_changes.append({
                "asset_id": asset_id,
                "new_weight": data["weight"],
                "old_weight": original_composition[asset_id]["weight"],
                "new_quantity": data["quantity"],
                "old_quantity": original_composition[asset_id]["quantity"]
            })
    
    working_portfolio_cache[portfolio_id] = new_composition
    sector_assets_with_changes.sort(key=lambda x: x["new_weight"], reverse=True)
    
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

    # Sort by weight descending, then by asset ID ascending as a tie-breaker
    sorted_constituents = sorted(constituents_to_sort.items(), key=lambda item: (-item[1]['weight'], item[0]))
    
    # Return the top N with full details (including quantity, price, value, weight, sector)
    enhanced_results = []
    for asset_id, data in sorted_constituents[:n]:
        enhanced_results.append((asset_id, data)) # data already contains all fields

    return {"constituents": enhanced_results, "total_in_portfolio": len(constituents_to_sort)}

def _move_weight(portfolio_id: str, from_sector: str, to_sectors: list):
    if portfolio_id not in working_portfolio_cache:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")

    # --- Validation ---
    if from_sector not in SECTORS:
        raise HTTPException(status_code=400, detail=f"Invalid source sector: '{from_sector}'.")
    for t in to_sectors:
        if t["sector"] not in SECTORS:
            raise HTTPException(status_code=400, detail=f"Invalid destination sector: '{t['sector']}'.")

    original_composition = working_portfolio_cache[portfolio_id]
    new_composition = {k: v.copy() for k, v in original_composition.items()}

    # Calculate current value of from_sector
    current_from_value = sum(data["quantity"] * data["price"] for data in original_composition.values() if data["sector"] == from_sector)
    total_portfolio_value = sum(data["quantity"] * data["price"] for data in original_composition.values())

    # Calculate total value to move based on to_sectors instructions
    total_value_to_move = sum(t["weight_to_add"] * total_portfolio_value for t in to_sectors)

    if current_from_value <= 0:
        raise HTTPException(status_code=400, detail=f"Cannot move weight from {from_sector} as it has no value in the portfolio.")

    if current_from_value < total_value_to_move:
        raise HTTPException(status_code=400, detail=f"Cannot move {total_value_to_move:.2f} value from {from_sector} as it only has {current_from_value:.2f} value.")

    # --- Perform Adjustment ---
    # Decrease quantity from the source sector, pro-rata based on value
    reduction_factor = 1 - (total_value_to_move / current_from_value)
    for asset_id, data in new_composition.items():
        if data["sector"] == from_sector:
            new_quantity = data["quantity"] * reduction_factor
            new_composition[asset_id]["quantity"] = round(new_quantity)

    # Increase quantity in destination sectors
    for to_instruction in to_sectors:
        dest_sector = to_instruction["sector"]
        value_to_add = to_instruction["weight_to_add"] * total_portfolio_value
        
        dest_constituents = {k: v for k, v in original_composition.items() if v["sector"] == dest_sector}
        current_dest_value = sum(data["quantity"] * data["price"] for data in dest_constituents.values())

        if current_dest_value > 0:
            # Increase pro-rata based on value
            increase_factor = 1 + (value_to_add / current_dest_value)
            for asset_id, data in new_composition.items():
                if data["sector"] == dest_sector:
                    new_quantity = data["quantity"] * increase_factor
                    new_composition[asset_id]["quantity"] = round(new_quantity)
        else:
            # Distribute equally if destination sector has 0 value
            if not dest_constituents:
                raise HTTPException(status_code=400, detail=f"Cannot add value to {dest_sector} as it has no assets in the portfolio.")
            equal_value_add = value_to_add / len(dest_constituents)
            for asset_id in dest_constituents:
                new_quantity = equal_value_add / data["price"]
                new_composition[asset_id]["quantity"] = round(new_quantity)

    # Recalculate weights for the entire portfolio after quantity changes
    recalculate_portfolio_weights(new_composition)

    working_portfolio_cache[portfolio_id] = new_composition
    return {"from_sector": from_sector, "to_sectors": to_sectors, "amount": total_value_to_move}

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

def _lookup_prices(asset_ids: list[str]):
    """Internal function to look up prices for a list of asset IDs."""
    return {
        asset_id: asset_price_map.get(asset_id, "Not Found")
        for asset_id in asset_ids
    }

def _batch_adjust_sectors(portfolio_id: str, adjustments: list):
    if portfolio_id not in working_portfolio_cache:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")

    # --- Validation and Net Change Calculation ---
    net_value_change = 0
    mentioned_sectors = set()
    original_composition = working_portfolio_cache[portfolio_id]
    total_portfolio_value = sum(data["quantity"] * data["price"] for data in original_composition.values())

    for adj in adjustments:
        sector = adj.get("sector")
        if sector not in SECTORS:
            raise HTTPException(status_code=400, detail=f"Invalid sector in batch adjustments: '{sector}'.")
        mentioned_sectors.add(sector)
        
        increase_weight = adj.get("increase_by_weight", 0)
        decrease_weight = adj.get("decrease_by_weight", 0)
        net_value_change += (increase_weight - decrease_weight) * total_portfolio_value

    # --- Perform Adjustments ---
    new_composition = {k: v.copy() for k, v in original_composition.items()}

    # First, fund the net change from all unmentioned sectors pro-rata
    unmentioned_value = sum(data["quantity"] * data["price"] for data in original_composition.values() if data["sector"] not in mentioned_sectors)
    
    # Safeguard against division by zero if unmentioned sectors have no value to give/take
    if unmentioned_value <= 0 and net_value_change != 0:
        raise HTTPException(status_code=400, detail="Cannot perform adjustment as there is no value in unmentioned sectors to source from or allocate to.")

    funding_factor = 1 - (net_value_change / unmentioned_value) if unmentioned_value > 0 else 1
    for asset_id, data in new_composition.items():
        if data["sector"] not in mentioned_sectors:
            new_quantity = data["quantity"] * funding_factor
            new_composition[asset_id]["quantity"] = round(new_quantity)

    # Second, apply the specific adjustments to each mentioned sector
    for adj in adjustments:
        sector_to_change = adj.get("sector")
        change_weight = adj.get("increase_by_weight", 0) - adj.get("decrease_by_weight", 0)
        change_value = change_weight * total_portfolio_value
        
        current_sector_value = sum(data["quantity"] * data["price"] for data in original_composition.values() if data["sector"] == sector_to_change)

        if current_sector_value > 0:
            sector_increase_factor = 1 + (change_value / current_sector_value)
            for asset_id, data in new_composition.items():
                if data["sector"] == sector_to_change:
                    new_quantity = data["quantity"] * sector_increase_factor
                    new_composition[asset_id]["quantity"] = round(new_quantity)
        elif change_value > 0:
            # Handle adding to a zero-value sector
            constituents = [k for k, v in original_composition.items() if v["sector"] == sector_to_change]
            if constituents:
                equal_value_add = change_value / len(constituents)
                for asset_id in constituents:
                    new_quantity = equal_value_add / data["price"]
                    new_composition[asset_id]["quantity"] = round(new_quantity)

    # Recalculate weights for the entire portfolio after quantity changes
    recalculate_portfolio_weights(new_composition)

    working_portfolio_cache[portfolio_id] = new_composition
    return {"message": "Batch adjustments applied successfully.", "adjustments": adjustments}

def _create_portfolio(portfolio_id: str, initial_composition: list):
    if portfolio_id in working_portfolio_cache:
        raise HTTPException(status_code=400, detail=f"Portfolio '{portfolio_id}' already exists. Please choose a different name.")

    if not initial_composition:
        raise HTTPException(status_code=400, detail="Initial composition cannot be empty.")

    new_portfolio_data = {}
    total_portfolio_value = 0.0

    for item in initial_composition:
        asset_id = item.get("asset_id")
        quantity = item.get("quantity")

        if not asset_id or not isinstance(quantity, int) or quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Invalid asset entry: {item}. Must have positive integer quantity and valid asset_id.")

        if asset_id not in asset_sector_map:
            raise HTTPException(status_code=400, detail=f"Asset '{asset_id}' not found in universe.")

        price = asset_price_map[asset_id]
        sector = asset_sector_map[asset_id]
        value = quantity * price
        total_portfolio_value += value

        new_portfolio_data[asset_id] = {
            "quantity": quantity,
            "sector": sector,
            "price": price,
            "value": value,
            "weight": 0.0 # Placeholder
        }
    
    # Calculate weights
    for asset_id, data in new_portfolio_data.items():
        new_portfolio_data[asset_id]["weight"] = data["value"] / total_portfolio_value

    # Store in caches
    original_portfolio_cache[portfolio_id] = new_portfolio_data
    working_portfolio_cache[portfolio_id] = {k: v.copy() for k, v in new_portfolio_data.items()}

    # Return the full composition for display
    return {"message": f"Portfolio '{portfolio_id}' created successfully.", "composition": new_portfolio_data}

def _manage_assets_by_quantity(portfolio_id: str, operations: list):
    if portfolio_id not in working_portfolio_cache:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")

    original_composition = working_portfolio_cache[portfolio_id]
    new_composition = {k: v.copy() for k, v in original_composition.items()}
    
    processed_operations = []

    for op in operations:
        asset_id = op.get("asset_id")
        add_qty = op.get("add_quantity", 0)
        subtract_qty = op.get("subtract_quantity", 0)

        if not asset_id:
            processed_operations.append({"asset_id": "N/A", "status": "Error", "message": "Operation missing asset_id."})
            continue

        current_asset_data = new_composition.get(asset_id)

        if add_qty > 0:
            if current_asset_data:
                # Asset exists, increase quantity
                new_composition[asset_id]["quantity"] += add_qty
                processed_operations.append({"asset_id": asset_id, "status": "Added", "quantity_change": add_qty})
            else:
                # Asset does not exist, add it to portfolio
                if asset_id not in asset_sector_map:
                    processed_operations.append({"asset_id": asset_id, "status": "Error", "message": "Asset not found in universe."})
                    continue
                new_composition[asset_id] = {
                    "quantity": add_qty,
                    "sector": asset_sector_map[asset_id],
                    "price": asset_price_map[asset_id],
                    "value": 0.0, # Will be recalculated
                    "weight": 0.0 # Will be recalculated
                }
                processed_operations.append({"asset_id": asset_id, "status": "Added New", "quantity_change": add_qty})
        elif subtract_qty > 0:
            if not current_asset_data:
                # Asset does not exist, ignore subtraction
                processed_operations.append({"asset_id": asset_id, "status": "Ignored", "message": "Asset not in portfolio for subtraction."})
                continue
            
            current_qty = current_asset_data["quantity"]
            if subtract_qty >= current_qty:
                # Remove asset entirely
                del new_composition[asset_id]
                processed_operations.append({"asset_id": asset_id, "status": "Removed", "quantity_change": -current_qty})
            else:
                # Subtract quantity
                new_composition[asset_id]["quantity"] -= subtract_qty
                processed_operations.append({"asset_id": asset_id, "status": "Subtracted", "quantity_change": -subtract_qty})
        else:
            processed_operations.append({"asset_id": asset_id, "status": "Error", "message": "Operation must specify add_quantity or subtract_quantity."})

    # Recalculate weights for the entire portfolio after quantity changes
    recalculate_portfolio_weights(new_composition)

    working_portfolio_cache[portfolio_id] = new_composition
    return {"message": "Asset quantities managed successfully.", "operations": processed_operations}

# --- Tool Registry ---
tool_registry = {
    "adjust_sector_exposure": {
        "function": _adjust_portfolio_sector,
        "schema": {
            "name": "adjust_sector_exposure",
            "description": "Adjusts the weight of a specific sector by setting an absolute target, or increasing/decreasing by a relative amount.",
            "type": "write",
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
            "type": "read",
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
            "type": "write",
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
            "type": "write",
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
            "type": "write",
            "parameters": {
                "portfolio_id": {"type": "string", "description": "The ID of the portfolio to modify (e.g., \"P1\")."},
                "adjustments": {"type": "array", "description": "A list of adjustments to perform.", "items": {"type": "object", "properties": {"sector": {"type": "string"}, "increase_by_weight": {"type": "float"}, "decrease_by_weight": {"type": "float"}}}}
            },
            "required": ["portfolio_id", "adjustments"]
        }
    },
    "create_portfolio": {
        "function": _create_portfolio,
        "schema": {
            "name": "create_portfolio",
            "description": "Creates a new portfolio with a specified name and initial asset composition.",
            "type": "write",
            "parameters": {
                "portfolio_id": {"type": "string", "description": "The name/ID for the new portfolio (e.g., \"P3\")."},
                "initial_composition": {"type": "array", "description": "A list of assets and their quantities to include in the new portfolio.", "items": {"type": "object", "properties": {"asset_id": {"type": "string"}, "quantity": {"type": "integer"}}}}
            },
            "required": ["portfolio_id", "initial_composition"]
        }
    },
    "manage_assets_by_quantity": {
        "function": _manage_assets_by_quantity,
        "schema": {
            "name": "manage_assets_by_quantity",
            "description": "Adds or subtracts specific quantities of assets in a portfolio.",
            "type": "write",
            "parameters": {
                "portfolio_id": {"type": "string", "description": "The ID of the portfolio to modify (e.g., \"P1\")."},
                "operations": {"type": "array", "description": "A list of operations, each specifying an asset_id and either add_quantity or subtract_quantity.", "items": {"type": "object", "properties": {"asset_id": {"type": "string"}, "add_quantity": {"type": "integer"}, "subtract_quantity": {"type": "integer"}}}}
            },
            "required": ["portfolio_id", "operations"]
        }
    },
    "lookup_sectors": {
        "function": _lookup_sectors,
        "schema": {
            "name": "lookup_sectors",
            "description": "Looks up the sector for a given list of asset IDs.",
            "type": "read",
            "parameters": {
                "asset_ids": {"type": "array", "description": "A list of asset IDs to look up.", "items": {"type": "string"}}
            },
            "required": ["asset_ids"]
        }
    },
    "lookup_prices": {
        "function": _lookup_prices,
        "schema": {
            "name": "lookup_prices",
            "description": "Looks up the price for a given list of asset IDs.",
            "type": "read",
            "parameters": {
                "asset_ids": {"type": "array", "description": "A list of asset IDs to look up prices for.", "items": {"type": "string"}}
            },
            "required": ["asset_ids"]
        }
    }
}