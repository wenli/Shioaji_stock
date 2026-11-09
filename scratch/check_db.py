import sqlite3
import os

db_dir = r"C:\Intel\Database"
for fname in ["Shioaji.db", "Shioaji-future.db", "SK.db", "Y.db"]:
    db_path = os.path.join(db_dir, fname)
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"=== {fname} ({os.path.getsize(db_path)/1024/1024:.1f} MB) ===", flush=True)
        for t in tables:
            tname = t[0]
            try:
                cnt = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
                cols = [col[1] for col in conn.execute(f"PRAGMA table_info({tname})").fetchall()]
                print(f"  Table: {tname:15} | Rows: {cnt:10} | Cols: {','.join(cols[:5])}", flush=True)
            except Exception as e:
                print(f"  Table: {tname:15} | Error: {e}", flush=True)
        conn.close()
