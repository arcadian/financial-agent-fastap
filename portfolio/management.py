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

def generate_new_portfolio(portfolio_id: str):
    setup_asset_universe()
    # Get a list of all asset IDs from the map
    all_asset_ids = list(asset_sector_map.keys())
    selected_asset_ids = random.sample(all_asset_ids, 100)
    
    weight = 1 / 100
    portfolio_composition = {
        asset_id: {"weight": weight, "sector": asset_sector_map[asset_id]}
        for asset_id in selected_asset_ids
    }
    # Store in both original and working caches initially
    original_portfolio_cache[portfolio_id] = portfolio_composition
    working_portfolio_cache[portfolio_id] = {k: v.copy() for k, v in portfolio_composition.items()}
    return portfolio_composition