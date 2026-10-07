import time
import sys
import pandas as pd
import numpy as np
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.fast_stock_simulator import load_stock_data, FastStockSimulator

TEST_STOCKS = ["2317", "0050", "2454", "2618", "2409"]

def run_fast_grid():
    print("=" * 70)
    print(" [FAST VECTORIZED SWEEP] Testing High-Winrate Configurations")
    print("=" * 70)

    # 1. Preload data and create simulators
    t0 = time.time()
    sims = {}
    for code in TEST_STOCKS:
        data = load_stock_data(code)
        sim = FastStockSimulator(code, data["5K"], data["60K"])
        sims[code] = sim
        print(f"Loaded & Pre-computed {code}: 5K={len(data['5K'])}, 60K={len(data['60K'])}")
    print(f"All {len(TEST_STOCKS)} stocks initialized in {time.time()-t0:.2f}s\n")

    # 2. Build grid
    archetypes = ["dr_discount_pa", "dr_sweep_pa", "ob_retest_pa"]
    pa_filters = ["tbf_only", "pin_only", "pz_only", "tbf_or_pin", "all"]
    trend_filters = ["ema20", "ema_golden", "none"]
    rrs = [0.8, 1.0, 1.2, 1.5, 2.0]
    holding_modes = ["swing", "day_trade"]
    bes = [True, False]

    param_grid = []
    for arch in archetypes:
        for paf in pa_filters:
            for tf in trend_filters:
                for rr in rrs:
                    for hm in holding_modes:
                        for be in bes:
                            param_grid.append({
                                "archetype": arch,
                                "pa_filter": paf,
                                "trend_filter": tf,
                                "target_rr": rr,
                                "holding_mode": hm,
                                "use_breakeven": be
                            })

    total_runs = len(param_grid)
    print(f"Testing {total_runs} parameter combinations across {len(TEST_STOCKS)} stocks ({total_runs * len(TEST_STOCKS)} total simulations)...")

    results = []
    start_sim = time.time()

    for idx, cfg in enumerate(param_grid):
        tot_trades = 0
        tot_wins = 0
        tot_pnl = 0.0
        stock_success = 0

        for code, sim in sims.items():
            trades, stats = sim.run_strategy(cfg)
            tot_trades += stats["trades"]
            tot_wins += stats["wins"]
            tot_pnl += stats["net_pnl"]
            if stats["trades"] >= 5:
                stock_success += 1

        if tot_trades >= 30:  # Minimum statistical sample across 5 stocks
            wr = (tot_wins / tot_trades) * 100.0
            avg_pnl = tot_pnl / len(TEST_STOCKS)
            rec = dict(cfg)
            rec.update({
                "trades": tot_trades,
                "wins": tot_wins,
                "win_rate": round(wr, 2),
                "avg_net_pnl": round(avg_pnl, 2),
                "stocks_active": stock_success
            })
            results.append(rec)

    elapsed = time.time() - start_sim
    print(f"\nAll simulations completed in {elapsed:.2f}s! ({len(param_grid)*len(TEST_STOCKS)/elapsed:.1f} sims/sec)")

    df = pd.DataFrame(results)
    if df.empty:
        print("No strategy met the 30 trade minimum threshold.")
        return

    df.to_csv("scratch/fast_sweep_high_winrate_results.csv", index=False)
    print(f"Saved {len(df)} candidate strategies to scratch/fast_sweep_high_winrate_results.csv")

    # Filter for High Win Rate (>= 50%)
    high_wr = df[df["win_rate"] >= 50.0].sort_values(by=["win_rate", "avg_net_pnl"], ascending=[False, False])
    print("\n" + "=" * 80)
    print(" TOP 10 HIGHEST WIN-RATE STRATEGIES (Sample Trades >= 30, Win Rate >= 50%)")
    print("=" * 80)
    cols = ["archetype", "pa_filter", "trend_filter", "target_rr", "holding_mode", "use_breakeven", "trades", "win_rate", "avg_net_pnl"]
    print(high_wr[cols].head(15).to_string(index=False))

    # Also show Top Net PnL Strategies
    top_pnl = df.sort_values(by=["avg_net_pnl", "win_rate"], ascending=[False, False])
    print("\n" + "=" * 80)
    print(" TOP 10 HIGHEST NET RETURN STRATEGIES (Sample Trades >= 30)")
    print("=" * 80)
    print(top_pnl[cols].head(10).to_string(index=False))

if __name__ == "__main__":
    run_fast_grid()
