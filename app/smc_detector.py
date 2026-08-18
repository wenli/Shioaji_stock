import logging
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

def detect_order_blocks(df: pd.DataFrame, timeframe: str = "5k", swing_window: int = 3) -> dict:
    """
    Detects the most recent active (unmitigated) Bullish and Bearish Order Blocks from K-line data.
    
    Returns:
        dict: {
            "bullish_ob": {"type": "BULLISH", "top": float, "bottom": float, "time": str} or None,
            "bearish_ob": {"type": "BEARISH", "top": float, "bottom": float, "time": str} or None,
        }
    """
    if df is None or len(df) < 10:
        return {"bullish_ob": None, "bearish_ob": None}

    df = df.copy().reset_index(drop=True)
    n = len(df)
    
    # 1. 識別 Swing Highs 與 Swing Lows
    swing_highs = [] # (index, high_price)
    swing_lows = []  # (index, low_price)
    
    w = swing_window
    for i in range(w, n - w):
        current_high = df.loc[i, 'high']
        current_low = df.loc[i, 'low']
        
        is_sh = True
        is_sl = True
        for offset in range(1, w + 1):
            if df.loc[i - offset, 'high'] >= current_high or df.loc[i + offset, 'high'] > current_high:
                is_sh = False
            if df.loc[i - offset, 'low'] <= current_low or df.loc[i + offset, 'low'] < current_low:
                is_sl = False
                
        if is_sh:
            swing_highs.append((i, current_high))
        if is_sl:
            swing_lows.append((i, current_low))

    bullish_obs = [] # list of dicts: {'top', 'bottom', 'time', 'bar_idx'}
    bearish_obs = [] # list of dicts: {'top', 'bottom', 'time', 'bar_idx'}

    # 2. 檢測結構突破 (BOS) 與其前置反向 K 線 (Order Block)
    # 2a. Bullish BOS: 當突破之前的 Swing High，尋找突破起點前的最後一根下跌陰線 (close < open)
    for sh_idx, sh_price in swing_highs:
        # 尋找在 sh_idx 之後第一次突破 sh_price 的點
        for i in range(sh_idx + 1, n):
            if df.loc[i, 'close'] > sh_price:
                # 發生 BOS，回溯尋找在 sh_idx 到 i 之間（或 i 之前 5 根）最低點附近的最後一根陰線
                search_start = max(0, sh_idx)
                sub_df = df.iloc[search_start:i]
                down_candles = sub_df[sub_df['close'] < sub_df['open']]
                if not down_candles.empty:
                    # 選取該波段最低的那根陰線
                    ob_candle = down_candles.loc[down_candles['low'].idxmin()]
                    ob_idx = ob_candle.name
                    bullish_obs.append({
                        'type': 'BULLISH',
                        'top': float(ob_candle['high']),
                        'bottom': float(ob_candle['low']),
                        'time': str(ob_candle['ts']),
                        'bar_idx': int(ob_idx)
                    })
                break

    # 2b. Bearish BOS: 當跌破之前的 Swing Low，尋找起跌前的最後一根上漲陽線 (close > open)
    for sl_idx, sl_price in swing_lows:
        for i in range(sl_idx + 1, n):
            if df.loc[i, 'close'] < sl_price:
                search_start = max(0, sl_idx)
                sub_df = df.iloc[search_start:i]
                up_candles = sub_df[sub_df['close'] > sub_df['open']]
                if not up_candles.empty:
                    # 選取該波段最高的那根陽線
                    ob_candle = up_candles.loc[up_candles['high'].idxmax()]
                    ob_idx = ob_candle.name
                    bearish_obs.append({
                        'type': 'BEARISH',
                        'top': float(ob_candle['high']),
                        'bottom': float(ob_candle['low']),
                        'time': str(ob_candle['ts']),
                        'bar_idx': int(ob_idx)
                    })
                break

    # 2c. 若 Swing Window 較大導致歷史 OB 較少，使用動能突破補充 (Momentum Displacement)
    if len(bullish_obs) == 0 or len(bearish_obs) == 0:
        for i in range(3, n):
            # Bullish displacement: 連續 2 根強陽線且漲幅大於前幾根平均波動
            if df.loc[i, 'close'] > df.loc[i, 'open'] and df.loc[i-1, 'close'] > df.loc[i-1, 'open']:
                if df.loc[i-2, 'close'] < df.loc[i-2, 'open']:
                    ob_candle = df.loc[i-2]
                    bullish_obs.append({
                        'type': 'BULLISH',
                        'top': float(ob_candle['high']),
                        'bottom': float(ob_candle['low']),
                        'time': str(ob_candle['ts']),
                        'bar_idx': int(i - 2)
                    })
            # Bearish displacement: 連續 2 根強陰線
            if df.loc[i, 'close'] < df.loc[i, 'open'] and df.loc[i-1, 'close'] < df.loc[i-1, 'open']:
                if df.loc[i-2, 'close'] > df.loc[i-2, 'open']:
                    ob_candle = df.loc[i-2]
                    bearish_obs.append({
                        'type': 'BEARISH',
                        'top': float(ob_candle['high']),
                        'bottom': float(ob_candle['low']),
                        'time': str(ob_candle['ts']),
                        'bar_idx': int(i - 2)
                    })

    # 3. 緩解檢查 (Mitigation / Invalidation Check)
    # 看多 OB：若後續價格跌破 bottom，則視為失效 (mitigated/broken)
    valid_bullish = None
    for ob in reversed(bullish_obs):
        ob_bar_idx = ob['bar_idx']
        bottom = ob['bottom']
        # 檢查從 ob_bar_idx + 1 到現在是否被跌破
        future_prices = df.iloc[ob_bar_idx + 1:]
        if not future_prices.empty:
            min_future_low = future_prices['low'].min()
            # 若最低價完全跌破底部，則無效
            if min_future_low < bottom:
                continue
        valid_bullish = {
            'type': 'BULLISH',
            'top': ob['top'],
            'bottom': ob['bottom'],
            'time': ob['time']
        }
        break

    # 看空 OB：若後續價格升破 top，則視為失效 (mitigated/broken)
    valid_bearish = None
    for ob in reversed(bearish_obs):
        ob_bar_idx = ob['bar_idx']
        top = ob['top']
        future_prices = df.iloc[ob_bar_idx + 1:]
        if not future_prices.empty:
            max_future_high = future_prices['high'].max()
            if max_future_high > top:
                continue
        valid_bearish = {
            'type': 'BEARISH',
            'top': ob['top'],
            'bottom': ob['bottom'],
            'time': ob['time']
        }
        break

    return {
        "bullish_ob": valid_bullish,
        "bearish_ob": valid_bearish
    }


def compute_and_save_obs_for_stock(conn: sqlite3.Connection, code: str) -> dict:
    """
    Computes active OBs across 5k, 15k, 60k, 1d for a stock and updates `stock_order_blocks`.
    """
    timeframes = ["5k", "15k", "60k", "1d"]
    results = {}

    cursor = conn.cursor()
    # 確保資料表存在
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_order_blocks (
            code TEXT,
            timeframe TEXT,
            ob_type TEXT,
            top_price REAL,
            bottom_price REAL,
            ob_time TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (code, timeframe, ob_type)
        )
    """)

    for tf in timeframes:
        table_name = f"stock{tf}"
        try:
            # 讀取最近 200 根 K 線
            query = f"""
                SELECT ts, open, high, low, close, volume
                FROM (
                    SELECT ts, open, high, low, close, volume
                    FROM {table_name}
                    WHERE code = ?
                    ORDER BY ts DESC
                    LIMIT 200
                )
                ORDER BY ts ASC
            """
            rows = conn.execute(query, (code,)).fetchall()
            if not rows:
                continue

            df = pd.DataFrame([dict(r) for r in rows])
            obs = detect_order_blocks(df, timeframe=tf)
            results[tf] = obs

            # 寫入或更新資料庫
            for ob_key in ["bullish_ob", "bearish_ob"]:
                ob_data = obs.get(ob_key)
                if ob_data:
                    cursor.execute("""
                        INSERT OR REPLACE INTO stock_order_blocks 
                        (code, timeframe, ob_type, top_price, bottom_price, ob_time, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        code,
                        tf,
                        ob_data['type'],
                        ob_data['top'],
                        ob_data['bottom'],
                        ob_data['time']
                    ))
                else:
                    # 如果該週期已無有效 OB，刪除舊的失效紀錄
                    target_type = "BULLISH" if ob_key == "bullish_ob" else "BEARISH"
                    cursor.execute("""
                        DELETE FROM stock_order_blocks 
                        WHERE code = ? AND timeframe = ? AND ob_type = ?
                    """, (code, tf, target_type))

        except Exception as e:
            logger.error(f"Error calculating OB for stock {code} ({tf}): {e}")

    conn.commit()
    return results


def get_stock_obs_from_db(conn: sqlite3.Connection, code: str) -> dict:
    """
    Retrieves cached OBs for a given stock code from `stock_order_blocks`.
    """
    try:
        rows = conn.execute("""
            SELECT timeframe, ob_type, top_price, bottom_price, ob_time
            FROM stock_order_blocks
            WHERE code = ?
        """, (code,)).fetchall()

        obs_by_tf = {"5k": {}, "15k": {}, "60k": {}, "1d": {}}
        for r in rows:
            tf = r['timeframe']
            ob_type = r['ob_type'].lower()
            if tf in obs_by_tf:
                obs_by_tf[tf][ob_type] = {
                    "type": r['ob_type'],
                    "top": r['top_price'],
                    "bottom": r['bottom_price'],
                    "time": r['ob_time']
                }
        return obs_by_tf
    except Exception as e:
        logger.error(f"Error fetching OBs from DB for {code}: {e}")
        return {"5k": {}, "15k": {}, "60k": {}, "1d": {}}


def calculate_trade_setup(ob_type: str, top: float, bottom: float) -> dict | None:
    """
    Calculates Entry, Stop Loss (SL), Take Profit 1 (TP1 1:2 R:R), and Take Profit 2 (TP2 1:3 R:R)
    based on an active Order Block's boundaries.
    """
    if not top or not bottom or top <= 0 or bottom <= 0:
        return None
    try:
        top = float(top)
        bottom = float(bottom)
    except (ValueError, TypeError):
        return None

    if top < bottom:
        top, bottom = bottom, top

    mid = round((top + bottom) / 2.0, 2)
    spread = top - bottom
    
    ob_upper = ob_type.upper()
    if ob_upper == "BULLISH":
        # Protective buffer below OB bottom (at least 0.5% or 0.1)
        buffer = max(spread * 0.2, mid * 0.005, 0.1)
        sl = round(bottom - buffer, 2)
        risk = round(mid - sl, 2)
        if risk <= 0:
            risk = round(max(mid * 0.01, 0.1), 2)
            sl = round(mid - risk, 2)
        
        tp1 = round(mid + (2.0 * risk), 2)
        tp2 = round(mid + (3.0 * risk), 2)
        risk_pct = round((risk / mid) * 100.0, 2) if mid > 0 else 0
        tp1_gain_pct = round(((tp1 - mid) / mid) * 100.0, 2) if mid > 0 else 0
        tp2_gain_pct = round(((tp2 - mid) / mid) * 100.0, 2) if mid > 0 else 0
        
        return {
            "direction": "LONG",
            "entry_range": [bottom, top],
            "entry_mid": mid,
            "stop_loss": sl,
            "risk": risk,
            "risk_pct": risk_pct,
            "tp1": tp1,
            "tp1_gain_pct": tp1_gain_pct,
            "tp2": tp2,
            "tp2_gain_pct": tp2_gain_pct,
            "rr_label": "1:2 / 1:3"
        }
    elif ob_upper == "BEARISH":
        # Protective buffer above OB top (at least 0.5% or 0.1)
        buffer = max(spread * 0.2, mid * 0.005, 0.1)
        sl = round(top + buffer, 2)
        risk = round(sl - mid, 2)
        if risk <= 0:
            risk = round(max(mid * 0.01, 0.1), 2)
            sl = round(mid + risk, 2)
        
        tp1 = round(max(0.1, mid - (2.0 * risk)), 2)
        tp2 = round(max(0.1, mid - (3.0 * risk)), 2)
        risk_pct = round((risk / mid) * 100.0, 2) if mid > 0 else 0
        tp1_gain_pct = round(((mid - tp1) / mid) * 100.0, 2) if mid > 0 else 0
        tp2_gain_pct = round(((mid - tp2) / mid) * 100.0, 2) if mid > 0 else 0
        
        return {
            "direction": "SHORT",
            "entry_range": [bottom, top],
            "entry_mid": mid,
            "stop_loss": sl,
            "risk": risk,
            "risk_pct": risk_pct,
            "tp1": tp1,
            "tp1_gain_pct": tp1_gain_pct,
            "tp2": tp2,
            "tp2_gain_pct": tp2_gain_pct,
            "rr_label": "1:2 / 1:3"
        }
    return None

