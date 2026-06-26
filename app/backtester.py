import sqlite3
import pandas as pd
import numpy as np
import logging
from pathlib import Path
from download_stock_data import get_db_connection

logger = logging.getLogger(__name__)

def calculate_atr(df_ltf, period=14):
    """Calculates Simple ATR for LTF dataframe."""
    high_low = df_ltf['high'] - df_ltf['low']
    high_close = np.abs(df_ltf['high'] - df_ltf['close'].shift())
    low_close = np.abs(df_ltf['low'] - df_ltf['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(window=period).mean()
    return atr.fillna(0.0)

def run_backtest(
    code: str,
    start_date: str,
    end_date: str,
    initial_balance: float = 1000000.0,
    risk_pct: float = 0.01,
    rr_ratio: float = 2.0,
    htf_window: int = 20,
    entry_mode: str = "fvg_top",
    sl_buffer_pct: float = 0.2,
    fee_discount: float = 0.6,
    enable_short: bool = False,
    holding_mode: str = "day_trade",
    ltf_timeframe: str = "5k",
    strategy_name: str = "smc"
) -> dict:
    """
    Runs trading strategy backtest on the SQLite data.
    Supports strategies: 'smc', 'ema_cross', 'bollinger_bands', 'kd_indicator'.
    """
    conn = get_db_connection()
    
    # 1. 載入日K資料 (HTF)
    query_1d = """
        SELECT ts, open, high, low, close, volume 
        FROM stock1d 
        WHERE code = ? AND date(ts) BETWEEN date(?) AND date(?)
        ORDER BY ts ASC
    """
    df_1d = pd.read_sql_query(query_1d, conn, params=[code, start_date, end_date])
    
    # 2. 載入分K資料 (LTF)，往前多抓幾天用來計算指標
    query_ltf = f"""
        SELECT ts, open, high, low, close, volume 
        FROM stock{ltf_timeframe} 
        WHERE code = ? AND date(ts) BETWEEN date(?, '-10 day') AND date(?)
        ORDER BY ts ASC
    """
    df_ltf = pd.read_sql_query(query_ltf, conn, params=[code, start_date, end_date])
    conn.close()

    if df_1d.empty or df_ltf.empty:
        logger.warning(f"No backtest data for stock {code} in database.")
        return {
            "success": False,
            "error": f"資料庫中沒有此日期區間的歷史 K 線數據（週期: {ltf_timeframe}），請先同步資料。"
        }

    # 3. 計算 HTF 日線結構 (BOS, Equilibrium, Bias)
    df_1d['range_high'] = df_1d['high'].shift(1).rolling(window=htf_window).max()
    df_1d['range_low'] = df_1d['low'].shift(1).rolling(window=htf_window).min()
    df_1d['equilibrium'] = (df_1d['range_high'] + df_1d['range_low']) / 2
    
    bias_series = []
    current_bias = "BULLISH"
    for idx, row in df_1d.iterrows():
        close = row['close']
        r_high = row['range_high']
        r_low = row['range_low']
        
        if not np.isnan(r_high) and not np.isnan(r_low):
            if close > r_high:
                current_bias = "BULLISH"
            elif close < r_low:
                current_bias = "BEARISH"
        bias_series.append(current_bias)
        
    df_1d['bias'] = bias_series
    
    # 建立日期對照 Dict (YYYY-MM-DD -> HTF 狀態)
    df_1d['date_str'] = pd.to_datetime(df_1d['ts']).dt.strftime('%Y-%m-%d')
    htf_status = {}
    for _, row in df_1d.iterrows():
        htf_status[row['date_str']] = {
            "bias": row['bias'],
            "equilibrium": row['equilibrium'],
            "range_high": row['range_high'],
            "range_low": row['range_low']
        }

    # 4. 計算 LTF 輔助指標 (ATR, 昨日最低點 PDL/昨日最高點 PDH)
    df_ltf['ts_datetime'] = pd.to_datetime(df_ltf['ts'])
    df_ltf['date_str'] = df_ltf['ts_datetime'].dt.strftime('%Y-%m-%d')
    df_ltf['atr'] = calculate_atr(df_ltf, period=14)
    
    # A. 基礎昨日極值計算
    daily_lows = df_ltf.groupby('date_str')['low'].min().to_dict()
    daily_highs = df_ltf.groupby('date_str')['high'].max().to_dict()
    
    sorted_dates = sorted(daily_lows.keys())
    pdl_map = {}
    pdh_map = {}
    for i in range(1, len(sorted_dates)):
        pdl_map[sorted_dates[i]] = daily_lows[sorted_dates[i-1]]
        pdh_map[sorted_dates[i]] = daily_highs[sorted_dates[i-1]]

    # B. 計算其他交易策略之指標
    s_name = strategy_name.lower().strip()
    if s_name == "ema_cross":
        # 快均線天期為 htf_window / 4, 慢均線天期為 htf_window
        fast_span = max(5, int(htf_window / 4))
        df_ltf['ema_fast'] = df_ltf['close'].ewm(span=fast_span, adjust=False).mean()
        df_ltf['ema_slow'] = df_ltf['close'].ewm(span=int(htf_window), adjust=False).mean()
        
    elif s_name == "bollinger_bands":
        # 布林通道 (天期 htf_window, 2倍標準差)
        df_ltf['bb_mid'] = df_ltf['close'].rolling(window=int(htf_window)).mean()
        df_ltf['bb_std'] = df_ltf['close'].rolling(window=int(htf_window)).std()
        df_ltf['bb_upper'] = df_ltf['bb_mid'] + 2.0 * df_ltf['bb_std']
        df_ltf['bb_lower'] = df_ltf['bb_mid'] - 2.0 * df_ltf['bb_std']
        
    elif s_name == "kd_indicator":
        # KD 指標 (9, 3, 3)
        ndays = 9
        low_min = df_ltf['low'].rolling(window=ndays).min()
        high_max = df_ltf['high'].rolling(window=ndays).max()
        rsv = ((df_ltf['close'] - low_min) / (high_max - low_min) * 100).fillna(50.0)
        
        k_list = []
        d_list = []
        curr_k = 50.0
        curr_d = 50.0
        for rsv_val in rsv:
            curr_k = (2/3) * curr_k + (1/3) * rsv_val
            curr_d = (2/3) * curr_d + (1/3) * curr_k
            k_list.append(curr_k)
            d_list.append(curr_d)
            
        df_ltf['k'] = k_list
        df_ltf['d'] = d_list

    # 5. 過濾出符合回測範圍內的 LTF，開始遍歷
    df_backtest_ltf = df_ltf[df_ltf['date_str'] >= pd.to_datetime(start_date).strftime('%Y-%m-%d')].copy().reset_index(drop=True)

    # 虛擬帳戶變數
    balance = initial_balance
    in_position = False
    position_type = None # "LONG" or "SHORT"
    shares = 0
    entry_price = 0.0
    entry_time = None
    sl_price = 0.0
    tp_price = 0.0
    
    # 掛單/訊號狀態
    pending_order = None 
    
    # SMC 訊號暫存
    sweep_type = None
    sweep_low = 0.0
    sweep_high = 0.0
    sweep_idx = None
    choch_detected = False
    
    trades_log = []
    equity_curve = []
    last_logged_date = None

    # 遍歷 LTF K棒
    for idx in range(10, len(df_backtest_ltf)):
        row = df_backtest_ltf.iloc[idx]
        current_time = row['ts']
        current_date_str = row['date_str']
        close_ltf = row['close']
        high_ltf = row['high']
        low_ltf = row['low']
        atr_ltf = row['atr']
        
        # 記錄每日淨值
        if last_logged_date != current_date_str:
            current_equity = balance
            if in_position:
                if position_type == "LONG":
                    current_equity += close_ltf * shares
                else: # SHORT
                    current_equity += (entry_price - close_ltf) * shares
            equity_curve.append({
                "time": current_date_str,
                "value": round(float(current_equity), 2)
            })
            last_logged_date = current_date_str

        day_htf = htf_status.get(current_date_str)
        pdl = pdl_map.get(current_date_str, 0.0)
        pdh = pdh_map.get(current_date_str, 0.0)

        # 6. 持倉管理
        if in_position:
            # A. 做多持倉管理
            if position_type == "LONG":
                if low_ltf <= sl_price:
                    exit_price = sl_price
                    fee_tax = exit_price * shares * (0.001425 * fee_discount + 0.003)
                    pnl = (exit_price - entry_price) * shares - fee_tax - (entry_price * shares * 0.001425 * fee_discount)
                    balance = balance + (exit_price * shares) - fee_tax
                    
                    trades_log.append({
                        "trade_no": len(trades_log) + 1,
                        "direction": "LONG",
                        "entry_time": entry_time,
                        "entry_price": round(float(entry_price), 2),
                        "exit_time": current_time,
                        "exit_price": round(float(exit_price), 2),
                        "shares": int(shares),
                        "type": "SL",
                        "pnl": round(float(pnl), 2),
                        "pnl_pct": round(float((pnl / (entry_price * shares)) * 100), 2),
                        "fee_tax": round(float(fee_tax), 2)
                    })
                    in_position = False
                    position_type = None
                    shares = 0
                    logger.info(f"[{current_time}] Long SL hit at {exit_price}")
                    
                elif high_ltf >= tp_price:
                    exit_price = tp_price
                    fee_tax = exit_price * shares * (0.001425 * fee_discount + 0.003)
                    pnl = (exit_price - entry_price) * shares - fee_tax - (entry_price * shares * 0.001425 * fee_discount)
                    balance = balance + (exit_price * shares) - fee_tax
                    
                    trades_log.append({
                        "trade_no": len(trades_log) + 1,
                        "direction": "LONG",
                        "entry_time": entry_time,
                        "entry_price": round(float(entry_price), 2),
                        "exit_time": current_time,
                        "exit_price": round(float(exit_price), 2),
                        "shares": int(shares),
                        "type": "TP",
                        "pnl": round(float(pnl), 2),
                        "pnl_pct": round(float((pnl / (entry_price * shares)) * 100), 2),
                        "fee_tax": round(float(fee_tax), 2)
                    })
                    in_position = False
                    position_type = None
                    shares = 0
                    logger.info(f"[{current_time}] Long TP hit at {exit_price}")
                    
                elif (holding_mode == "day_trade" and current_time.endswith("13:30:00")) or idx == len(df_backtest_ltf) - 1:
                    exit_price = close_ltf
                    fee_tax = exit_price * shares * (0.001425 * fee_discount + 0.003)
                    pnl = (exit_price - entry_price) * shares - fee_tax - (entry_price * shares * 0.001425 * fee_discount)
                    balance = balance + (exit_price * shares) - fee_tax
                    
                    trades_log.append({
                        "trade_no": len(trades_log) + 1,
                        "direction": "LONG",
                        "entry_time": entry_time,
                        "entry_price": round(float(entry_price), 2),
                        "exit_time": current_time,
                        "exit_price": round(float(exit_price), 2),
                        "shares": int(shares),
                        "type": "EOD" if idx != len(df_backtest_ltf) - 1 else "EOF",
                        "pnl": round(float(pnl), 2),
                        "pnl_pct": round(float((pnl / (entry_price * shares)) * 100), 2),
                        "fee_tax": round(float(fee_tax), 2)
                    })
                    in_position = False
                    position_type = None
                    shares = 0
                    logger.info(f"[{current_time}] Long EOD/EOF exit at {exit_price}")
            
            # B. 做空持倉管理
            elif position_type == "SHORT":
                if high_ltf >= sl_price:
                    exit_price = sl_price
                    tax = entry_price * shares * 0.003
                    buy_fee = exit_price * shares * 0.001425 * fee_discount
                    flat_costs = buy_fee + tax
                    pnl = (entry_price - exit_price) * shares - flat_costs
                    balance = balance - (exit_price * shares) - flat_costs
                    
                    trades_log.append({
                        "trade_no": len(trades_log) + 1,
                        "direction": "SHORT",
                        "entry_time": entry_time,
                        "entry_price": round(float(entry_price), 2),
                        "exit_time": current_time,
                        "exit_price": round(float(exit_price), 2),
                        "shares": int(shares),
                        "type": "SL",
                        "pnl": round(float(pnl), 2),
                        "pnl_pct": round(float((pnl / (entry_price * shares)) * 100), 2),
                        "fee_tax": round(float(flat_costs), 2)
                    })
                    in_position = False
                    position_type = None
                    shares = 0
                    logger.info(f"[{current_time}] Short SL hit at {exit_price}")
                    
                elif low_ltf <= tp_price:
                    exit_price = tp_price
                    tax = entry_price * shares * 0.003
                    buy_fee = exit_price * shares * 0.001425 * fee_discount
                    flat_costs = buy_fee + tax
                    pnl = (entry_price - exit_price) * shares - flat_costs
                    balance = balance - (exit_price * shares) - flat_costs
                    
                    trades_log.append({
                        "trade_no": len(trades_log) + 1,
                        "direction": "SHORT",
                        "entry_time": entry_time,
                        "entry_price": round(float(entry_price), 2),
                        "exit_time": current_time,
                        "exit_price": round(float(exit_price), 2),
                        "shares": int(shares),
                        "type": "TP",
                        "pnl": round(float(pnl), 2),
                        "pnl_pct": round(float((pnl / (entry_price * shares)) * 100), 2),
                        "fee_tax": round(float(flat_costs), 2)
                    })
                    in_position = False
                    position_type = None
                    shares = 0
                    logger.info(f"[{current_time}] Short TP hit at {exit_price}")
                    
                elif (holding_mode == "day_trade" and current_time.endswith("13:30:00")) or idx == len(df_backtest_ltf) - 1:
                    exit_price = close_ltf
                    tax = entry_price * shares * 0.003
                    buy_fee = exit_price * shares * 0.001425 * fee_discount
                    flat_costs = buy_fee + tax
                    pnl = (entry_price - exit_price) * shares - flat_costs
                    balance = balance - (exit_price * shares) - flat_costs
                    
                    trades_log.append({
                        "trade_no": len(trades_log) + 1,
                        "direction": "SHORT",
                        "entry_time": entry_time,
                        "entry_price": round(float(entry_price), 2),
                        "exit_time": current_time,
                        "exit_price": round(float(exit_price), 2),
                        "shares": int(shares),
                        "type": "EOD" if idx != len(df_backtest_ltf) - 1 else "EOF",
                        "pnl": round(float(pnl), 2),
                        "pnl_pct": round(float((pnl / (entry_price * shares)) * 100), 2),
                        "fee_tax": round(float(flat_costs), 2)
                    })
                    in_position = False
                    position_type = None
                    shares = 0
                    logger.info(f"[{current_time}] Short EOD/EOF exit at {exit_price}")
            
            continue

        # 7. 掛單撮合與限價單進場 (主要用於 SMC 策略之限價單)
        if pending_order is not None:
            if pending_order["date"] != current_date_str:
                pending_order = None 
            else:
                if pending_order["type"] == "LONG":
                    if low_ltf <= pending_order["entry"]:
                        p_entry = pending_order["entry"]
                        p_sl = pending_order["sl"]
                        p_tp = pending_order["tp"]
                        
                        risk_amount = balance * risk_pct
                        price_diff = p_entry - p_sl
                        if price_diff > 0:
                            shares = int(min(risk_amount / price_diff, balance / p_entry))
                            if shares > 0:
                                balance = balance - (p_entry * shares) - (p_entry * shares * 0.001425 * fee_discount)
                                in_position, position_type, entry_price, entry_time, sl_price, tp_price = True, "LONG", p_entry, current_time, p_sl, p_tp
                                pending_order = None
                                logger.info(f"[{current_time}] Long Filled (SMC) at {entry_price}")
                                continue
                                
                elif pending_order["type"] == "SHORT":
                    if high_ltf >= pending_order["entry"]:
                        p_entry = pending_order["entry"]
                        p_sl = pending_order["sl"]
                        p_tp = pending_order["tp"]
                        
                        risk_amount = balance * risk_pct
                        price_diff = p_sl - p_entry
                        if price_diff > 0:
                            shares = int(min(risk_amount / price_diff, balance / p_entry))
                            if shares > 0:
                                balance = balance + (p_entry * shares) - (p_entry * shares * 0.001425 * fee_discount)
                                in_position, position_type, entry_price, entry_time, sl_price, tp_price = True, "SHORT", p_entry, current_time, p_sl, p_tp
                                pending_order = None
                                logger.info(f"[{current_time}] Short Filled (SMC) at {entry_price}")
                                continue

        # 8. 訊號生成與直接交易 (無持倉與掛單時)
        if not in_position and pending_order is None:
            
            # --- 策略 A: SMC 策略 ---
            if s_name == "smc":
                # 判定做多或做空
                can_trade_long = (day_htf is not None and day_htf['bias'] == "BULLISH" and day_htf['equilibrium'] is not None and close_ltf < day_htf['equilibrium'])
                can_trade_short = (day_htf is not None and day_htf['bias'] == "BEARISH" and enable_short and day_htf['equilibrium'] is not None and close_ltf > day_htf['equilibrium'])
                
                if can_trade_long:
                    prev_10_lows = df_backtest_ltf.iloc[idx-10:idx]['low'].min()
                    ref_low = min(pdl, prev_10_lows) if pdl > 0 else prev_10_lows
                    if low_ltf < ref_low and close_ltf > ref_low:
                        sweep_type, sweep_low, sweep_idx, choch_detected = "bullish", low_ltf, idx, False
                        
                    if sweep_type == "bullish" and not choch_detected:
                        if close_ltf > df_backtest_ltf.iloc[idx-5:idx]['high'].max():
                            choch_detected = True
                            
                    if choch_detected and sweep_type == "bullish":
                        if entry_mode in ["fvg_top", "fvg_mid"]:
                            k3_low, k1_high = low_ltf, df_backtest_ltf.iloc[idx-2]['high']
                            if k3_low > k1_high:
                                p_entry = k1_high if entry_mode == "fvg_top" else (k1_high + k3_low) / 2
                                p_sl = max(sweep_low - (sl_buffer_pct * atr_ltf), 0.1)
                                if p_sl >= p_entry: p_sl = p_entry - 0.5
                                p_tp = p_entry + (p_entry - p_sl) * rr_ratio
                                
                                pending_order = {"type": "LONG", "entry": p_entry, "sl": p_sl, "tp": p_tp, "date": current_date_str}
                                sweep_type, sweep_idx, choch_detected = None, None, False
                                logger.info(f"[{current_time}] SMC Long order placed (FVG).")
                                
                        elif entry_mode == "ob_open":
                            search_df = df_backtest_ltf.iloc[sweep_idx:idx+1]
                            bearish_candles = search_df[search_df['close'] < search_df['open']]
                            if not bearish_candles.empty:
                                ob_candle = bearish_candles.loc[bearish_candles['low'].idxmin()]
                                p_entry = ob_candle['open']
                            else:
                                ob_candle = search_df.loc[search_df['low'].idxmin()]
                                p_entry = ob_candle['low']
                                
                            p_sl = max(sweep_low - (sl_buffer_pct * atr_ltf), 0.1)
                            if p_sl >= p_entry: p_sl = p_entry - 0.5
                            p_tp = p_entry + (p_entry - p_sl) * rr_ratio
                            
                            pending_order = {"type": "LONG", "entry": p_entry, "sl": p_sl, "tp": p_tp, "date": current_date_str}
                            sweep_type, sweep_idx, choch_detected = None, None, False
                            logger.info(f"[{current_time}] SMC Long order placed (OB). Entry: {p_entry}")
                            
                        elif entry_mode.startswith("ote_"):
                            ratio = 0.705
                            try:
                                parts = entry_mode.split("_")
                                if len(parts) > 1:
                                    val_str = parts[1]
                                    if len(val_str) == 3:
                                        ratio = float(val_str) / 1000.0
                                    elif len(val_str) == 2:
                                        ratio = float(val_str) / 100.0
                            except Exception:
                                ratio = 0.705
                                
                            search_df = df_backtest_ltf.iloc[sweep_idx:idx+1]
                            choch_high = search_df['high'].max()
                            p_entry = choch_high - (choch_high - sweep_low) * ratio
                            p_sl = max(sweep_low - (sl_buffer_pct * atr_ltf), 0.1)
                            if p_sl >= p_entry: p_sl = p_entry - 0.5
                            p_tp = p_entry + (p_entry - p_sl) * rr_ratio
                            
                            pending_order = {"type": "LONG", "entry": p_entry, "sl": p_sl, "tp": p_tp, "date": current_date_str}
                            sweep_type, sweep_idx, choch_detected = None, None, False
                            logger.info(f"[{current_time}] SMC Long order placed (OTE {ratio}). Entry: {p_entry}")
                            
                elif can_trade_short:
                    prev_10_highs = df_backtest_ltf.iloc[idx-10:idx]['high'].max()
                    ref_high = max(pdh, prev_10_highs) if pdh > 0 else prev_10_highs
                    if high_ltf > ref_high and close_ltf < ref_high:
                        sweep_type, sweep_high, sweep_idx, choch_detected = "bearish", high_ltf, idx, False
                        
                    if sweep_type == "bearish" and not choch_detected:
                        if close_ltf < df_backtest_ltf.iloc[idx-5:idx]['low'].min():
                            choch_detected = True
                            
                    if choch_detected and sweep_type == "bearish":
                        if entry_mode in ["fvg_top", "fvg_mid"]:
                            k3_high, k1_low = high_ltf, df_backtest_ltf.iloc[idx-2]['low']
                            if k3_high < k1_low:
                                p_entry = k1_low if entry_mode == "fvg_top" else (k1_low + k3_high) / 2
                                p_sl = sweep_high + (sl_buffer_pct * atr_ltf)
                                if p_sl <= p_entry: p_sl = p_entry + 0.5
                                p_tp = p_entry - (p_sl - p_entry) * rr_ratio
                                
                                pending_order = {"type": "SHORT", "entry": p_entry, "sl": p_sl, "tp": p_tp, "date": current_date_str}
                                sweep_type, sweep_idx, choch_detected = None, None, False
                                logger.info(f"[{current_time}] SMC Short order placed (FVG).")
                                
                        elif entry_mode == "ob_open":
                            search_df = df_backtest_ltf.iloc[sweep_idx:idx+1]
                            bullish_candles = search_df[search_df['close'] > search_df['open']]
                            if not bullish_candles.empty:
                                ob_candle = bullish_candles.loc[bullish_candles['high'].idxmax()]
                                p_entry = ob_candle['open']
                            else:
                                ob_candle = search_df.loc[search_df['high'].idxmax()]
                                p_entry = ob_candle['high']
                                
                            p_sl = sweep_high + (sl_buffer_pct * atr_ltf)
                            if p_sl <= p_entry: p_sl = p_entry + 0.5
                            p_tp = p_entry - (p_sl - p_entry) * rr_ratio
                            
                            pending_order = {"type": "SHORT", "entry": p_entry, "sl": p_sl, "tp": p_tp, "date": current_date_str}
                            sweep_type, sweep_idx, choch_detected = None, None, False
                            logger.info(f"[{current_time}] SMC Short order placed (OB). Entry: {p_entry}")
                            
                        elif entry_mode.startswith("ote_"):
                            ratio = 0.705
                            try:
                                parts = entry_mode.split("_")
                                if len(parts) > 1:
                                    val_str = parts[1]
                                    if len(val_str) == 3:
                                        ratio = float(val_str) / 1000.0
                                    elif len(val_str) == 2:
                                        ratio = float(val_str) / 100.0
                            except Exception:
                                ratio = 0.705
                                
                            search_df = df_backtest_ltf.iloc[sweep_idx:idx+1]
                            choch_low = search_df['low'].min()
                            p_entry = choch_low + (sweep_high - choch_low) * ratio
                            p_sl = sweep_high + (sl_buffer_pct * atr_ltf)
                            if p_sl <= p_entry: p_sl = p_entry + 0.5
                            p_tp = p_entry - (p_sl - p_entry) * rr_ratio
                            
                            pending_order = {"type": "SHORT", "entry": p_entry, "sl": p_sl, "tp": p_tp, "date": current_date_str}
                            sweep_type, sweep_idx, choch_detected = None, None, False
                            logger.info(f"[{current_time}] SMC Short order placed (OTE {ratio}). Entry: {p_entry}")

            # --- 策略 B: EMA 雙均線交叉策略 ---
            elif s_name == "ema_cross":
                # 順勢指標：多頭 Bias 只做多，空頭 Bias 只做空
                bias = day_htf['bias'] if day_htf is not None else "BULLISH"
                
                # 金叉 (快線穿越慢線)
                gold_cross = (df_backtest_ltf.iloc[idx-1]['ema_fast'] <= df_backtest_ltf.iloc[idx-1]['ema_slow'] and 
                              row['ema_fast'] > row['ema_slow'])
                # 死叉 (快線跌破慢線)
                death_cross = (df_backtest_ltf.iloc[idx-1]['ema_fast'] >= df_backtest_ltf.iloc[idx-1]['ema_slow'] and 
                               row['ema_fast'] < row['ema_slow'])
                
                if gold_cross and bias == "BULLISH":
                    # 下一根 K 棒開盤買入做多
                    p_entry = close_ltf
                    p_sl = p_entry - (2.0 * atr_ltf)
                    p_tp = p_entry + (p_entry - p_sl) * rr_ratio
                    
                    risk_amount = balance * risk_pct
                    shares = int(min(risk_amount / (p_entry - p_sl), balance / p_entry))
                    if shares > 0:
                        balance = balance - (p_entry * shares) - (p_entry * shares * 0.001425 * fee_discount)
                        in_position, position_type, entry_price, entry_time, sl_price, tp_price = True, "LONG", p_entry, current_time, p_sl, p_tp
                        logger.info(f"[{current_time}] EMA Long Filled at {entry_price}")
                        
                elif death_cross and bias == "BEARISH" and enable_short:
                    # 下一根做空
                    p_entry = close_ltf
                    p_sl = p_entry + (2.0 * atr_ltf)
                    p_tp = p_entry - (p_sl - p_entry) * rr_ratio
                    
                    risk_amount = balance * risk_pct
                    shares = int(min(risk_amount / (p_sl - p_entry), balance / p_entry))
                    if shares > 0:
                        balance = balance + (p_entry * shares) - (p_entry * shares * 0.001425 * fee_discount)
                        in_position, position_type, entry_price, entry_time, sl_price, tp_price = True, "SHORT", p_entry, current_time, p_sl, p_tp
                        logger.info(f"[{current_time}] EMA Short Filled at {entry_price}")

            # --- 策略 C: 布林通道逆勢均值回歸 ---
            elif s_name == "bollinger_bands":
                # 收盤跌破下軌：超跌買入做多
                bb_long = close_ltf < row['bb_lower']
                # 收盤衝破上軌：超漲放空做空
                bb_short = close_ltf > row['bb_upper']
                
                if bb_long:
                    p_entry = close_ltf
                    p_sl = p_entry - (2.0 * atr_ltf)
                    p_tp = p_entry + (p_entry - p_sl) * rr_ratio
                    
                    shares = int(min((balance * risk_pct) / (p_entry - p_sl), balance / p_entry))
                    if shares > 0:
                        balance = balance - (p_entry * shares) - (p_entry * shares * 0.001425 * fee_discount)
                        in_position, position_type, entry_price, entry_time, sl_price, tp_price = True, "LONG", p_entry, current_time, p_sl, p_tp
                        logger.info(f"[{current_time}] BB Long Filled at {entry_price}")
                        
                elif bb_short and enable_short:
                    p_entry = close_ltf
                    p_sl = p_entry + (2.0 * atr_ltf)
                    p_tp = p_entry - (p_sl - p_entry) * rr_ratio
                    
                    shares = int(min((balance * risk_pct) / (p_sl - p_entry), balance / p_entry))
                    if shares > 0:
                        balance = balance + (p_entry * shares) - (p_entry * shares * 0.001425 * fee_discount)
                        in_position, position_type, entry_price, entry_time, sl_price, tp_price = True, "SHORT", p_entry, current_time, p_sl, p_tp
                        logger.info(f"[{current_time}] BB Short Filled at {entry_price}")

            # --- 策略 D: KD 指標超買超賣黃金死亡交叉 ---
            elif s_name == "kd_indicator":
                # RSV, K, D 計算在前面
                prev_row = df_backtest_ltf.iloc[idx-1]
                # KD低檔金叉 (K值 <= 20)
                kd_long = (prev_row['k'] <= prev_row['d'] and row['k'] > row['d'] and row['k'] <= 20)
                # KD高檔死叉 (K值 >= 80)
                kd_short = (prev_row['k'] >= prev_row['d'] and row['k'] < row['d'] and row['k'] >= 80)
                
                if kd_long:
                    p_entry = close_ltf
                    p_sl = p_entry - (2.0 * atr_ltf)
                    p_tp = p_entry + (p_entry - p_sl) * rr_ratio
                    
                    shares = int(min((balance * risk_pct) / (p_entry - p_sl), balance / p_entry))
                    if shares > 0:
                        balance = balance - (p_entry * shares) - (p_entry * shares * 0.001425 * fee_discount)
                        in_position, position_type, entry_price, entry_time, sl_price, tp_price = True, "LONG", p_entry, current_time, p_sl, p_tp
                        logger.info(f"[{current_time}] KD Long Filled at {entry_price}")
                        
                elif kd_short and enable_short:
                    p_entry = close_ltf
                    p_sl = p_entry + (2.0 * atr_ltf)
                    p_tp = p_entry - (p_sl - p_entry) * rr_ratio
                    
                    shares = int(min((balance * risk_pct) / (p_sl - p_entry), balance / p_entry))
                    if shares > 0:
                        balance = balance + (p_entry * shares) - (p_entry * shares * 0.001425 * fee_discount)
                        in_position, position_type, entry_price, entry_time, sl_price, tp_price = True, "SHORT", p_entry, current_time, p_sl, p_tp
                        logger.info(f"[{current_time}] KD Short Filled at {entry_price}")

    # 9. 統計回測成果
    total_trades = len(trades_log)
    if total_trades > 0:
        winning_trades = len([t for t in trades_log if t['pnl'] > 0])
        losing_trades = len([t for t in trades_log if t['pnl'] <= 0])
        win_rate = (winning_trades / total_trades) * 100
        
        gross_profit = sum([t['pnl'] for t in trades_log if t['pnl'] > 0])
        gross_loss = abs(sum([t['pnl'] for t in trades_log if t['pnl'] <= 0]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
        
        values = [e['value'] for e in equity_curve]
        if values:
            peak = values[0]
            max_dd = 0.0
            for v in values:
                if v > peak: peak = v
                dd = (peak - v) / peak * 100
                if dd > max_dd: max_dd = dd
        else:
            max_dd = 0.0
            
        if len(equity_curve) > 1:
            equity_df = pd.DataFrame(equity_curve)
            equity_df['daily_return'] = equity_df['value'].pct_change()
            daily_rf = 0.015 / 244
            mean_return = equity_df['daily_return'].mean()
            std_return = equity_df['daily_return'].std()
            if std_return > 0 and not np.isnan(std_return):
                sharpe_ratio = ((mean_return - daily_rf) / std_return) * np.sqrt(244)
            else:
                sharpe_ratio = 0.0
        else:
            sharpe_ratio = 0.0
    else:
        win_rate = 0.0
        winning_trades = 0
        losing_trades = 0
        profit_factor = 1.0
        max_dd = 0.0
        sharpe_ratio = 0.0

    final_balance = balance
    if in_position:
        last_close = df_backtest_ltf.iloc[-1]['close']
        if position_type == "LONG":
            final_balance += last_close * shares
        else: 
            tax = entry_price * shares * 0.003
            buy_fee = last_close * shares * 0.001425 * fee_discount
            flat_costs = buy_fee + tax
            final_balance += (entry_price - last_close) * shares - flat_costs - (entry_price * shares)

    total_return_pct = ((final_balance - initial_balance) / initial_balance) * 100

    return {
        "success": True,
        "summary": {
            "initial_balance": round(float(initial_balance), 2),
            "final_balance": round(float(final_balance), 2),
            "total_return_pct": round(float(total_return_pct), 2),
            "win_rate_pct": round(float(win_rate), 2),
            "total_trades": int(total_trades),
            "winning_trades": int(winning_trades),
            "losing_trades": int(losing_trades),
            "max_drawdown_pct": round(float(max_dd), 2),
            "profit_factor": round(float(profit_factor), 2),
            "sharpe_ratio": round(float(sharpe_ratio), 2)
        },
        "equity_curve": equity_curve,
        "trades": trades_log
    }
