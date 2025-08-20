import random

# --- In-Memory Cache and Asset Universe ---
original_portfolio_cache = {}
working_portfolio_cache = {}
asset_sector_map = {} # Using a dictionary for efficient lookups
asset_price_map = {} # Cache for asset prices
SECTORS = ["Financials", "Energy", "Banking", "Industrials", "Textiles"]
ASSETS_PER_SECTOR = 4000 # Increased to 4000 for a 20k universe

def setup_asset_universe():
    """Generates a 20k asset universe as a direct lookup map."""
    global asset_sector_map, asset_price_map
    if asset_sector_map: return
    for i, sector in enumerate(SECTORS):
        for j in range(1, ASSETS_PER_SECTOR + 1):
            # Asset IDs are now 1-based, e.g., BBID1, BBID2, ...
            asset_id = f"BBID{i * ASSETS_PER_SECTOR + j}"
            asset_sector_map[asset_id] = sector
            # Assign a random price between 1.0 and 5.0
            asset_price_map[asset_id] = round(random.uniform(1.0, 5.0), 2)

def generate_new_portfolio(portfolio_id: str, num_positions: int):
    setup_asset_universe()
    all_asset_ids = list(asset_sector_map.keys())
    
    # Ensure we don't try to select more positions than available assets
    if num_positions > len(all_asset_ids):
        raise ValueError(f"Cannot generate {num_positions} positions, only {len(all_asset_ids)} assets available.")

    selected_asset_ids = random.sample(all_asset_ids, num_positions)
    
    portfolio_composition = {}
    total_portfolio_value = 0.0

    for asset_id in selected_asset_ids:
        quantity = random.randint(100, 150)
        price = asset_price_map[asset_id]
        value = quantity * price
        total_portfolio_value += value
        
        portfolio_composition[asset_id] = {
            "quantity": quantity,
            "sector": asset_sector_map[asset_id],
            "price": price,
            "value": value, # Store value for easier recalculation
            "weight": 0.0 # Placeholder, will be calculated below
        }
    
    # Calculate weights based on quantity and price
    for asset_id, data in portfolio_composition.items():
        portfolio_composition[asset_id]["weight"] = data["value"] / total_portfolio_value

    # Store in both original and working caches initially
    original_portfolio_cache[portfolio_id] = portfolio_composition
    working_portfolio_cache[portfolio_id] = {k: v.copy() for k, v in portfolio_composition.items()}
    return portfolio_composition

def recalculate_portfolio_weights(portfolio_composition: dict):
    """Recalculates values and weights for a given portfolio composition based on quantities and prices."""
    total_portfolio_value = 0.0
    for asset_id, data in portfolio_composition.items():
        data["value"] = data["quantity"] * data["price"]
        total_portfolio_value += data["value"]

    if total_portfolio_value == 0:
        # Handle case where portfolio value becomes zero (e.g., all quantities are zero)
        for asset_id, data in portfolio_composition.items():
            data["weight"] = 0.0
    else:
        for asset_id, data in portfolio_composition.items():
            data["weight"] = data["value"] / total_portfolio_value
    
    return portfolio_composition