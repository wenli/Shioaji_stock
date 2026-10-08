"""
Fast Vectorized Simulator for Taiwan Stocks (SMC + Dealing Range + Galen Woods PA)
High-performance pre-computed backtest engine tailored for TWSE market microstructure.
Includes HTF Trend Filters (EMA 20/50), Dynamic Dealing Ranges, Order Blocks, and ATR volatility protection.
"""

import sqlite3
import os
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional


def load_stock_data(
    code: str,
    db_path: str = "C:/Intel/Database/Shioaji.db",
    start_date: str = "2025-07-01",
    end_date: str = "2026-09-30"
) -> Dict[str, pd.DataFrame]:
    """Loads 5K and 60K bars for a specific stock from SQLite."""
    conn = sqlite3.connect(db_path)
    
    q_5k = f"""
        SELECT ts, open, high, low, close, volume 
        FROM stock5k 
        WHERE code = ? AND ts >= ? AND ts <= ?
        ORDER BY ts ASC
    """
    df_5k = pd.read_sql_query(q_5k, conn, params=[code, f"{start_date} 09:00:00", f"{end_date} 13:30:00"])
    
    # HTF 60K: query with 60 days lookback
    q_60k = f"""
        SELECT ts, open, high, low, close, volume 
        FROM stock60k 
        WHERE code = ? AND ts >= date(?, '-60 day') AND ts <= ?
        ORDER BY ts ASC
    """
    df_60k = pd.read_sql_query(q_60k, conn, params=[code, start_date, f"{end_date} 13:30:00"])
    conn.close()

    for col in ["open", "high", "low", "close", "volume"]:
        df_5k[col] = pd.to_numeric(df_5k[col], errors="coerce")
        df_60k[col] = pd.to_numeric(df_60k[col], errors="coerce")

    df_5k["ts"] = pd.to_datetime(df_5k["ts"])
    df_60k["ts"] = pd.to_datetime(df_60k["ts"])

    return {"5K": df_5k, "60K": df_60k}


class FastStockSimulator:
    """
    Pre-computes structural SMC, Dealing Range, and Price Action features.
    Executes lightning-fast trade simulations across thousands of parameter sets.
    """

    def __init__(self, code: str, df_5k: pd.DataFrame, df_60k: pd.DataFrame, swing_window: int = 3):
        self.code = code
        self.df_5k = df_5k.copy().reset_index(drop=True)
        self.df_60k = df_60k.copy().reset_index(drop=True)
        self.swing_window = swing_window

        self._precompute_60k_structures()
        self._precompute_5k_pa_patterns()
        self._align_features()

    def _precompute_60k_structures(self):
        """Pre-computes Swings, Dealing Range, EMAs, and Order Blocks on 60K."""
        df = self.df_60k
        n = len(df)
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        opens = df["open"].values
        w = self.swing_window

        # 1. EMAs on 60K
        s_close = df["close"]
        df["ema_20"] = s_close.ewm(span=20, adjust=False).mean()
        df["ema_50"] = s_close.ewm(span=50, adjust=False).mean()

        # 2. Swings
        swing_highs = np.full(n, np.nan)
        swing_lows = np.full(n, np.nan)

        for i in range(w, n - w):
            if all(highs[i] > highs[i - k] for k in range(1, w + 1)) and all(highs[i] >= highs[i + k] for k in range(1, w + 1)):
                swing_highs[i] = highs[i]
            if all(lows[i] < lows[i - k] for k in range(1, w + 1)) and all(lows[i] <= lows[i + k] for k in range(1, w + 1)):
                swing_lows[i] = lows[i]

        # 3. Dynamic Dealing Range & Order Blocks
        dr_high = np.full(n, np.nan)
        dr_low = np.full(n, np.nan)
        dr_mid = np.full(n, np.nan)
        ob_bull_top = np.full(n, np.nan)
        ob_bull_bot = np.full(n, np.nan)

        last_sh = np.nan
        last_sl = np.nan
        active_ob_top = np.nan
        active_ob_bot = np.nan

        for i in range(n):
            # No-lookahead: Swing confirmed only after w bars have elapsed (candidate is at i - w)
            if i >= w:
                cand = i - w
                if not np.isnan(swing_highs[cand]):
                    last_sh = swing_highs[cand]
                if not np.isnan(swing_lows[cand]):
                    last_sl = swing_lows[cand]

            dr_high[i] = last_sh
            dr_low[i] = last_sl
            if not np.isnan(last_sh) and not np.isnan(last_sl) and last_sh > last_sl:
                dr_mid[i] = (last_sh + last_sl) / 2.0
            else:
                dr_mid[i] = np.nan

            # Detect Bullish OB: down bar before breaking swing high
            if i >= 3 and not np.isnan(last_sh) and closes[i] > last_sh and closes[i - 1] <= last_sh:
                for j in range(i - 1, max(0, i - 8), -1):
                    if closes[j] < opens[j]:
                        active_ob_top = highs[j]
                        active_ob_bot = lows[j]
                        break

            # Invalidate/mitigate OB if price drops below bot
            if not np.isnan(active_ob_bot) and lows[i] < active_ob_bot:
                active_ob_top = np.nan
                active_ob_bot = np.nan

            ob_bull_top[i] = active_ob_top
            ob_bull_bot[i] = active_ob_bot

        self.df_60k["dr_high"] = dr_high
        self.df_60k["dr_low"] = dr_low
        self.df_60k["dr_mid"] = dr_mid
        self.df_60k["ob_bull_top"] = ob_bull_top
        self.df_60k["ob_bull_bot"] = ob_bull_bot

    def _precompute_5k_pa_patterns(self):
        """Pre-computes Galen Woods Price Action patterns and ATR on 5K."""
        df = self.df_5k
        n = len(df)
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values

        # ATR calculation
        prev_closes = np.roll(closes, 1)
        prev_closes[0] = closes[0]
        tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_closes), np.abs(lows - prev_closes)))
        df["atr"] = pd.Series(tr).rolling(14, min_periods=1).mean().values

        is_tbf_long = np.zeros(n, dtype=bool)
        is_pin_bull = np.zeros(n, dtype=bool)
        is_rev_bull = np.zeros(n, dtype=bool)
        is_pz_bull = np.zeros(n, dtype=bool)  # Pressure Zone (2 consecutive strong bullish bars)

        for i in range(1, n):
            rng = highs[i] - lows[i]
            if rng <= 0:
                continue

            prev_rng = highs[i - 1] - lows[i - 1]
            prev_body = abs(closes[i - 1] - opens[i - 1])
            is_prev_bear = closes[i - 1] < opens[i - 1] and prev_body >= 0.4 * prev_rng

            # 1. TBF Long (Trend Bar Failure)
            if is_prev_bear and closes[i] > opens[i] and closes[i] >= highs[i - 1]:
                is_tbf_long[i] = True

            # 2. Bullish Pinbar (Lower wick >= 55% of candle range)
            lower_wick = min(opens[i], closes[i]) - lows[i]
            if lower_wick >= 0.55 * rng and closes[i] >= opens[i]:
                is_pin_bull[i] = True

            # 3. Bullish Reversal Bar (Pierces prev low, but closes above prev close)
            if lows[i] < lows[i - 1] and closes[i] > closes[i - 1] and closes[i] > opens[i]:
                is_rev_bull[i] = True

            # 4. Bullish Pressure Zone (2 consecutive strong trend bars closing near highs)
            if i >= 2:
                body_i = closes[i] - opens[i]
                body_prev = closes[i - 1] - opens[i - 1]
                if body_i >= 0.5 * rng and body_prev >= 0.5 * prev_rng and closes[i] > highs[i - 1]:
                    is_pz_bull[i] = True

        self.df_5k["pa_tbf"] = is_tbf_long
        self.df_5k["pa_pin"] = is_pin_bull
        self.df_5k["pa_rev"] = is_rev_bull
        self.df_5k["pa_pz"] = is_pz_bull

    def _align_features(self):
        """Aligns HTF 60K features onto 5K bars without lookahead bias."""
        df_5k = self.df_5k
        cols = ["ts", "dr_high", "dr_low", "dr_mid", "ob_bull_top", "ob_bull_bot", "ema_20", "ema_50"]
        df_60k = self.df_60k[cols].copy()

        aligned = pd.merge_asof(
            df_5k.sort_values("ts"),
            df_60k.sort_values("ts"),
            on="ts",
            direction="backward"
        )
        self.df_5k = aligned.reset_index(drop=True)

    def run_strategy(self, cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Executes lightning simulation for a single parameter configuration.
        """
        archetype = cfg.get("archetype", "dr_discount_pa")
        pa_filter = cfg.get("pa_filter", "tbf_or_pin")
        trend_filter = cfg.get("trend_filter", "ema20")  # "none", "ema20", "ema_golden"
        target_rr = float(cfg.get("target_rr", 1.5))
        target_mode = cfg.get("target_mode", "fixed_rr")  # "fixed_rr" or "dr_mid"
        holding_mode = cfg.get("holding_mode", "swing")  # "day_trade" or "swing"
        use_breakeven = bool(cfg.get("use_breakeven", False))
        be_trigger_rr = float(cfg.get("be_trigger_rr", 0.8))
        min_atr_sl_mult = float(cfg.get("min_atr_sl_mult", 0.8))  # Minimum SL buffer in ATR

        fee_rate = 0.001425 * 0.6
        tax_rate = 0.0015 if holding_mode == "day_trade" else 0.003

        df = self.df_5k
        n = len(df)
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        ts_arr = df["ts"].values
        atrs = df["atr"].values

        dr_high = df["dr_high"].values
        dr_low = df["dr_low"].values
        dr_mid = df["dr_mid"].values
        ob_top = df["ob_bull_top"].values
        ob_bot = df["ob_bull_bot"].values
        ema_20 = df["ema_20"].values
        ema_50 = df["ema_50"].values

        pa_tbf = df["pa_tbf"].values
        pa_pin = df["pa_pin"].values
        pa_rev = df["pa_rev"].values
        pa_pz = df["pa_pz"].values

        trades = []
        i = 10

        while i < n - 1:
            curr_close = closes[i]
            curr_low = lows[i]

            # 1. Trend Filter (60K Alignment)
            if trend_filter == "ema20":
                if np.isnan(ema_20[i]) or curr_close < ema_20[i]:
                    i += 1
                    continue
            elif trend_filter == "ema_golden":
                if np.isnan(ema_20[i]) or np.isnan(ema_50[i]) or ema_20[i] < ema_50[i]:
                    i += 1
                    continue

            # 2. Price Action Trigger
            pa_match = False
            if pa_filter == "tbf_only" and pa_tbf[i]:
                pa_match = True
            elif pa_filter == "pin_only" and pa_pin[i]:
                pa_match = True
            elif pa_filter == "pz_only" and pa_pz[i]:
                pa_match = True
            elif pa_filter == "tbf_or_pin" and (pa_tbf[i] or pa_pin[i]):
                pa_match = True
            elif pa_filter == "all" and (pa_tbf[i] or pa_pin[i] or pa_rev[i] or pa_pz[i]):
                pa_match = True

            if not pa_match:
                i += 1
                continue

            # 3. Structural Filters
            struct_match = False
            if archetype == "dr_discount_pa":
                # In 60K discount zone (price <= dr_mid)
                if not np.isnan(dr_mid[i]) and curr_close <= dr_mid[i]:
                    struct_match = True
            elif archetype == "dr_sweep_pa":
                # Pierced below dr_low and closed back above/near it
                if not np.isnan(dr_low[i]) and curr_low <= dr_low[i] and curr_close >= dr_low[i]:
                    struct_match = True
            elif archetype == "ob_retest_pa":
                # Touched 60K Bullish Order Block
                if not np.isnan(ob_top[i]) and not np.isnan(ob_bot[i]):
                    if curr_low <= ob_top[i] and curr_close >= ob_bot[i]:
                        struct_match = True
            elif archetype == "unfiltered_pa":
                struct_match = True

            if not struct_match:
                i += 1
                continue

            # Signal Triggered -> Entry at next bar Open
            entry_idx = i + 1
            if entry_idx >= n:
                break

            entry_price = opens[entry_idx]
            entry_ts = pd.Timestamp(ts_arr[entry_idx])

            # SL: Setup bar low minus ATR buffer protection
            atr_buf = atrs[i] * min_atr_sl_mult
            raw_sl = curr_low - atr_buf
            sl_price = min(raw_sl, entry_price * 0.99)  # At least 1% SL to avoid fee noise
            risk = entry_price - sl_price
            if risk <= 0:
                i += 1
                continue

            # TP Calculation
            if target_mode == "dr_mid" and not np.isnan(dr_mid[i]) and dr_mid[i] > entry_price:
                tp_price = dr_mid[i]
            else:
                tp_price = entry_price + (risk * target_rr)

            # Simulation Forward Loop
            exit_idx = entry_idx
            exit_price = entry_price
            exit_reason = "TIME_EXIT"
            be_active = False

            max_bars = 48 if holding_mode == "day_trade" else 240  # 1 day vs 5 days

            for k in range(entry_idx, min(n, entry_idx + max_bars)):
                k_ts = pd.Timestamp(ts_arr[k])
                k_open = opens[k]
                k_high = highs[k]
                k_low = lows[k]
                k_close = closes[k]

                # Day trade exit at 13:20
                if holding_mode == "day_trade" and k_ts.hour == 13 and k_ts.minute >= 20:
                    exit_idx = k
                    exit_price = k_close
                    exit_reason = "DAY_END"
                    break

                # Breakeven update
                if use_breakeven and not be_active:
                    if k_high >= entry_price + (risk * be_trigger_rr):
                        sl_price = entry_price
                        be_active = True

                # Check SL (Conservative: Gap down opens below SL must fill at actual open price)
                if k_low <= sl_price:
                    exit_idx = k
                    exit_price = min(k_open, sl_price)
                    exit_reason = "BE_HIT" if be_active else "SL_HIT"
                    break

                # Check TP
                if k_high >= tp_price:
                    exit_idx = k
                    exit_price = tp_price
                    exit_reason = "TP_HIT"
                    break

                exit_idx = k
                exit_price = k_close

            # Calculate Net Return
            gross_pnl_pct = (exit_price - entry_price) / entry_price
            net_pnl_pct = gross_pnl_pct - (fee_rate * 2) - tax_rate
            is_win = net_pnl_pct > 0

            trade_rec = {
                "entry_time": entry_ts.strftime("%Y-%m-%d %H:%M"),
                "exit_time": pd.Timestamp(ts_arr[exit_idx]).strftime("%Y-%m-%d %H:%M"),
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "sl_price": round(sl_price, 2),
                "tp_price": round(tp_price, 2),
                "net_pnl_pct": round(net_pnl_pct * 100, 2),
                "is_win": is_win,
                "exit_reason": exit_reason,
                "bars_held": exit_idx - entry_idx
            }
            trades.append(trade_rec)

            i = exit_idx + 1

        tot_trades = len(trades)
        if tot_trades == 0:
            return trades, {
                "trades": 0, "win_rate": 0.0, "net_pnl": 0.0,
                "profit_factor": 0.0, "max_drawdown": 0.0, "wins": 0, "losses": 0
            }

        wins = sum(1 for t in trades if t["is_win"])
        losses = tot_trades - wins
        wr = (wins / tot_trades) * 100.0

        pnl_arr = np.array([t["net_pnl_pct"] for t in trades])
        cum_pnl = np.cumsum(pnl_arr)
        peak = np.maximum.accumulate(cum_pnl)
        dd = peak - cum_pnl
        mdd = np.max(dd) if len(dd) > 0 else 0.0

        win_sum = sum(t["net_pnl_pct"] for t in trades if t["is_win"])
        loss_sum = abs(sum(t["net_pnl_pct"] for t in trades if not t["is_win"]))
        pf = (win_sum / loss_sum) if loss_sum > 0 else 999.0

        stats = {
            "trades": tot_trades,
            "win_rate": round(wr, 2),
            "net_pnl": round(float(np.sum(pnl_arr)), 2),
            "profit_factor": round(float(pf), 2),
            "max_drawdown": round(float(mdd), 2),
            "wins": wins,
            "losses": losses
        }
        return trades, stats
