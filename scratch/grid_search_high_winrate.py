import sys
import os
import time
import logging
from pathlib import Path
import pandas as pd
import numpy as np
import json

sys.path.append(str(Path(__file__).resolve().parent.parent))

# Suppress loggers
logging.getLogger("sentry_sdk").setLevel(logging.ERROR)
logging.getLogger("download_stock_data").setLevel(logging.WARNING)
logging.getLogger("app.backtester").setLevel(logging.WARNING)
logging.getLogger("app.smc_detector").setLevel(logging.WARNING)

from app.backtester import run_backtest

START_DATE = "2025-07-01"
END_DATE = "2026-09-30"

# Broad selection of liquid stocks
TEST_STOCKS = [
    "2330", "2317", "2454", "2618", "2610", 
    "2409", "3481", "2887", "1301", "2002",
    "0050", "2303", "2603", "2382", "3231"
]

def run_single(code, strat_name, entry_mode, rr, htf_tf, ltf_tf, enable_short, holding="swing", be_rr=0.0):
    try:
        res = run_backtest(
            code=code,
            start_date=START_DATE,
            end_date=END_DATE,
            initial_balance=1000000.0,
            risk_pct=0.01,
            rr_ratio=rr,
            htf_window=20,
            entry_mode=entry_mode,
            sl_buffer_pct=0.2,
            fee_discount=0.6,
            enable_short=enable_short,
            holding_mode=holding,
            htf_timeframe=htf_tf,
            ltf_timeframe=ltf_tf,
            strategy_name=strat_name,
            breakeven_rr=be_rr
        )
        if res.get("success"):
            s = res.get("summary", {})
            return {
                "trades": s.get("total_trades", 0),
                "wins": s.get("winning_trades", 0),
                "losses": s.get("losing_trades", 0),
                "win_rate": s.get("win_rate_pct", 0.0),
                "ret": s.get("total_return_pct", 0.0),
                "mdd": s.get("max_drawdown_pct", 0.0),
                "pf": s.get("profit_factor", 0.0),
                "sharpe": s.get("sharpe_ratio", 0.0)
            }
        return None
    except Exception:
        return None

def experiment_rr_and_entry_modes():
    """
    掃描不同進場模式與不同盈虧比 (R:R) 的勝率與報酬表現
    """
    print("\n=======================================================", flush=True)
    print("實驗 2：SMC 進場模式 x 盈虧比 (R:R) 網格大掃描", flush=True)
    print("=======================================================", flush=True)

    entry_modes = ["fvg_top", "fvg_mid", "ob_open", "ote_705", "ob_pa_limit", "pa_ob"]
    rr_ratios = [1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
    
    records = []
    
    # 測試在 8 檔核心股票上的聚合表現
    sample_stocks = ["2317", "2454", "2618", "2409", "3481", "2887", "0050", "2610"]
    
    for em in entry_modes:
        for rr in rr_ratios:
            tot_trades = 0
            tot_wins = 0
            tot_ret = 0.0
            stocks_tested = 0
            
            for code in sample_stocks:
                out = run_single(
                    code=code,
                    strat_name="smc",
                    entry_mode=em,
                    rr=rr,
                    htf_tf="1d",
                    ltf_tf="5k",
                    enable_short=True,
                    holding="swing"
                )
                if out:
                    tot_trades += out["trades"]
                    tot_wins += out["wins"]
                    tot_ret += out["ret"]
                    stocks_tested += 1
            
            wr = (tot_wins / tot_trades * 100) if tot_trades > 0 else 0.0
            avg_ret = tot_ret / stocks_tested if stocks_tested > 0 else 0.0
            
            rec = {
                "entry_mode": em,
                "rr_ratio": rr,
                "total_trades": tot_trades,
                "wins": tot_wins,
                "win_rate": round(wr, 2),
                "avg_return": round(avg_ret, 2)
            }
            records.append(rec)
            print(f"Mode: {em:<12} | RR: {rr:3.1f} | Trades: {tot_trades:3d} | Wins: {tot_wins:3d} | WR: {wr:6.2f}% | AvgRet: {avg_ret:6.2f}%", flush=True)

    df = pd.DataFrame(records)
    df.to_csv("scratch/exp2_smc_rr_modes.csv", index=False)
    print("\nExp 2 saved to scratch/exp2_smc_rr_modes.csv", flush=True)
    return df

def experiment_timeframe_matrix():
    """
    掃描不同週期組合 (HTF x LTF) 的勝率與表現
    """
    print("\n=======================================================", flush=True)
    print("實驗 3：多週期組合 (HTF x LTF) 勝率大掃描", flush=True)
    print("=======================================================", flush=True)
    
    tf_combos = [
        ("1d", "5k"),
        ("1d", "15k"),
        ("1d", "30k"),
        ("1d", "60k"),
        ("60k", "5k"),
        ("60k", "15k")
    ]
    
    sample_stocks = ["2317", "2454", "2618", "2409", "3481", "2887", "0050", "2610"]
    records = []
    
    for htf, ltf in tf_combos:
        tot_trades = 0
        tot_wins = 0
        tot_ret = 0.0
        stocks_tested = 0
        
        for code in sample_stocks:
            out = run_single(
                code=code,
                strat_name="smc",
                entry_mode="fvg_top", # standard SMC entry
                rr=1.5, # balanced high win rate RR
                htf_tf=htf,
                ltf_tf=ltf,
                enable_short=True,
                holding="swing"
            )
            if out:
                tot_trades += out["trades"]
                tot_wins += out["wins"]
                tot_ret += out["ret"]
                stocks_tested += 1
                
        wr = (tot_wins / tot_trades * 100) if tot_trades > 0 else 0.0
        avg_ret = tot_ret / stocks_tested if stocks_tested > 0 else 0.0
        rec = {
            "htf": htf,
            "ltf": ltf,
            "total_trades": tot_trades,
            "wins": tot_wins,
            "win_rate": round(wr, 2),
            "avg_return": round(avg_ret, 2)
        }
        records.append(rec)
        print(f"HTF: {htf:<4} x LTF: {ltf:<4} | Trades: {tot_trades:3d} | Wins: {tot_wins:3d} | WR: {wr:6.2f}% | AvgRet: {avg_ret:6.2f}%", flush=True)
        
    df = pd.DataFrame(records)
    df.to_csv("scratch/exp3_timeframes.csv", index=False)
    print("\nExp 3 saved to scratch/exp3_timeframes.csv", flush=True)
    return df

if __name__ == "__main__":
    t0 = time.time()
    df2 = experiment_rr_and_entry_modes()
    df3 = experiment_timeframe_matrix()
    print(f"\nAll grid searches completed in {time.time() - t0:.2f}s", flush=True)
