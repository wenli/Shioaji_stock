import time
import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path
import json

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.append(str(Path(__file__).resolve().parent.parent))
from app.fast_stock_simulator import load_stock_data, FastStockSimulator

# 15 Highly Diverse Liquid Representative Stocks
STOCKS = [
    "0050",  # Taiwan Top 50 ETF
    "2317",  # Hon Hai (EMS / AI server)
    "2454",  # MediaTek (IC Design / High Beta)
    "2303",  # UMC (Foundry / Value)
    "2618",  # EVA Air (Aviation / Tourism)
    "2610",  # China Airlines (Aviation / Cargo)
    "2409",  # AUO (Display / Cyclical)
    "3481",  # Innolux (Display / High Volatility)
    "2887",  # Taishin FHC (Financial)
    "1301",  # Formosa Plastics (Petrochemical)
    "2002",  # China Steel (Commodity)
    "2615",  # Wan Hai (Container Shipping)
    "5351",  # Etron (Memory / High Momentum)
    "2337",  # Macronix (Flash / Semiconductor)
    "2324"   # Compal (Notebook / ODM)
]

def run_grand_study():
    print("=" * 80)
    print(" [GRAND WIN-RATE QUANTITATIVE STUDY] Taiwan Stock Highest Win-rate Study")
    print(f" Target Universe: 15 Diverse Liquid Leaders across sectors (2025/07 - 2026/09)")
    print("=" * 80, flush=True)

    t0 = time.time()
    sims = {}
    for code in STOCKS:
        data = load_stock_data(code)
        sim = FastStockSimulator(code, data["5K"], data["60K"])
        sims[code] = sim
        print(f"  [Loaded] {code:5s} | 5K bars: {len(data['5K']):5d} | 60K bars: {len(data['60K']):4d}", flush=True)
    
    print(f"\nAll 15 stocks pre-computed successfully in {time.time()-t0:.2f}s\n", flush=True)

    # Grid Dimensions
    archetypes = ["ob_retest_pa", "dr_sweep_pa", "dr_discount_pa"]
    pa_filters = ["tbf_or_pin", "pin_only", "tbf_only", "all"]
    trend_filters = ["ema20", "none"]
    rrs = [0.8, 1.0, 1.2, 1.4, 1.5, 1.6, 1.8, 2.0, 2.5]
    holding_modes = ["swing", "day_trade"]
    bes = [False, True]

    grid = []
    for arch in archetypes:
        for paf in pa_filters:
            for tf in trend_filters:
                for rr in rrs:
                    for hm in holding_modes:
                        for be in bes:
                            grid.append({
                                "archetype": arch,
                                "pa_filter": paf,
                                "trend_filter": tf,
                                "target_rr": rr,
                                "holding_mode": hm,
                                "use_breakeven": be
                            })

    total_runs = len(grid)
    print(f"Starting parameter sweep: {total_runs} configs x {len(STOCKS)} stocks = {total_runs * len(STOCKS)} simulations...", flush=True)

    sim_start = time.time()
    aggregated_results = []
    per_stock_records = []

    for idx, cfg in enumerate(grid):
        tot_trades = 0
        tot_wins = 0
        tot_losses = 0
        stock_pnls = []
        stock_wins = {}
        stock_trades = {}

        for code, sim in sims.items():
            trades, stats = sim.run_strategy(cfg)
            t_count = stats["trades"]
            w_count = stats["wins"]
            tot_trades += t_count
            tot_wins += w_count
            tot_losses += stats["losses"]
            stock_pnls.append(stats["net_pnl"])
            stock_trades[code] = t_count
            stock_wins[code] = w_count

        if tot_trades >= 40: # Minimum 40 trades across 15 stocks
            wr = (tot_wins / tot_trades) * 100.0
            avg_pnl = float(np.mean(stock_pnls))
            
            rec = dict(cfg)
            rec.update({
                "total_trades": tot_trades,
                "wins": tot_wins,
                "losses": tot_losses,
                "win_rate": round(wr, 2),
                "avg_net_pnl": round(avg_pnl, 2),
                "pnl_std": round(float(np.std(stock_pnls)), 2),
                "positive_stocks": sum(1 for p in stock_pnls if p > 0)
            })
            aggregated_results.append(rec)

            # Store top candidate per-stock breakdown
            if wr >= 60.0 or (wr >= 55.0 and avg_pnl > 2.0):
                for code in STOCKS:
                    c_trades = stock_trades[code]
                    c_wins = stock_wins[code]
                    c_wr = (c_wins / c_trades * 100.0) if c_trades > 0 else 0.0
                    per_stock_records.append({
                        "archetype": cfg["archetype"],
                        "pa_filter": cfg["pa_filter"],
                        "trend_filter": cfg["trend_filter"],
                        "target_rr": cfg["target_rr"],
                        "holding_mode": cfg["holding_mode"],
                        "use_breakeven": cfg["use_breakeven"],
                        "code": code,
                        "trades": c_trades,
                        "wins": c_wins,
                        "win_rate": round(c_wr, 2)
                    })

    sim_time = time.time() - sim_start
    print(f"\nAll simulations completed in {sim_time:.2f}s! ({total_runs * len(STOCKS) / sim_time:.1f} sims/sec)", flush=True)

    df_agg = pd.DataFrame(aggregated_results)
    df_agg.to_csv("scratch/grand_study_aggregate.csv", index=False)
    
    if per_stock_records:
        df_per_stock = pd.DataFrame(per_stock_records)
        df_per_stock.to_csv("scratch/grand_study_per_stock.csv", index=False)

    # 1. Highest Win Rate Overall
    print("\n" + "=" * 95)
    print(" [RANK 1] Absolute Highest Win Rate Top 10 (Total Trades >= 40)")
    print("=" * 95)
    top_wr = df_agg.sort_values(by=["win_rate", "total_trades"], ascending=[False, False])
    cols_display = ["archetype", "pa_filter", "trend_filter", "target_rr", "holding_mode", "use_breakeven", "total_trades", "win_rate", "avg_net_pnl", "positive_stocks"]
    print(top_wr[cols_display].head(10).to_string(index=False), flush=True)

    # 2. Highest Win Rate with POSITIVE EXPECTANCY (Net PnL > 0)
    print("\n" + "=" * 95)
    print(" [RANK 2] Actionable Highest Win Rate with Positive Net Return (Net Return > 0 & Trades >= 40)")
    print("=" * 95)
    profitable_high_wr = df_agg[df_agg["avg_net_pnl"] > 0].sort_values(by=["win_rate", "avg_net_pnl"], ascending=[False, False])
    print(profitable_high_wr[cols_display].head(10).to_string(index=False), flush=True)

    # 3. Highest Net PnL
    print("\n" + "=" * 95)
    print(" [RANK 3] Maximum Total Return Top 10 Configurations")
    print("=" * 95)
    top_pnl = df_agg.sort_values(by=["avg_net_pnl", "win_rate"], ascending=[False, False])
    print(top_pnl[cols_display].head(10).to_string(index=False), flush=True)

    # 4. R:R vs Win Rate Curve Analysis
    print("\n" + "=" * 95)
    print(" [CURVE] R:R vs Win Rate & PnL Decay Matrix (Swing + 60K EMA20)")
    print("=" * 95)
    rr_curve = df_agg[
        (df_agg["holding_mode"] == "swing") & 
        (df_agg["trend_filter"] == "ema20") & 
        (df_agg["pa_filter"] == "tbf_or_pin") &
        (df_agg["use_breakeven"] == False)
    ].sort_values(by=["archetype", "target_rr"])
    print(rr_curve[["archetype", "target_rr", "total_trades", "win_rate", "avg_net_pnl"]].to_string(index=False), flush=True)

    # 5. Day Trade vs Swing Mode Comparison
    print("\n" + "=" * 95)
    print(" [COMPARISON] Day Trade vs Swing Mode Performance")
    print("=" * 95)
    dt_vs_swing = df_agg[
        (df_agg["archetype"] == "ob_retest_pa") &
        (df_agg["pa_filter"] == "tbf_or_pin") &
        (df_agg["trend_filter"] == "ema20") &
        (df_agg["target_rr"].isin([1.0, 1.5, 2.0])) &
        (df_agg["use_breakeven"] == False)
    ].sort_values(by=["target_rr", "holding_mode"])
    print(dt_vs_swing[["target_rr", "holding_mode", "total_trades", "win_rate", "avg_net_pnl"]].to_string(index=False), flush=True)

    return df_agg

if __name__ == "__main__":
    run_grand_study()
