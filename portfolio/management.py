import random

# --- In-Memory Cache and Asset Universe ---
original_portfolio_cache = {}
working_portfolio_cache = {}
asset_universe = []
SECTORS = ["Financials", "Energy", "Banking", "Industrials", "Textiles"]
ASSETS_PER_SECTOR = 200

def setup_asset_universe():
    global asset_universe
    if asset_universe: return
    for i, sector in enumerate(SECTORS):
        for j in range(1, ASSETS_PER_SECTOR + 1):
            asset_id = f"BBID{i * ASSETS_PER_SECTOR + j}"
            asset_universe.append({"id": asset_id, "sector": sector})

def generate_new_portfolio(portfolio_id: str):
    setup_asset_universe()
    selected_constituents = random.sample(asset_universe, 100)
    weight = 1 / 100
    portfolio_composition = {
        asset["id"]: {"weight": weight, "sector": asset["sector"]}
        for asset in selected_constituents
    }
    # Store in both original and working caches initially
    original_portfolio_cache[portfolio_id] = portfolio_composition
    working_portfolio_cache[portfolio_id] = {k: v.copy() for k, v in portfolio_composition.items()}
    return portfolio_composition
