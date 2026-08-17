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
import requests
from bs4 import BeautifulSoup

import download_stock_data as dsd
import scheduler_manager as sm
import pandas as pd
from app import backtester
from app import smc_detector

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Yahoo Import Settings
YAHOO_IMPORT_MAX_PRICE = int(os.getenv("YAHOO_IMPORT_MAX_PRICE", "100"))
YAHOO_IMPORT_LIMIT = int(os.getenv("YAHOO_IMPORT_LIMIT", "20"))


# Lifespan for Shioaji Init & Scheduler
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize Database
    dsd.init_db()
    
    # 2. Login to Shioaji
    api = dsd.get_shioaji_client()
    app.state.api = api
    if api:
        logger.info("Shioaji API logged in successfully during startup.")
    else:
        logger.warning("FastAPI failed to log in to Shioaji. Operating in offline or Yahoo Finance mode.")
        
    # 3. Start Scheduler (allow starting even if api is None, since Yahoo mode does not need Shioaji)
    sm.start_scheduler(api)
        
    yield
    # 4. Cleanup
    sm.stop_scheduler()
    if hasattr(app.state, 'api') and app.state.api:
        logger.info("Logging out from Shioaji API during shutdown...")
        try:
            app.state.api.logout()
        except Exception as e:
            logger.warning(f"Error logging out from Shioaji API: {e}")


app = FastAPI(title="Shioaji Stock Wish List Updater", lifespan=lifespan)

# Setup frontend static directory
frontend_path = Path("frontend")
frontend_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="frontend"), name="static")

class WishlistRequest(BaseModel):
    code: str

class YahooSettingsRequest(BaseModel):
    max_price: int
    limit: int

class BacktestRequest(BaseModel):
    code: str
    start_date: str
    end_date: str
    initial_balance: float = 1001000.0
    risk_pct: float = 0.01
    rr_ratio: float = 2.0
    htf_window: int = 20
    entry_mode: str = "fvg_top"
    sl_buffer_pct: float = 0.2
    fee_discount: float = 0.6
    enable_short: bool = False
    holding_mode: str = "day_trade"
    ltf_timeframe: str = "5k"
    strategy_name: str = "smc"

def update_env_file(key: str, value: str):
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        logger.error(f".env file not found at {env_path}")
        return
    try:
        content = env_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        updated = False
        for i, line in enumerate(lines):
            # 支援可能帶有空白的等號
            if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
                lines[i] = f"{key}={value}"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={value}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(f"Successfully updated {key}={value} in .env")
    except Exception as e:
        logger.error(f"Error writing to .env: {e}")
        raise e

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serves the main Dashboard HTML."""
    html_file = frontend_path / "index.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return "<h1>Frontend index.html not found. Place it in frontend/index.html</h1>"

class SourceConfigRequest(BaseModel):
    source: str

@app.get("/api/status")
def get_status():
    """Returns the system status, login status and active source."""
    is_online = hasattr(app.state, 'api') and app.state.api is not None
    active_source = dsd.get_active_source()
    
    # In Yahoo mode, system is Online if it has network, regardless of Shioaji login
    system_status = "Online"
    if active_source == "shioaji" and not is_online:
        system_status = "Offline"
        
    return {
        "status": system_status,
        "api_login": is_online,
        "active_source": active_source
    }

@app.get("/api/config/source")
def get_source_config():
    """Gets the active data source configuration."""
    return {"active_source": dsd.get_active_source()}

@app.post("/api/config/source")
def update_source_config(req: SourceConfigRequest):
    """Updates the active data source configuration and initializes the target database."""
    if req.source not in ["shioaji", "yahoo"]:
        raise HTTPException(status_code=400, detail="Invalid source. Must be 'shioaji' or 'yahoo'.")
    
    dsd.set_active_source(req.source)
    try:
        dsd.init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database for source {req.source}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize database: {e}")
        
    return {"active_source": req.source}


@app.get("/api/wishlist")
def get_wishlist():
    """Gets all stocks in the wish list, with optional live quotes and db stats."""
    wish_stocks = dsd.get_wish_list()
    if not wish_stocks:
        return []

    active_source = dsd.get_active_source()
    is_online = hasattr(app.state, 'api') and app.state.api is not None
    snapshots_dict = {}

    # Try to fetch live quotes (snapshots)
    if active_source == "shioaji" and is_online:
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

    conn = dsd.get_db_connection()
    result = []
    try:
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

            # Fetch or compute OBs
            obs_by_tf = smc_detector.get_stock_obs_from_db(conn, code)
            # If completely empty for this stock, compute once
            if not any(obs_by_tf[tf] for tf in ["5k", "15k", "60k", "1d"]):
                smc_detector.compute_and_save_obs_for_stock(conn, code)
                obs_by_tf = smc_detector.get_stock_obs_from_db(conn, code)

            # Evaluate touch status
            active_touches = []
            ob_status = {}
            for tf in ["5k", "15k", "60k", "1d"]:
                tf_obs = obs_by_tf.get(tf, {})
                bullish = tf_obs.get("bullish")
                bearish = tf_obs.get("bearish")

                bullish_touch = False
                bearish_touch = False
                if close_price is not None and close_price != "N/A":
                    try:
                        p = float(close_price)
                        if bullish and bullish['bottom'] <= p <= bullish['top']:
                            bullish_touch = True
                        if bearish and bearish['bottom'] <= p <= bearish['top']:
                            bearish_touch = True
                    except Exception:
                        pass

                touch_type = None
                if bullish_touch and bearish_touch:
                    touch_type = "BOTH"
                    active_touches.append(tf)
                elif bullish_touch:
                    touch_type = "BULLISH"
                    active_touches.append(tf)
                elif bearish_touch:
                    touch_type = "BEARISH"
                    active_touches.append(tf)

                ob_status[tf] = {
                    "bullish": {**bullish, "is_touching": bullish_touch} if bullish else None,
                    "bearish": {**bearish, "is_touching": bearish_touch} if bearish else None,
                    "touch_type": touch_type
                }

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
                "change_rate": snap.get("change_rate", 0) if snap.get("change_rate") is not None else 0,
                "change_price": snap.get("change_price", 0) if snap.get("change_price") is not None else 0,
                "sync_status": tracker_status.get("status", "idle"),
                "sync_error": tracker_status.get("error", ""),
                "active_touches": active_touches,
                "ob_status": ob_status
            })
    finally:
        conn.close()
        
    return result

@app.get("/api/ob-radar")
def get_ob_radar():
    """Returns all stocks that are actively touching any 5M, 15M, 60M, or 1D Order Block."""
    all_stocks = get_wishlist()
    touching_stocks = [s for s in all_stocks if s.get("active_touches") and len(s["active_touches"]) > 0]
    return {
        "count": len(touching_stocks),
        "stocks": touching_stocks,
        "all_monitored_count": len(all_stocks)
    }

@app.post("/api/wishlist")
def add_stock(req: WishlistRequest, background_tasks: BackgroundTasks):
    """Adds a stock to the wish list and triggers background sync."""
    code = req.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Stock code cannot be empty.")

    active_source = dsd.get_active_source()
    is_online = hasattr(app.state, 'api') and app.state.api is not None

    if active_source == "shioaji":
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

    else:
        # Yahoo mode - check yfinance ticker availability
        import yfinance as yf
        import time
        tickers_to_try = [f"{code}.TW", f"{code}.TWO"]
        selected_ticker = None
        stock_name = f"Yahoo {code}"
        
        for ticker in tickers_to_try:
            try:
                df_test = yf.download(tickers=ticker, period="1d", progress=False)
                if df_test is not None and not df_test.empty:
                    selected_ticker = ticker
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if not selected_ticker:
            raise HTTPException(status_code=400, detail=f"Stock code {code} not found on Yahoo Finance (.TW or .TWO)")

        # Add to wish list
        success = dsd.add_to_wish_list(code, stock_name)
        if not success:
             raise HTTPException(status_code=500, detail="Failed to write stock to database wish_list.")

        # Trigger sync
        dsd.sync_tracker.set_status(code, "pending")
        background_tasks.add_task(dsd.sync_to_latest, None, code)
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
    active_source = dsd.get_active_source()
    is_online = hasattr(app.state, 'api') and app.state.api is not None
    
    if active_source == "shioaji" and not is_online:
        raise HTTPException(status_code=503, detail="Shioaji API is not logged in.")
        
    api = getattr(app.state, 'api', None)
    background_tasks.add_task(sm.sync_all_wish_stocks, api)
    return {"message": "Manual sync triggered in the background for all active stocks."}


@app.get("/api/settings/yahoo")
def get_yahoo_settings():
    """Gets current Yahoo Import Settings (max price, limit)."""
    return {
        "max_price": YAHOO_IMPORT_MAX_PRICE,
        "limit": YAHOO_IMPORT_LIMIT
    }

@app.post("/api/settings/yahoo")
def update_yahoo_settings(req: YahooSettingsRequest):
    """Updates Yahoo Import Settings in memory and persists them to .env."""
    global YAHOO_IMPORT_MAX_PRICE, YAHOO_IMPORT_LIMIT
    if req.max_price <= 0 or req.limit <= 0:
        raise HTTPException(status_code=400, detail="價格與數量限制必須大於 0")
    
    try:
        update_env_file("YAHOO_IMPORT_MAX_PRICE", str(req.max_price))
        update_env_file("YAHOO_IMPORT_LIMIT", str(req.limit))
        
        YAHOO_IMPORT_MAX_PRICE = req.max_price
        YAHOO_IMPORT_LIMIT = req.limit
        
        return {"message": "設定儲存成功，已寫入 .env 檔案"}
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail=f"儲存設定失敗: {str(e)}")

@app.post("/api/import_yahoo")
def import_yahoo_stock(background_tasks: BackgroundTasks):
    """匯入 Yahoo 成交量排行前 YAHOO_IMPORT_LIMIT 且股價 <= YAHOO_IMPORT_MAX_PRICE 的股票"""
    active_source = dsd.get_active_source()
    is_online = hasattr(app.state, 'api') and app.state.api is not None
    
    if active_source == "shioaji" and not is_online:
        raise HTTPException(status_code=503, detail="Shioaji API is not logged in. Operation unavailable.")
        
    api = getattr(app.state, 'api', None)
    
    try:
        url = "https://tw.stock.yahoo.com/rank/volume"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        rows = soup.select('li div[class*="table-row"]')
        
        wish_stocks = dsd.get_wish_list()
        existing_codes = {s['code'] for s in wish_stocks}
        
        added_count = 0
        imported_stocks = []
        
        for row in rows[:YAHOO_IMPORT_LIMIT]:
            try:
                # 尋找連結與代碼
                link = row.select_one('a[href*="/quote/"]')
                if not link:
                    continue
                
                href = str(link["href"])
                parts = href.split("/quote/")
                if len(parts) < 2:
                    continue
                
                code_with_market = parts[1].split("?")[0].split("#")[0]
                if "." in code_with_market:
                    code_raw = code_with_market.split(".")[0]
                else:
                    code_raw = code_with_market
                
                # 尋找名稱
                name_div = row.select_one('div[class*="Lh(20px)"]')
                if name_div:
                    stock_name = name_div.get_text(strip=True)
                else:
                    stock_name = link.get_text(strip=True)
                    if code_raw in stock_name:
                        stock_name = stock_name.replace(code_raw, "")
                
                # 尋找價格 Price
                cells = row.find_all("div", recursive=False)
                price = None
                found_link_cell = False
                for cell in cells:
                    if link in cell.find_all("a"):
                        found_link_cell = True
                        continue
                    
                    if found_link_cell:
                        txt = cell.get_text(strip=True).replace(",", "")
                        try:
                            val = float(txt)
                            price = val
                            break
                        except ValueError:
                            continue
                
                if price is not None and price <= YAHOO_IMPORT_MAX_PRICE:
                    if code_raw not in existing_codes:
                        if active_source == "shioaji":
                            # 驗證該股票在 Shioaji 中是否存在合約
                            try:
                                contract = api.Contracts.Stocks[code_raw]
                                if contract:
                                    real_name = contract.name or stock_name
                                    success = dsd.add_to_wish_list(code_raw, real_name)
                                    if success:
                                        # 觸發背景同步
                                        dsd.sync_tracker.set_status(code_raw, "pending")
                                        background_tasks.add_task(dsd.sync_to_latest, api, code_raw)
                                        
                                        imported_stocks.append(f"{real_name}({code_raw})")
                                        added_count += 1
                                        existing_codes.add(code_raw)
                            except Exception as e:
                                logger.error(f"Failed to verify stock {code_raw} via Shioaji: {e}")
                        else:
                            # Yahoo mode - 直接加入並背景同步
                            # 因是在 Yahoo 熱門榜，必定存在，不另外做慢速的 yfinance 請求
                            success = dsd.add_to_wish_list(code_raw, stock_name)
                            if success:
                                dsd.sync_tracker.set_status(code_raw, "pending")
                                background_tasks.add_task(dsd.sync_to_latest, None, code_raw)
                                
                                imported_stocks.append(f"{stock_name}({code_raw})")
                                added_count += 1
                                existing_codes.add(code_raw)
            except Exception as e:
                logger.error(f"Error processing Yahoo stock row: {e}")
                continue
                
        return {
            "success": True,
            "message": f"成功匯入 {added_count} 檔股價 <= {YAHOO_IMPORT_MAX_PRICE} 的熱門股: {', '.join(imported_stocks)}" if added_count > 0 else f"抓取排行前 {YAHOO_IMPORT_LIMIT} 檔，但沒有新增任何股票 (可能均已在清單中，或股價均高於 {YAHOO_IMPORT_MAX_PRICE} 元)",
            "imported": imported_stocks
        }
    except Exception as e:
        logger.error(f"Failed to import Yahoo stocks: {e}")
        raise HTTPException(status_code=500, detail=f"匯入 Yahoo 股票失敗: {str(e)}")

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

@app.get("/api/kbars/multi/{code}")
def get_multi_kbars(code: str, limit: int = 1000, anchor_time: str = None):
    """Gets historical K-bars for multiple timeframes (5k, 15k, 60k, 1d) in one call, optionally centered at anchor_time."""
    timeframes = ["5k", "15k", "60k", "1d"]
    conn = dsd.get_db_connection()
    result = {}
    
    limit_before = int(limit * 0.8)
    limit_after = limit - limit_before
    
    try:
        for tf in timeframes:
            table_name = f"stock{tf}"
            if anchor_time:
                # 取得 anchor_time 之前的數據 (時間 DESC，需反轉為 ASC)
                query_before = f"""
                    SELECT ts as time, open, high, low, close, volume
                    FROM {table_name}
                    WHERE code = ? AND ts <= ?
                    ORDER BY ts DESC
                    LIMIT ?
                """
                rows_before = conn.execute(query_before, (code, anchor_time, limit_before)).fetchall()
                rows_before = list(reversed(rows_before))
                
                # 取得 anchor_time 之後的數據 (時間 ASC)
                query_after = f"""
                    SELECT ts as time, open, high, low, close, volume
                    FROM {table_name}
                    WHERE code = ? AND ts > ?
                    ORDER BY ts ASC
                    LIMIT ?
                """
                rows_after = conn.execute(query_after, (code, anchor_time, limit_after)).fetchall()
                
                rows = rows_before + rows_after
            else:
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
                
            result[tf] = [dict(row) for row in rows]
            
        return {
            "success": True,
            "code": code,
            "data": result
        }
    except Exception as e:
        logger.error(f"Failed to query multi kbars for {code} with anchor_time={anchor_time}: {e}")
        raise HTTPException(status_code=500, detail="Database query failed.")
    finally:
        conn.close()

@app.get("/chart/{code}", response_class=HTMLResponse)
async def get_chart_page(code: str):
    """Serves the multi-timeframe chart page."""
    html_file = frontend_path / "chart.html"
    logger.info(f"DEBUG: Serving chart page for {code} from absolute path: {html_file.resolve().absolute()}")
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return "<h1>chart.html not found. Place it in frontend/chart.html</h1>"

@app.get("/backtest", response_class=HTMLResponse)
async def get_backtest_page():
    """Serves the SMC Backtest page."""
    html_file = frontend_path / "backtest.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return "<h1>backtest.html not found. Place it in frontend/backtest.html</h1>"

@app.get("/api/stock/{code}")
def get_stock_info(code: str):
    """Gets stock code and name (from Shioaji contract or Database wish_list fallback)."""
    is_online = hasattr(app.state, 'api') and app.state.api is not None
    name = "Unknown"
    
    if is_online:
        try:
            contract = app.state.api.Contracts.Stocks[code]
            if contract:
                return {"code": code, "name": contract.name or "Unknown"}
        except Exception:
            pass
            
    try:
        conn = dsd.get_db_connection()
        row = conn.execute("SELECT name FROM wish_list WHERE code = ?", (code,)).fetchone()
        if row:
            name = row['name']
    except Exception:
        pass
    finally:
        conn.close()
        
@app.post("/api/backtest")
def run_backtest_endpoint(req: BacktestRequest):
    """Runs the SMC backtest, automatically syncing historical data if incomplete."""
    
    # 檢查並補齊本地 SQLite 的歷史 K 線數據
    conn = dsd.get_db_connection()
    row = None
    try:
        row = conn.execute("SELECT MIN(ts) as min_ts, MAX(ts) as max_ts FROM stock1d WHERE code = ?", (req.code,)).fetchone()
    except Exception as e:
        logger.error(f"Error querying stock1d min/max for backtest: {e}")
    finally:
        conn.close()

    # 檢查 Shioaji 在線狀態以決定是否能下載，且只在 active_source 為 shioaji 時才自動補齊
    active_source = dsd.get_active_source()
    is_online = hasattr(app.state, 'api') and app.state.api is not None
    
    if is_online and active_source == "shioaji":
        api = app.state.api
        try:
            # 我們需要回測起點往前推 3 天，確保 5分K 有足夠歷史資料計算 PDL (前一日最低點)
            start_dt_sync = (pd.to_datetime(req.start_date) - pd.Timedelta(days=3)).strftime('%Y-%m-%d')
            end_dt_sync = req.end_date
            
            need_download = False
            if not row or not row['min_ts'] or not row['max_ts']:
                need_download = True
            else:
                db_min = pd.to_datetime(row['min_ts']).strftime('%Y-%m-%d')
                db_max = pd.to_datetime(row['max_ts']).strftime('%Y-%m-%d')
                if start_dt_sync < db_min or end_dt_sync > db_max:
                    need_download = True
                    
            if need_download:
                contract = api.Contracts.Stocks[req.code]
                if not contract:
                    raise HTTPException(status_code=400, detail=f"Stock code {req.code} not found in Shioaji Contracts.")
                
                logger.info(f"Backtest data incomplete for {req.code}. Syncing from Shioaji: {start_dt_sync} to {end_dt_sync}...")
                dsd.download_stock_kbars(api, contract, start_dt_sync, end_dt_sync)
        except Exception as e:
            logger.error(f"Failed to automatically sync backtest data: {e}")
            # 即使失敗，後面還是會嘗試使用本地已有資料進行回測

            
    # 執行回測
    try:
        result = backtester.run_backtest(
            code=req.code,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_balance=req.initial_balance,
            risk_pct=req.risk_pct,
            rr_ratio=req.rr_ratio,
            htf_window=req.htf_window,
            entry_mode=req.entry_mode,
            sl_buffer_pct=req.sl_buffer_pct,
            fee_discount=req.fee_discount,
            enable_short=req.enable_short,
            holding_mode=req.holding_mode,
            ltf_timeframe=req.ltf_timeframe,
            strategy_name=req.strategy_name
        )
        if not result.get("success", False):
            raise HTTPException(status_code=400, detail=result.get("error", "回測執行失敗"))
        return result
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Backtest execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"回測執行錯誤: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=True)
