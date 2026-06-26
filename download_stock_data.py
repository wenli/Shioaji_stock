import sqlite3
import os
import time
import logging
import json
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
import shioaji as sj

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Load Environment Variables
load_dotenv()
DEFAULT_START_DAYS = int(os.getenv("DEFAULT_START_DAYS", "30"))
YAHOO_60K_BACKTRACK_DAYS = int(os.getenv("YAHOO_60K_BACKTRACK_DAYS", "365"))
YAHOO_1D_BACKTRACK_DAYS = int(os.getenv("YAHOO_1D_BACKTRACK_DAYS", "1825"))
CONFIG_FILE = "config.json"


def get_active_source() -> str:
    """Reads active source from config.json. Defaults to 'shioaji'."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("active_source", "shioaji")
    except Exception as e:
        logger.error(f"Error reading config.json: {e}")
    return "shioaji"

def set_active_source(source: str) -> None:
    """Writes active source to config.json."""
    try:
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        config["active_source"] = source
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error writing config.json: {e}")

def get_db_name() -> str:
    source = get_active_source()
    if source == "yahoo":
        return "Y.db"
    return os.getenv("DB_NAME", "Shioaji.db")


class SyncStatusTracker:
    def __init__(self):
        self.states = {}

    def set_status(self, code: str, status: str, error: str = ""):
        self.states[code] = {
            "status": status,
            "error": error,
            "timestamp": time.time()
        }

    def get_status(self, code: str) -> dict:
        return self.states.get(code, {
            "status": "idle",
            "error": "",
            "timestamp": None
        })

    def remove(self, code: str):
        if code in self.states:
            del self.states[code]

sync_tracker = SyncStatusTracker()

def get_db_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with timeout for busy handling."""
    db_name = get_db_name()
    db_path = Path(db_name)
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
         
    conn = sqlite3.connect(db_name, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initializes the SQLite database creating tables for stocks and wish list."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Create wish_list table
        logger.info("Checking/Creating table: wish_list")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wish_list (
                code TEXT PRIMARY KEY,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active',
                last_sync_ts TIMESTAMP
            )
        """)
        
        # Create stock K-line tables
        tables = [
            "stock1k", "stock5k", "stock15k",
            "stock30k", "stock60k", "stock1d"
        ]
        for table in tables:
            logger.info(f"Checking/Creating table: {table}")
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    code TEXT,
                    ts TIMESTAMP,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    PRIMARY KEY (code, ts)
                )
            """)
            
        conn.commit()
        logger.info("Database initialization successful.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()

# Wish List DB helpers
def get_wish_list() -> list:
    """Gets all stocks in the wish list."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT code, name, created_at, status, last_sync_ts FROM wish_list ORDER BY code ASC")
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error reading wish_list: {e}")
        return []
    finally:
        conn.close()

def add_to_wish_list(code: str, name: str) -> bool:
    """Adds a stock to the wish list."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO wish_list (code, name, status) VALUES (?, ?, 'active')",
            (code, name)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding {code} to wish_list: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def remove_from_wish_list(code: str, delete_data: bool = False) -> bool:
    """Removes a stock from the wish list and optionally deletes its K-line data."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM wish_list WHERE code = ?", (code,))
        if delete_data:
            tables = ["stock1k", "stock5k", "stock15k", "stock30k", "stock60k", "stock1d"]
            for table in tables:
                cursor.execute(f"DELETE FROM {table} WHERE code = ?", (code,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error removing {code} from wish_list: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def update_wish_list_sync_time(code: str, ts: str) -> None:
    """Updates the last synchronized timestamp of a stock."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE wish_list SET last_sync_ts = ? WHERE code = ?", (ts, code))
        conn.commit()
    except Exception as e:
        logger.error(f"Error updating last_sync_ts for {code}: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_last_ts(table: str, code: str) -> str:
    """Gets the latest timestamp for a stock in a table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT MAX(ts) FROM {table} WHERE code = ?", (code,))
        result = cursor.fetchone()
        if result and result[0] is not None:
            return str(result[0])
        return ""
    except Exception as e:
        logger.error(f"Error getting last ts from {table}: {e}")
        return ""
    finally:
        conn.close()

def save_to_db(df: pd.DataFrame, table_name: str) -> int:
    """Saves DataFrame to specified SQLite table using INSERT OR IGNORE."""
    if df.empty:
        return 0

    conn = get_db_connection()
    cursor = conn.cursor()
    
    rows = list(df[['code', 'ts', 'open', 'high', 'low', 'close', 'volume']].itertuples(index=False, name=None))

    try:
        cursor.executemany(f"""
            INSERT OR IGNORE INTO {table_name} 
            (code, ts, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
        inserted = cursor.rowcount
        return inserted if inserted >= 0 else len(rows)
    except Exception as e:
        logger.error(f"Error saving to {table_name}: {e}")
        conn.rollback()
        return 0
    finally:
        conn.close()

def aggregate_kbars(df_1k: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Aggregates 1k K-bars into higher timeframes (5m, 15m, 30m, 60m, 1d)."""
    if df_1k.empty:
        return pd.DataFrame()

    agg_rules = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }

    # Resample with left closing/labeling (standard Taiwan Stock style)
    resampled = df_1k.resample(interval, closed='left', label='left').agg(agg_rules)
    
    # Drop NaNs that occur outside trading hours
    resampled.dropna(subset=['open'], inplace=True)
    
    if not df_1k.empty:
         resampled['code'] = df_1k['code'].iloc[0]
         
    resampled.reset_index(inplace=True)
    resampled.rename(columns={'ts_datetime': 'ts'}, inplace=True)
    resampled['ts'] = resampled['ts'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    return resampled

def download_stock_kbars(api, contract, start_date: str, end_date: str) -> dict:
    """Downloads 1k K-bars for a stock, aggregates to higher timeframes, and saves to DB."""
    code = contract.code
    logger.info(f"Downloading 1k K-bars for Stock {code} from {start_date} to {end_date}...")

    try:
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        # 由於 Shioaji API 每次查詢 K 線區間不能超過 30 天，
        # 我們將 start_date 到 end_date 區間拆分成多個不超過 29 天的區間
        chunks = []
        current_start = start_dt
        while current_start <= end_dt:
            current_end = min(current_start + pd.Timedelta(days=29), end_dt)
            chunks.append((current_start.strftime('%Y-%m-%d'), current_end.strftime('%Y-%m-%d')))
            current_start = current_end + pd.Timedelta(days=1)
            
        logger.info(f"Splitted request into {len(chunks)} chunk(s).")
        
        all_kbars_list = []
        for index, (s_str, e_str) in enumerate(chunks):
            logger.info(f"Fetching chunk {index+1}/{len(chunks)}: {s_str} to {e_str}")
            
            # 多個 chunk 下載時，小睡 0.5 秒避免觸發 Rate Limit
            if index > 0:
                time.sleep(0.5)
                
            kbars = api.kbars(contract=contract, start=s_str, end=e_str)
            
            if kbars and hasattr(kbars, 'ts') and len(kbars.ts) > 0:
                df_chunk = pd.DataFrame({
                    'ts': kbars.ts,
                    'open': kbars.Open,
                    'high': kbars.High,
                    'low': kbars.Low,
                    'close': kbars.Close,
                    'volume': kbars.Volume
                })
                all_kbars_list.append(df_chunk)
            else:
                logger.info(f"No data returned for chunk {s_str} to {e_str}")
                
        if not all_kbars_list:
            logger.warning(f"No data returned for Stock {code} in the entire range.")
            sync_tracker.set_status(code, "success")
            return {}
            
        # 合併所有 chunk 的 K 線資料
        df_1k = pd.concat(all_kbars_list, ignore_index=True)
        # 去除可能重疊的 ts
        df_1k.drop_duplicates(subset=['ts'], inplace=True)
        # 依時間戳排序
        df_1k.sort_values(by='ts', inplace=True)
        
        df_1k['code'] = code

        # Convert ts to datetime index for resampling
        df_1k['ts_datetime'] = pd.to_datetime(df_1k['ts'], unit='ns')
        df_1k.set_index('ts_datetime', inplace=True)

        stats = {}
        # Save 1k directly
        df_1k_save = df_1k.copy()
        df_1k_save.reset_index(inplace=True)
        df_1k_save['ts'] = df_1k_save['ts_datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
        inserted_1k = save_to_db(df_1k_save, "stock1k")
        stats["1k"] = inserted_1k
        
        # 2. Aggregate and Save others
        intervals = {
            "5k": "5min",
            "15k": "15min",
            "30k": "30min",
            "60k": "60min",
            "1d": "D"
        }

        for name, rule in intervals.items():
            logger.info(f"Aggregating {code} to {name}...")
            df_agg = aggregate_kbars(df_1k, rule)
            inserted = save_to_db(df_agg, f"stock{name}")
            stats[name] = inserted

        # Update last sync time in wish_list
        if not df_1k_save.empty:
            last_ts = df_1k_save['ts'].iloc[-1]
            update_wish_list_sync_time(code, last_ts)

        logger.info(f"Sync Stats for Stock {code}: {stats}")
        sync_tracker.set_status(code, "success")
        return stats

    except Exception as e:
        logger.error(f"Download/Aggregation pipeline failed for Stock {code}: {e}")
        sync_tracker.set_status(code, "failed", error=str(e))
        return {}

def download_yahoo_kbars(code: str, start_date: str, end_date: str) -> dict:
    """Downloads stock data from Yahoo Finance for intervals: 5m, 15m, 30m, 60m, 1d.
    No 1m data is downloaded. Timezone is aligned to Asia/Taipei.
    1-second sleep is introduced between individual requests to prevent IP ban.
    """
    import yfinance as yf
    
    # 1. Ticker Suffix Resolution (.TW or .TWO)
    tickers_to_try = [f"{code}.TW", f"{code}.TWO"]
    selected_ticker = None
    
    for ticker in tickers_to_try:
        try:
            logger.info(f"Testing Yahoo ticker: {ticker}")
            df_test = yf.download(tickers=ticker, period="1d", progress=False)
            if df_test is not None and not df_test.empty:
                selected_ticker = ticker
                logger.info(f"Successfully matched Yahoo ticker: {selected_ticker}")
                break
        except Exception as e:
            logger.warning(f"Failed to test Yahoo ticker {ticker}: {e}")
        time.sleep(1.0)
        
    if not selected_ticker:
        logger.error(f"Cannot find valid Yahoo ticker for code: {code}")
        sync_tracker.set_status(code, "failed", error="Valid Yahoo ticker not found (.TW or .TWO)")
        return {}

    # 2. Map tables to yfinance intervals
    intervals = {
        "stock5k": "5m",
        "stock15k": "15m",
        "stock30k": "30m",
        "stock60k": "60m",
        "stock1d": "1d"
    }

    stats = {}
    
    try:
        for table_name, interval in intervals.items():
            last_ts = get_last_ts(table_name, code)
            
            if last_ts:
                # To prevent gaps, step back 1 day from last_ts for yfinance query start
                start_dt = pd.to_datetime(last_ts) - pd.Timedelta(days=1)
                start_str = start_dt.strftime('%Y-%m-%d')
            else:
                if table_name == "stock60k":
                    backtrack_days = YAHOO_60K_BACKTRACK_DAYS
                elif table_name == "stock1d":
                    backtrack_days = YAHOO_1D_BACKTRACK_DAYS
                else:
                    # Limit short periods (5m, 15m, 30m) to max 55 days to avoid Yahoo 60-day limit error
                    backtrack_days = min(DEFAULT_START_DAYS, 55)
                    
                start_dt = pd.Timestamp.now() - pd.Timedelta(days=backtrack_days)
                start_str = start_dt.strftime('%Y-%m-%d')


                
            end_str = end_date
            
            logger.info(f"Downloading Yahoo {interval} for {selected_ticker} from {start_str} to {end_str}...")
            time.sleep(1.0) # sleep 1 second to comply with rate limiting
            
            df = yf.download(tickers=selected_ticker, start=start_str, end=end_str, interval=interval, progress=False)
            
            if df is None or df.empty:
                logger.info(f"No data returned for Yahoo {interval} for {selected_ticker}")
                stats[table_name] = 0
                continue
                
            df.reset_index(inplace=True)
            
            # Normalize MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] for col in df.columns]
            
            time_col = None
            for col in ['Datetime', 'Date', 'index', 'timestamp']:
                if col in df.columns:
                    time_col = col
                    break
            
            if not time_col:
                logger.error(f"Cannot find time column in yfinance output: {df.columns}")
                stats[table_name] = 0
                continue
                
            df.rename(columns={
                time_col: 'ts_raw',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            }, inplace=True)
            
            # Align Timezone to Asia/Taipei
            ts_series = pd.to_datetime(df['ts_raw'])
            if ts_series.dt.tz is not None:
                ts_series = ts_series.dt.tz_convert('Asia/Taipei')
            else:
                ts_series = ts_series.dt.tz_localize('Asia/Taipei')
                
            df['ts'] = ts_series.dt.strftime('%Y-%m-%d %H:%M:%S')
            df['code'] = code
            
            df_save = df[['code', 'ts', 'open', 'high', 'low', 'close', 'volume']].copy()
            df_save['open'] = df_save['open'].astype(float)
            df_save['high'] = df_save['high'].astype(float)
            df_save['low'] = df_save['low'].astype(float)
            df_save['close'] = df_save['close'].astype(float)
            df_save['volume'] = df_save['volume'].fillna(0).astype(int)
            
            df_save.sort_values(by='ts', inplace=True)
            
            # Save to Database Y.db
            inserted = save_to_db(df_save, table_name)
            stats[table_name] = inserted
            
            if not df_save.empty:
                last_ts_written = df_save['ts'].iloc[-1]
                update_wish_list_sync_time(code, last_ts_written)

        logger.info(f"Yahoo Sync Stats for Stock {code}: {stats}")
        sync_tracker.set_status(code, "success")
        return stats
        
    except Exception as e:
        logger.error(f"Yahoo Download pipeline failed for Stock {code}: {e}")
        sync_tracker.set_status(code, "failed", error=str(e))
        return {}

def get_shioaji_client():
    """Initializes and logs into Shioaji client using .env credentials."""
    api_key = os.getenv("SHIOAJI_API_KEY")
    secret_key = os.getenv("SHIOAJI_SECRET_KEY")
    env = os.getenv("SHIOAJI_ENV", "simulation")
    simulation = (env == "simulation")

    if not api_key or not secret_key:
        logger.error("SHIOAJI_API_KEY or SHIOAJI_SECRET_KEY missing in .env")
        return None

    try:
        logger.info(f"Initializing Shioaji Stock Client (Simulation={simulation})...")
        api = sj.Shioaji(simulation=simulation)
        api.login(api_key, secret_key)
        logger.info("Shioaji Stock Login Successful.")
        return api
    except Exception as e:
        logger.error(f"Shioaji Stock Login Failed: {e}")
        return None

def sync_to_latest(api, code: str) -> dict:
    """Synchronizes K-lines from the last known timestamp up to today for a stock code."""
    logger.info(f"Checking sync breakpoint for Stock {code}...")
    
    sync_tracker.set_status(code, "syncing")
    
    active_source = get_active_source()
    if active_source == "yahoo":
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=DEFAULT_START_DAYS)).strftime('%Y-%m-%d')
        end_date = pd.Timestamp.now().strftime('%Y-%m-%d')
        try:
            return download_yahoo_kbars(code, start_date, end_date)
        except Exception as e:
            err_msg = f"Yahoo Download pipeline failed for Stock {code}: {e}"
            logger.error(err_msg)
            sync_tracker.set_status(code, "failed", error=err_msg)
            return {}
            
    # 取得股票合約 (Shioaji 模式)
    try:
        contract = api.Contracts.Stocks[code]
        if not contract:
            err_msg = f"Stock contract for {code} not found in Shioaji database."
            logger.error(err_msg)
            sync_tracker.set_status(code, "failed", error=err_msg)
            return {}
    except Exception as e:
        err_msg = f"Failed to lookup Stock contract for {code}: {e}"
        logger.error(err_msg)
        sync_tracker.set_status(code, "failed", error=err_msg)
        return {}
        
    last_ts = get_last_ts("stock1k", code)
    if not last_ts:
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=DEFAULT_START_DAYS)).strftime('%Y-%m-%d')
        logger.info(f"No existing data for {code}. Starting full sync from {start_date}")
    else:
        start_date = pd.to_datetime(last_ts).strftime('%Y-%m-%d')
        logger.info(f"Found last TS for {code}: {last_ts} ({start_date}). Syncing onward.")

    end_date = pd.Timestamp.now().strftime('%Y-%m-%d')
    
    try:
        return download_stock_kbars(api, contract, start_date, end_date)
    except Exception as e:
        err_msg = f"Download/Aggregation pipeline failed for Stock {code}: {e}"
        logger.error(err_msg)
        sync_tracker.set_status(code, "failed", error=err_msg)
        return {}

if __name__ == "__main__":
    logger.info("Starting Stock Database Initialization...")
    init_db()
    logger.info("Finished.")
