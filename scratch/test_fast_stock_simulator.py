import time
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.fast_stock_simulator import load_stock_data, FastStockSimulator

def test_single_stock():
    print("=== Testing FastStockSimulator on 2317 (Hon Hai) ===")
    t0 = time.time()
    data = load_stock_data("2317")
    print(f"Data loaded: 5K={len(data['5K'])} bars, 60K={len(data['60K'])} bars in {time.time()-t0:.2f}s")
    
    t1 = time.time()
    sim = FastStockSimulator("2317", data["5K"], data["60K"])
    print(f"Simulator initialized and features pre-computed in {time.time()-t1:.2f}s")
    
    # Test different setups
    configs = [
        {"archetype": "dr_discount_pa", "pa_filter": "tbf_or_pin", "target_rr": 1.2, "holding_mode": "swing", "use_breakeven": False},
        {"archetype": "dr_discount_pa", "pa_filter": "tbf_only", "target_rr": 1.5, "holding_mode": "swing", "use_breakeven": True},
        {"archetype": "dr_discount_pa", "pa_filter": "pin_only", "target_rr": 1.0, "holding_mode": "day_trade", "use_breakeven": False},
        {"archetype": "dr_sweep_pa", "pa_filter": "tbf_or_pin", "target_rr": 1.5, "holding_mode": "swing", "use_breakeven": True},
        {"archetype": "unfiltered_pa", "pa_filter": "tbf_or_pin", "target_rr": 1.5, "holding_mode": "swing", "use_breakeven": False},
    ]
    
    print("\n--- Running simulations ---")
    for cfg in configs:
        ts_start = time.time()
        trades, stats = sim.run_strategy(cfg)
        elapsed = (time.time() - ts_start) * 1000
        print(f"[{cfg['archetype']:<16} | PA:{cfg['pa_filter']:<10} | RR:{cfg['target_rr']} | Hold:{cfg['holding_mode']:<9}] "
              f"Trades: {stats['trades']:2d} | WinRate: {stats['win_rate']:5.2f}% | PnL: {stats['net_pnl']:6.2f}% | "
              f"PF: {stats['profit_factor']:4.2f} | Time: {elapsed:5.1f}ms")

if __name__ == "__main__":
    test_single_stock()
