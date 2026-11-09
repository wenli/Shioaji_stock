import sqlite3
import pandas as pd
import numpy as np

def test_stock_confluence(code="2317"):
    conn = sqlite3.connect(r"C:\Intel\Database\Shioaji.db")
    
    # 1. 60K Data
    rows_60k = conn.execute(
        "SELECT ts, open, high, low, close, volume FROM stock60k WHERE code = ? ORDER BY ts DESC LIMIT 100",
        (code,)
    ).fetchall()
    
    if not rows_60k:
        print(f"No 60k data for {code}")
        conn.close()
        return
        
    df_60k = pd.DataFrame(rows_60k, columns=["ts", "open", "high", "low", "close", "volume"]).iloc[::-1].reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df_60k[col] = pd.to_numeric(df_60k[col], errors="coerce")
        
    # 60K EMA20
    df_60k["ema20"] = df_60k["close"].ewm(span=20, adjust=False).mean()
    ema20_val = round(float(df_60k["ema20"].iloc[-1]), 2)
    latest_close = float(df_60k["close"].iloc[-1])
    is_htf_bullish = latest_close >= ema20_val
    
    # 60K Dealing Range
    n = len(df_60k)
    highs = df_60k["high"].values
    lows = df_60k["low"].values
    w = 2
    sh = np.nan
    sl = np.nan
    for i in range(w, n - w):
        if all(highs[i] > highs[i - k] for k in range(1, w + 1)) and all(highs[i] >= highs[i + k] for k in range(1, w + 1)):
            sh = highs[i]
        if all(lows[i] < lows[i - k] for k in range(1, w + 1)) and all(lows[i] <= lows[i + k] for k in range(1, w + 1)):
            sl = lows[i]
            
    dr_mid = round((sh + sl) / 2.0, 2) if (not np.isnan(sh) and not np.isnan(sl)) else None
    is_in_discount = (latest_close <= dr_mid) if dr_mid else False
    
    # 2. 5K PA
    rows_5k = conn.execute(
        "SELECT ts, open, high, low, close, volume FROM stock5k WHERE code = ? ORDER BY ts DESC LIMIT 20",
        (code,)
    ).fetchall()
    
    df_5k = pd.DataFrame(rows_5k, columns=["ts", "open", "high", "low", "close", "volume"]).iloc[::-1].reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df_5k[col] = pd.to_numeric(df_5k[col], errors="coerce")
        
    # Check PA on last 2 bars
    pa_pattern = "無"
    if len(df_5k) >= 3:
        for idx in [-1, -2]:
            cur = df_5k.iloc[idx]
            prev = df_5k.iloc[idx - 1]
            c, o, h, l = cur["close"], cur["open"], cur["high"], cur["low"]
            pc, po, ph, pl = prev["close"], prev["open"], prev["high"], prev["low"]
            rng = h - l
            prng = ph - pl
            if rng > 0 and prng > 0:
                is_prev_bear = pc < po and abs(pc - po) >= 0.4 * prng
                if is_prev_bear and c > o and c >= ph:
                    pa_pattern = "TBF 假跌破反轉"
                    break
                lower_wick = min(o, c) - l
                if lower_wick >= 0.55 * rng and c >= o:
                    pa_pattern = "Pinbar 拒絕長下影"
                    break
                if l < pl and c > pc and c > o:
                    pa_pattern = "破低看多反轉"
                    break

    # Calculate 5K ATR
    tr = np.maximum(df_5k["high"] - df_5k["low"], np.maximum(abs(df_5k["high"] - df_5k["close"].shift(1)), abs(df_5k["low"] - df_5k["close"].shift(1))))
    atr_5k = round(float(tr.tail(14).mean()), 2) if len(tr) > 0 else 1.0

    print(f"=== {code} Confluence Check ===")
    print(f"Latest Price: {latest_close}")
    print(f"60K EMA20: {ema20_val} (HTF Bullish: {is_htf_bullish})")
    print(f"60K Dealing Range: Low={sl}, High={sh}, Mid={dr_mid} (Discount: {is_in_discount})")
    print(f"5K PA Pattern: {pa_pattern}")
    print(f"5K ATR(14): {atr_5k}")
    
    conn.close()

if __name__ == "__main__":
    for c in ["2317", "0050", "2454", "2618", "2409"]:
        test_stock_confluence(c)
