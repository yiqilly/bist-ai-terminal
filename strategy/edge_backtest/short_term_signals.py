# ============================================================
# strategy/edge_backtest/short_term_signals.py
# Edge Signal Computation — Aggressive Swing (1-3 days)
#
# Signals designed to catch explosive short-term momentum
# or extreme oversold bounces within an uptrend.
# ============================================================
from __future__ import annotations

import numpy as np
import pandas as pd
from strategy.edge_backtest.edge_signals import compute_atr


def compute_swing_signals(
    symbol: str,
    df_in: pd.DataFrame,
    index_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute aggressive short-term swing signals.
    """
    df = df_in.copy()
    
    # Needs some basic indicators
    df["atr"] = compute_atr(df, 14)
    df["sma50"] = df["Close"].rolling(50).mean()
    
    vol_sma = df["Volume"].rolling(20, min_periods=20).mean()
    df["vol_ratio"] = df["Volume"] / vol_sma
    
    # RSI(3) for extreme short-term exhaustion
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.ewm(span=3, adjust=False).mean() / (loss.ewm(span=3, adjust=False).mean() + 1e-9)
    df["rsi3"] = 100 - (100 / (1 + rs))

    # 1. 3-Day Oversold Bounce (Pullback in uptrend)
    # Price is above SMA 50, but RSI(3) is extremely low (< 15) and today features a green candle
    green_candle = df["Close"] > df["Open"]
    oversold_bounce = (
        (df["Close"] > df["sma50"]) &
        (df["rsi3"].shift(1) < 15) &  # RSI was oversold yesterday
        green_candle &
        (df["vol_ratio"] > 1.2)       # Buyers stepping in
    )

    # 2. Explosive Volume Breakout
    # Volume is > 4x average, price closes near the high of the day
    close_to_high = (df["High"] - df["Close"]) / (df["High"] - df["Low"] + 1e-9) < 0.2
    explosive_vol = (
        (df["vol_ratio"] > 4.0) &
        green_candle &
        close_to_high &
        (df["Close"] > df["sma50"])
    )

    df["edge_active"] = oversold_bounce | explosive_vol
    
    # Edge score determines priority when capital is constrained
    # Score favors explosive volume
    df["edge_score"] = 0.0
    df.loc[oversold_bounce, "edge_score"] = 2.0 + (30 - df["rsi3"].shift(1)) / 10.0  # Lower RSI = higher score
    df.loc[explosive_vol, "edge_score"] = 3.0 + df["vol_ratio"]  # Higher vol = higher score
    
    df["symbol"] = symbol

    return df


def scan_swing_universe(
    stock_data: dict[str, pd.DataFrame],
    index_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Scan all symbols and return a combined DataFrame of swing signals.
    """
    all_signals = []

    for sym, sdf in stock_data.items():
        if len(sdf) < 50:
            continue
        try:
            signals = compute_swing_signals(sym, sdf, index_df)
            if not signals.empty:
                # Only keep days where edge is active to save memory
                active_signals = signals[signals["edge_active"]]
                if not active_signals.empty:
                    all_signals.append(active_signals)
        except Exception:
            pass

    if not all_signals:
        return pd.DataFrame()

    combined = pd.concat(all_signals, ignore_index=False)
    return combined
