import sys
from pathlib import Path
# Add parent directory to path so we can import from root
sys.path.append(str(Path(__file__).resolve().parent.parent))

import logging
import sqlite3
from download_stock_data import (
    init_db,
    get_shioaji_client,
    add_to_wish_list,
    sync_to_latest,
    get_db_connection
)

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

def verify_db_records(code: str):
    """Queries DB to check if data is written correctly."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tables = [
        "stock1k", "stock5k", "stock15k",
        "stock30k", "stock60k", "stock1d"
    ]
    
    logger.info("=== DB Verification ===")
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*), MIN(ts), MAX(ts) FROM {table} WHERE code = ?", (code,))
            count, min_ts, max_ts = cursor.fetchone()
            logger.info(f"Table {table:8s} | Count: {count:5d} | Range: {min_ts} ~ {max_ts}")
        except Exception as e:
            logger.error(f"Error checking table {table}: {e}")
            
    conn.close()

def main():
    logger.info("Starting integration test for Shioaji Stock Updater...")
    
    # 1. Initialize DB
    init_db()
    
    # 2. Login to Shioaji
    api = get_shioaji_client()
    if not api:
        logger.error("Failed to login to Shioaji. Test aborted.")
        return
        
    test_code = "2330"  # 台積電 TSMC
    test_name = "台積電"
    
    try:
        # 3. Add to wish list
        logger.info(f"Adding test stock {test_code} ({test_name}) to wish list...")
        success = add_to_wish_list(test_code, test_name)
        if not success:
            logger.error("Failed to add test stock to wish list.")
            return
            
        # 4. Trigger Sync
        logger.info(f"Syncing data for stock {test_code}...")
        stats = sync_to_latest(api, test_code)
        logger.info(f"Sync complete. Stats: {stats}")
        
        # 5. Verify Database Records
        verify_db_records(test_code)
        
    except Exception as e:
        logger.exception(f"Test encountered unexpected error: {e}")
    finally:
        logger.info("Logging out from Shioaji...")
        api.logout()
        logger.info("Test finished.")

if __name__ == "__main__":
    main()
