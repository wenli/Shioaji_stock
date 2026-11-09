import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.backtester import run_backtest
import download_stock_data as dsd

print(f"DB Path resolved: {dsd.get_db_name()}")

res = run_backtest(
    code="2317",
    start_date="2025-07-01",
    end_date="2026-06-30",
    initial_balance=1000000.0,
    risk_pct=0.01,
    rr_ratio=2.0,
    htf_window=20,
    entry_mode="ob_pa_limit",
    sl_buffer_pct=0.2,
    fee_discount=0.6,
    enable_short=True,
    holding_mode="swing",
    htf_timeframe="1d",
    ltf_timeframe="5k",
    strategy_name="smc"
)

print("Backtest success:", res.get("success"))
if res.get("success"):
    print("Summary:", res.get("summary"))
    print("Trades count:", len(res.get("trades", [])))
    if res.get("trades"):
        print("Sample trade:", res.get("trades")[0])
else:
    print("Error:", res.get("error"))
