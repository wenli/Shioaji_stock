import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import download_stock_data as dsd
from app import backtester
import sqlite3


def test_backtest():
    print("Setting active source to 'yahoo'...")
    dsd.set_active_source("yahoo")
    
    print(f"Current DB Name: {dsd.get_db_name()}")
    
    # 直接用 sqlite3 驗證該區間的資料是否存在
    conn = sqlite3.connect("Y.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stock60k LIMIT 3")
    print(f"Raw stock60k full rows: {cursor.fetchall()}")
    cursor.execute("SELECT DISTINCT code FROM stock60k")
    print(f"Distinct codes in stock60k: {cursor.fetchall()}")
    cursor.execute("SELECT COUNT(*) FROM stock60k WHERE code = '3481'")
    print(f"Total count for 3481 in stock60k: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM stock1d WHERE code = '3481'")
    print(f"Total count for 3481 in stock1d: {cursor.fetchone()[0]}")
    conn.close()


    
    print("Running 60k SMC backtest for stock 3481...")
    result = backtester.run_backtest(
        code="3481",
        start_date="2025-07-01",
        end_date="2026-06-25",
        initial_balance=1000000.0,
        risk_pct=0.01,
        rr_ratio=2.0,
        htf_window=20,
        entry_mode="fvg_top",
        sl_buffer_pct=0.2,
        fee_discount=0.6,
        enable_short=True,
        holding_mode="swing",
        ltf_timeframe="60k",
        strategy_name="smc"
    )
    
    print(f"Backtest success: {result.get('success')}")
    if result.get('success'):
        summary = result.get('summary')
        print("Backtest Summary:")
        print(f"  Total Trades: {summary.get('total_trades')}")
        print(f"  Win Rate: {summary.get('win_rate_pct')}%")
        print(f"  Total Return: {summary.get('total_return_pct')}%")
        print(f"  Final Balance: {summary.get('final_balance')}")
        print(f"  Max Drawdown: {summary.get('max_drawdown_pct')}%")
        
        trades = result.get('trades')
        print(f"Number of trades logged: {len(trades)}")
        if len(trades) > 0:
            print(f"  Sample Trade: {trades[0]}")
    else:
        print(f"Error: {result.get('error')}")

if __name__ == "__main__":
    test_backtest()
