import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from app.fast_stock_simulator import load_stock_data, FastStockSimulator

STOCKS = ["0050", "2317", "2454", "2303", "2618", "2610", "2409", "3481", "2887", "1301", "2002", "2615", "5351", "2337", "2324"]

configs = [
    # Golden Setup 1: High Win Rate (RR 1.5)
    {"name": "OB Retest PA (RR 1.5)", "archetype": "ob_retest_pa", "pa_filter": "tbf_or_pin", "trend_filter": "ema20", "target_rr": 1.5, "holding_mode": "swing", "use_breakeven": False},
    {"name": "DR Sweep PA (RR 1.5)", "archetype": "dr_sweep_pa", "pa_filter": "pin_only", "trend_filter": "ema20", "target_rr": 1.5, "holding_mode": "swing", "use_breakeven": False},
    # Golden Setup 2: Maximum Expectancy (RR 2.0)
    {"name": "OB Retest PA (RR 2.0)", "archetype": "ob_retest_pa", "pa_filter": "tbf_or_pin", "trend_filter": "ema20", "target_rr": 2.0, "holding_mode": "swing", "use_breakeven": False},
    {"name": "DR Sweep PA (RR 2.0)", "archetype": "dr_sweep_pa", "pa_filter": "tbf_or_pin", "trend_filter": "ema20", "target_rr": 2.0, "holding_mode": "swing", "use_breakeven": False},
    # Ultra-High Win Rate (RR 1.0)
    {"name": "DR Sweep PA (RR 1.0)", "archetype": "dr_sweep_pa", "pa_filter": "pin_only", "trend_filter": "ema20", "target_rr": 1.0, "holding_mode": "swing", "use_breakeven": False},
]

rows = []
for code in STOCKS:
    data = load_stock_data(code)
    sim = FastStockSimulator(code, data["5K"], data["60K"])
    for cfg in configs:
        trades, stats = sim.run_strategy(cfg)
        rows.append({
            "code": code,
            "strategy": cfg["name"],
            "target_rr": cfg["target_rr"],
            "trades": stats["trades"],
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": stats["win_rate"],
            "net_pnl": stats["net_pnl"],
            "profit_factor": stats["profit_factor"],
            "mdd": stats["max_drawdown"]
        })

df = pd.DataFrame(rows)
df.to_csv("scratch/focused_golden_setups_by_stock.csv", index=False)
print("Saved focused stock breakdowns to scratch/focused_golden_setups_by_stock.csv")

print("\n=== Strategy Summary Across All 15 Stocks ===")
summary = df.groupby("strategy").agg({
    "trades": "sum",
    "wins": "sum",
    "net_pnl": "mean",
    "profit_factor": "mean"
})
summary["overall_win_rate"] = (summary["wins"] / summary["trades"] * 100).round(2)
summary["net_pnl"] = summary["net_pnl"].round(2)
print(summary[["trades", "wins", "overall_win_rate", "net_pnl"]])

print("\n=== Individual Stocks with Win Rate >= 60% (Trades >= 5) ===")
top_singles = df[(df["trades"] >= 5) & (df["win_rate"] >= 60.0)].sort_values(by=["win_rate", "net_pnl"], ascending=[False, False])
print(top_singles[["code", "strategy", "trades", "wins", "win_rate", "net_pnl", "profit_factor"]].to_string(index=False))
