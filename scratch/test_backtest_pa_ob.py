import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import logging
from app.backtester import run_backtest
from download_stock_data import get_db_connection

logging.basicConfig(level=logging.INFO)

def test_pa_ob_backtest():
    conn = get_db_connection()
    # Check available stock codes in stock1d
    stocks = conn.execute("SELECT DISTINCT code FROM stock1d LIMIT 5").fetchall()
    conn.close()
    
    if not stocks:
        print("No stock data found in DB.")
        return
        
    code = stocks[0]['code']
    print(f"Testing pa_ob backtest for code: {code}")
    
    res = run_backtest(
        code=code,
        start_date="2025-01-01",
        end_date="2026-08-20",
        initial_balance=1000000.0,
        risk_pct=0.01,
        rr_ratio=2.0,
        htf_window=20,
        entry_mode="pa_ob",
        sl_buffer_pct=0.2,
        fee_discount=0.6,
        enable_short=True,
        holding_mode="swing",
        htf_timeframe="1d",
        ltf_timeframe="5k",
        strategy_name="smc"
    )
    
    print("Success:", res.get("success"))
    if res.get("success"):
        summary = res.get("summary", {})
        print("Summary:", summary)
        trades = res.get("trades", [])
        print(f"Total trades executed: {len(trades)}")
        for t in trades[:5]:
            print("Trade sample:", t)
    else:
        print("Error:", res.get("error"))

if __name__ == "__main__":
    test_pa_ob_backtest()
