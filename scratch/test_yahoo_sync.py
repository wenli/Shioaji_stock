import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import download_stock_data as dsd
import sqlite3

def run_test():
    import os
    if os.path.exists("Y.db"):
        print("Removing existing Y.db for clean backtrack test...")
        try:
            os.remove("Y.db")
        except Exception as e:
            print(f"Warning: Could not remove Y.db: {e}")
            
    print("Setting active source to 'yahoo'...")
    dsd.set_active_source("yahoo")
    
    print(f"Current DB Name: {dsd.get_db_name()}")
    
    print("Initializing Y.db database...")

    dsd.init_db()
    
    # 測試下載 2330 台積電
    print("Downloading Yahoo K-lines for 2330...")
    stats = dsd.download_yahoo_kbars("2330", "2026-06-01", "2026-06-25")
    print(f"Download Stats: {stats}")
    
    # 驗證 Y.db 是否有資料
    print("Verifying database records...")
    conn = sqlite3.connect("Y.db")
    cursor = conn.cursor()
    
    tables = ["stock5k", "stock15k", "stock30k", "stock60k", "stock1d"]
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"Table {table} record count: {count}")
        
        if count > 0:
            cursor.execute(f"SELECT * FROM {table} LIMIT 1")
            row = cursor.fetchone()
            print(f"  Sample row from {table}: {row}")
            
    conn.close()

if __name__ == "__main__":
    run_test()
