from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load environment variables at the very beginning
load_dotenv()

from agent.orchestrator import run_financial_agent
from portfolio.management import generate_new_portfolio, asset_sector_map, asset_price_map

# --- Data Models ---
class AdjustFromTextRequest(BaseModel):
    query: str

class AssetLookupRequest(BaseModel):
    asset_ids: list[str]

class PriceLookupRequest(BaseModel):
    asset_ids: list[str]

# --- FastAPI Lifespan & App Initialization ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Server starting up: Pre-generating portfolio for P1...")
    generate_new_portfolio("P1")
    print("Portfolio for P1 created and cached.")
    yield
    print("Server shutting down.")

app = FastAPI(lifespan=lifespan)

# Mount the static directory to serve files like index.html
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- API Endpoints ---
@app.get("/", response_class=FileResponse)
async def read_root():
    return "static/index.html"

@app.post("/portfolio/adjust-from-text")
async def adjust_portfolio_from_text(request: AdjustFromTextRequest):
    """Processes a natural language query via the financial agent."""
    return await run_financial_agent(request.query)

@app.post("/assets/lookup-sectors")
def lookup_asset_sectors(request: AssetLookupRequest):
    """Looks up the sector for a given list of asset IDs."""
    response = {
        asset_id: asset_sector_map.get(asset_id, "Not Found")
        for asset_id in request.asset_ids
    }
    return response

@app.post("/assets/lookup-prices")
def lookup_asset_prices(request: PriceLookupRequest):
    """Looks up the price for a given list of asset IDs."""
    response = {
        asset_id: asset_price_map.get(asset_id, "Not Found")
        for asset_id in request.asset_ids
    }
    return response
