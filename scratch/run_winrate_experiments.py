import sys
import os
import time
import logging
from pathlib import Path
import pandas as pd
import numpy as np
import json

sys.path.append(str(Path(__file__).resolve().parent.parent))

# Suppress verbose loggers
logging.getLogger("sentry_sdk").setLevel(logging.ERROR)
logging.getLogger("download_stock_data").setLevel(logging.WARNING)
logging.getLogger("app.backtester").setLevel(logging.WARNING)
logging.getLogger("app.smc_detector").setLevel(logging.WARNING)

from app.backtester import run_backtest

# Selected representative stocks across sectors:
# Tech Leaders: 2330 (TSMC), 2317 (Hon Hai), 2454 (MediaTek)
# High Beta / Cyclical: 2618 (EVA Air), 2610 (China Airlines), 2409 (AUO), 3481 (InnoLux)
# Financial: 2887 (Taishin)
# Traditional: 1301 (Formosa Plastics), 2002 (CSC)
# Benchmark ETF: 0050 (Taiwan Top 50)
CORE_STOCKS = ["2330", "2317", "2454", "2618", "2610", "2409", "3481", "2887", "1301", "0050"]

START_DATE = "2025-07-01"
END_DATE = "2026-09-30"

def test_config(code, config):
    try:
        res = run_backtest(
            code=code,
            start_date=START_DATE,
            end_date=END_DATE,
            initial_balance=1000000.0,
            risk_pct=config.get("risk_pct", 0.01),
            rr_ratio=config.get("rr_ratio", 2.0),
            htf_window=config.get("htf_window", 20),
            entry_mode=config.get("entry_mode", "ob_pa_limit"),
            sl_buffer_pct=config.get("sl_buffer_pct", 0.2),
            fee_discount=0.6,
            enable_short=config.get("enable_short", False),
            holding_mode=config.get("holding_mode", "swing"),
            htf_timeframe=config.get("htf_timeframe", "1d"),
            ltf_timeframe=config.get("ltf_timeframe", "5k"),
            strategy_name=config.get("strategy_name", "smc"),
            breakeven_rr=config.get("breakeven_rr", 0.0)
        )
        if res.get("success"):
            summ = res.get("summary", {})
            return {
                "success": True,
                "trades": summ.get("total_trades", 0),
                "wins": summ.get("winning_trades", 0),
                "losses": summ.get("losing_trades", 0),
                "win_rate": summ.get("win_rate_pct", 0.0),
                "return_pct": summ.get("total_return_pct", 0.0),
                "mdd": summ.get("max_drawdown_pct", 0.0),
                "pf": summ.get("profit_factor", 0.0),
                "sharpe": summ.get("sharpe_ratio", 0.0)
            }
        else:
            return {"success": False, "error": res.get("error")}
    except Exception as e:
        return {"success": False, "error": str(e)}

def run_experiment_1_strategy_types():
    print("\n=======================================================")
    print("實驗 1：橫向經典策略勝率大評比 (Across Strategy Archetypes)")
    print("SMC vs EMA Cross vs Bollinger Bands vs KD Indicator (5K & 15K)")
    print("=======================================================")
    strategies = [
        {"name": "SMC (OB PA Limit)", "strategy_name": "smc", "entry_mode": "ob_pa_limit", "rr_ratio": 2.0, "ltf_timeframe": "5k"},
        {"name": "SMC (OB PA Limit 15k)", "strategy_name": "smc", "entry_mode": "ob_pa_limit", "rr_ratio": 2.0, "ltf_timeframe": "15k"},
        {"name": "EMA Cross (5k)", "strategy_name": "ema_cross", "rr_ratio": 2.0, "ltf_timeframe": "5k"},
        {"name": "EMA Cross (15k)", "strategy_name": "ema_cross", "rr_ratio": 2.0, "ltf_timeframe": "15k"},
        {"name": "Bollinger Bands (5k)", "strategy_name": "bollinger_bands", "rr_ratio": 2.0, "ltf_timeframe": "5k"},
        {"name": "Bollinger Bands (15k)", "strategy_name": "bollinger_bands", "rr_ratio": 2.0, "ltf_timeframe": "15k"},
        {"name": "KD Indicator (5k)", "strategy_name": "kd_indicator", "rr_ratio": 2.0, "ltf_timeframe": "5k"},
        {"name": "KD Indicator (15k)", "strategy_name": "kd_indicator", "rr_ratio": 2.0, "ltf_timeframe": "15k"},
    ]
    
    results = []
    for strat in strategies:
        total_trades = 0
        total_wins = 0
        total_ret = 0.0
        stock_count = 0
        for code in CORE_STOCKS[:6]: # Test on 6 diverse stocks
            cfg = {
                "strategy_name": strat["strategy_name"],
                "entry_mode": strat.get("entry_mode", "ob_pa_limit"),
                "rr_ratio": strat["rr_ratio"],
                "ltf_timeframe": strat["ltf_timeframe"],
                "enable_short": False, # Long only first
                "holding_mode": "swing"
            }
            res = test_config(code, cfg)
            if res.get("success"):
                total_trades += res["trades"]
                total_wins += res["wins"]
                total_ret += res["return_pct"]
                stock_count += 1
        
        overall_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
        avg_ret = total_ret / stock_count if stock_count > 0 else 0.0
        results.append({
            "Strategy": strat["name"],
            "Total Trades": total_trades,
            "Wins": total_wins,
            "Overall Win Rate (%)": round(overall_wr, 2),
            "Avg Return (%)": round(avg_ret, 2)
        })
        print(f"[{strat['name']:<25}] Trades: {total_trades:4d} | Wins: {total_wins:4d} | WinRate: {overall_wr:6.2f}% | AvgRet: {avg_ret:6.2f}%")
        
    return results

if __name__ == "__main__":
    t0 = time.time()
    res1 = run_experiment_1_strategy_types()
    print(f"\nExperiment 1 completed in {time.time() - t0:.2f}s")
