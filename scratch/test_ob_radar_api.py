import sys
import io
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Set utf-8 output encoding for windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.main import get_ob_radar, get_wishlist
import json

def test_api():
    print("Testing get_ob_radar()...")
    res = get_ob_radar()
    print("OB Radar Stats:")
    print(f"  Total Touching: {res['count']}")
    print(f"  Momentum Touching: {res['momentum_count']}")
    print(f"  High Winrate (S/A Grade) Touching: {res['high_winrate_count']}")
    print(f"  Total Monitored: {res['all_monitored_count']}")
    
    # Filter only S/A grade stocks
    high_wr_stocks = [s for s in res['stocks'] if s.get('high_winrate_setup', {}).get('grade') in ['S+', 'A']]
    print(f"\nFound {len(high_wr_stocks)} High Win-Rate (S/A Grade) Stocks:")
    for s in high_wr_stocks[:5]:
        hwr = s['high_winrate_setup']
        tp = hwr.get('trade_plan')
        print(f"\n  [{s['code']} {s['name']}] Price: {s['live_price']} | Grade: {hwr.get('grade')} ({hwr.get('grade_badge')})")
        print(f"    60K Bullish: {hwr.get('is_htf_bullish')} (EMA20: {hwr.get('ema20_60k')})")
        print(f"    DR Status: {hwr.get('dr_status')} (Mid: {hwr.get('dr_mid')})")
        print(f"    5K PA Pattern: {hwr.get('pa_pattern')}")
        if tp:
            print(f"    SL: {tp['stop_loss']} (-{tp['risk_pct']}%)")
            print(f"    TP1 (1:1.5 RR, 62.8% WR): {tp['tp_1_5']} (+{tp['tp_1_5_gain_pct']}%)")
            print(f"    TP2 (1:2.0 RR, 57.1% WR): {tp['tp_2_0']} (+{tp['tp_2_0_gain_pct']}%)")

if __name__ == "__main__":
    test_api()
