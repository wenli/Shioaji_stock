import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import download_stock_data as dsd
import scheduler_manager as sm

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Lifespan for Shioaji Init & Scheduler
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize Database
    dsd.init_db()
    
    # 2. Login to Shioaji
    api = dsd.get_shioaji_client()
    if api:
        app.state.api = api
        logger.info("Shioaji API logged in successfully during startup.")
        
        # 3. Start Scheduler
        sm.start_scheduler(api)
    else:
        logger.error("FastAPI failed to log in to Shioaji. Background scheduler did not start.")
        
    yield
    # 4. Cleanup
    sm.stop_scheduler()
    if hasattr(app.state, 'api') and app.state.api:
        logger.info("Logging out from Shioaji API during shutdown...")
        app.state.api.logout()

app = FastAPI(title="Shioaji Stock Wish List Updater", lifespan=lifespan)

# Setup frontend static directory
frontend_path = Path("frontend")
frontend_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="frontend"), name="static")

class WishlistRequest(BaseModel):
    code: str

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serves the main Dashboard HTML."""
    html_file = frontend_path / "index.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return "<h1>Frontend index.html not found. Place it in frontend/index.html</h1>"

@app.get("/api/status")
def get_status():
    """Returns the system status and login status."""
    is_online = hasattr(app.state, 'api') and app.state.api is not None
    return {
        "status": "Online" if is_online else "Offline",
        "api_login": is_online
    }

@app.get("/api/wishlist")
def get_wishlist():
    """Gets all stocks in the wish list, with optional live quotes and db stats."""
    wish_stocks = dsd.get_wish_list()
    if not wish_stocks:
        return []

    is_online = hasattr(app.state, 'api') and app.state.api is not None
    snapshots_dict = {}

    # Try to fetch live quotes (snapshots)
    if is_online:
        try:
            api = app.state.api
            contracts = []
            for s in wish_stocks:
                code = s['code']
                try:
                    contract = api.Contracts.Stocks[code]
                    if contract:
                        contracts.append(contract)
                except Exception:
                    pass
            
            if contracts:
                snapshots = api.snapshots(contracts)
                for snap in snapshots:
                    snapshots_dict[snap.code] = {
                        "close": getattr(snap, 'close', None),
                        "change_price": getattr(snap, 'change_price', None),
                        "change_rate": getattr(snap, 'change_rate', None),
                        "open": getattr(snap, 'open', None),
                        "high": getattr(snap, 'high', None),
                        "low": getattr(snap, 'low', None),
                        "volume": getattr(snap, 'volume', None),
                    }
        except Exception as e:
            logger.error(f"Failed to fetch stock snapshots from Shioaji: {e}")

    # Combine with Database sync stats
    result = []
    for s in wish_stocks:
        code = s['code']
        # Fetch last ts from DB
        last_1k = dsd.get_last_ts("stock1k", code)
        last_5k = dsd.get_last_ts("stock5k", code)
        last_1d = dsd.get_last_ts("stock1d", code)
        
        # Merge live snapshot info
        snap = snapshots_dict.get(code, {})
        
        # If offline or market closed, fallback to db's last close price
        close_price = snap.get("close")
        if close_price is None or close_price == 0:
            # Try to get last close from 1d or 1k
            conn = dsd.get_db_connection()
            try:
                row = conn.execute("SELECT close FROM stock1d WHERE code = ? ORDER BY ts DESC LIMIT 1", (code,)).fetchone()
                if row:
                    close_price = row['close']
                else:
                    row = conn.execute("SELECT close FROM stock1k WHERE code = ? ORDER BY ts DESC LIMIT 1", (code,)).fetchone()
                    if row:
                        close_price = row['close']
            except Exception:
                pass
            finally:
                conn.close()

        # Fetch sync status from memory tracker
        tracker_status = dsd.sync_tracker.get_status(code)

        result.append({
            "code": code,
            "name": s['name'],
            "status": s['status'],
            "created_at": s['created_at'],
            "last_sync_ts": s['last_sync_ts'] or "Never Sync",
            "last_1k": last_1k or "No Data",
            "last_5k": last_5k or "No Data",
            "last_1d": last_1d or "No Data",
            "live_price": close_price if close_price is not None else "N/A",
            "change_rate": snap.get("change_rate", 0) * 100 if snap.get("change_rate") is not None else 0,
            "change_price": snap.get("change_price", 0) if snap.get("change_price") is not None else 0,
            "sync_status": tracker_status.get("status", "idle"),
            "sync_error": tracker_status.get("error", ""),
        })
        
    return result

@app.post("/api/wishlist")
def add_stock(req: WishlistRequest, background_tasks: BackgroundTasks):
    """Adds a stock to the wish list and triggers background sync."""
    code = req.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Stock code cannot be empty.")

    is_online = hasattr(app.state, 'api') and app.state.api is not None
    if not is_online:
        raise HTTPException(status_code=503, detail="Shioaji API is not logged in. Operation unavailable.")

    api = app.state.api
    
    # 1. Lookup stock contract in Shioaji
    try:
        contract = api.Contracts.Stocks[code]
        if not contract:
            raise HTTPException(status_code=400, detail=f"Stock code {code} does not exist in Taiwan market.")
    except Exception as e:
        logger.error(f"Error checking stock code {code}: {e}")
        raise HTTPException(status_code=400, detail=f"Stock code {code} lookup failed. Invalid code.")

    # 2. Add stock to Database wishlist
    stock_name = contract.name or "Unknown"
    success = dsd.add_to_wish_list(code, stock_name)
    if not success:
         raise HTTPException(status_code=500, detail="Failed to write stock to database wish_list.")

    # 3. Trigger initial sync in the background
    dsd.sync_tracker.set_status(code, "pending")
    background_tasks.add_task(dsd.sync_to_latest, api, code)
    
    return {"message": f"Successfully added {code} ({stock_name}) to wish list. Background sync initiated."}

@app.delete("/api/wishlist/{code}")
def delete_stock(code: str):
    """Removes a stock from the wish list and deletes its K-line history."""
    success = dsd.remove_from_wish_list(code, delete_data=True)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to delete {code} from database.")
    dsd.sync_tracker.remove(code)
    return {"message": f"Successfully removed stock {code} and cleared its historical data."}

@app.post("/api/sync")
def trigger_all_sync(background_tasks: BackgroundTasks):
    """Manually triggers background sync for all stocks in the wish list."""
    is_online = hasattr(app.state, 'api') and app.state.api is not None
    if not is_online:
        raise HTTPException(status_code=503, detail="Shioaji API is not logged in.")
        
    api = app.state.api
    background_tasks.add_task(sm.sync_all_wish_stocks, api)
    return {"message": "Manual sync triggered in the background for all active stocks."}

@app.get("/api/kbars/{code}")
def get_kbars(code: str, timeframe: str = "1k", limit: int = 500):
    """Gets historical K-bars for a specific stock and timeframe, sorted chronologically."""
    allowed_timeframes = ["1k", "5k", "15k", "30k", "60k", "1d"]
    tf = timeframe.lower()
    if tf not in allowed_timeframes:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe: {timeframe}. Allowed: {allowed_timeframes}")
        
    table_name = f"stock{tf}"
    conn = dsd.get_db_connection()
    try:
        # Use nested query to select the LATEST N bars and sort them ASC for lightweight-charts
        query = f"""
            SELECT ts as time, open, high, low, close, volume
            FROM (
                SELECT ts, open, high, low, close, volume
                FROM {table_name}
                WHERE code = ?
                ORDER BY ts DESC
                LIMIT ?
            )
            ORDER BY ts ASC
        """
        rows = conn.execute(query, (code, limit)).fetchall()
        kbars = [dict(row) for row in rows]
        
        # Format date for lightweight-charts:
        # If daily '1d', keep YYYY-MM-DD or Unix timestamp.
        # Otherwise, keep ISO string or Unix timestamp.
        # Lightweight charts accepts ISO strings for datetime.
        return {
            "success": True,
            "code": code,
            "timeframe": tf,
            "kbars": kbars
        }
    except Exception as e:
        logger.error(f"Failed to query kbars for {code} ({tf}): {e}")
        raise HTTPException(status_code=500, detail="Database query failed.")
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=True)
