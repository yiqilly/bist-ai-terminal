# ============================================================
# strategy/edge_backtest/edge_signals.py
# Edge Signal Computation — Daily Timeframe
#
# Signals:
#   1. Relative Strength vs XU100 (20-day) — RS ratio > 1.3
#   2. Volume Expansion — volume > 3x SMA(20)
#   3. Tight Consolidation — low ATR range
#   4. Price Breakout — Close > 20-day high (prior)
#
# All 4 must fire for an entry signal.
# ============================================================
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd


# ── Thresholds & Parameters ──────────────────────────────────

RS_PERIOD = 20
RS_THRESHOLD = 1.15         # Stock must be outperforming index by 15% (lowered from 1.3)

VOL_PERIOD = 20
VOL_THRESHOLD = 1.5         # Volume expansion (lowered from 3.0)

ATR_PERIOD = 20           # ATR lookback for consolidation check
CONSOLIDATION_THRESHOLD = 0.05  # ATR/Close < 5% = tight range (widened from 3%)

BREAKOUT_PERIOD = 20      # 20-day high for breakout detection

# Minimum conditions required (out of 4): RS + Volume + Breakout are core
# Consolidation is a bonus signal
MIN_CORE_CONDITIONS = 3   # RS + Volume + Breakout


# ── ATR Helper ───────────────────────────────────────────────

def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.rolling(window=period, min_periods=period).mean()


# ── Individual Signal Computations ───────────────────────────

def compute_relative_strength(
    stock_df: pd.DataFrame,
    index_df: pd.DataFrame,
    period: int = RS_PERIOD,
) -> pd.Series:
    """
    Relative strength ratio: stock_return_Nd / index_return_Nd.
    Returns > 1 means outperforming.
    """
    stock_ret = stock_df["Close"].pct_change(period)
    
    # Align index to stock dates
    idx_close = index_df["Close"].reindex(stock_df.index, method="ffill")
    index_ret = idx_close.pct_change(period)

    # Avoid division by zero: use ratio of (1+ret)
    rs = (1 + stock_ret) / (1 + index_ret)
    return rs


def compute_volume_expansion(
    df: pd.DataFrame,
    period: int = VOL_PERIOD,
    threshold: float = VOL_THRESHOLD,
) -> pd.Series:
    """Boolean: volume > threshold × SMA(volume, period)."""
    vol_sma = df["Volume"].rolling(window=period, min_periods=period).mean()
    return df["Volume"] / vol_sma


def compute_consolidation(
    df: pd.DataFrame,
    period: int = ATR_PERIOD,
) -> pd.Series:
    """
    ATR(period) / Close — lower = tighter consolidation.
    Shifted by 1 day so we measure the consolidation BEFORE the breakout day.
    """
    atr = compute_atr(df, period)
    # Shift by 1: on breakout day, check if PRIOR period was tight
    return (atr / df["Close"]).shift(1)


def compute_breakout(
    df: pd.DataFrame,
    period: int = BREAKOUT_PERIOD,
) -> pd.Series:
    """Boolean: Close > rolling max(High) of previous 'period' days."""
    # Use .shift(1) so we compare to PRIOR 20-day high (no look-ahead)
    prior_high = df["High"].rolling(window=period, min_periods=period).max().shift(1)
    return df["Close"] > prior_high


def compute_breakout_distance(
    df: pd.DataFrame,
    period: int = BREAKOUT_PERIOD,
) -> pd.Series:
    """Distance to the 'period' high in percentage. Lower is closer to breakout."""
    prior_high = df["High"].rolling(window=period, min_periods=period).max().shift(1)
    # Avoid division by zero
    dist = (prior_high - df["Close"]) / df["Close"] * 100
    # If already broken out, distance is negative
    return dist


# ── Combined Edge Signal ─────────────────────────────────────

@dataclass
class EdgeDay:
    """One day's edge signals for a single symbol."""
    date: date
    symbol: str
    rs_ratio: float
    vol_ratio: float
    consolidation: float
    breakout: bool
    edge_active: bool    # all 4 conditions met
    close: float
    atr: float


def compute_edge_signals(
    symbol: str,
    stock_df: pd.DataFrame,
    index_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute all edge signals for a symbol, return DataFrame with signal columns.
    """
    df = stock_df.copy()

    # 1. Relative strength
    df["rs_ratio"] = compute_relative_strength(df, index_df, RS_PERIOD)

    # 2. Volume expansion
    df["vol_ratio"] = compute_volume_expansion(df, VOL_PERIOD, VOL_THRESHOLD)

    # 3. Consolidation
    df["consolidation"] = compute_consolidation(df, ATR_PERIOD)

    # 4. Breakout
    df["breakout"] = compute_breakout(df, BREAKOUT_PERIOD)
    df["breakout_distance"] = compute_breakout_distance(df, BREAKOUT_PERIOD)

    # ATR for stop/sizing
    df["atr"] = compute_atr(df, 14)

    # 5. Pullback Edge (Near 20 EMA, strong RS, low volume)
    ema20 = df["Close"].ewm(span=20, adjust=False).mean()
    dist_to_ema20 = (df["Low"] - ema20) / ema20
    
    pullback_edge = (
        (df["rs_ratio"] > 1.1) &                # Outperforming
        (dist_to_ema20.between(-0.02, 0.03)) &  # Touched or very close to 20 EMA
        (df["Close"] > ema20 * 0.98) &          # Hanging around EMA
        (df["vol_ratio"] < 1.5)                 # Normal or low volume
    )

    # Combined edge:
    # 1. Standard Breakout (20-day high)
    standard_breakout = (
        (df["rs_ratio"] > RS_THRESHOLD) &
        (df["vol_ratio"] > VOL_THRESHOLD) &
        (df["breakout"])
    )
    
    # 2. High RS Breakout (If RS is very high > 1.20, just a 10-day high is enough, on avg volume)
    breakout_10 = df["Close"] > df["High"].rolling(10, min_periods=10).max().shift(1)
    
    high_rs_breakout = (
        (df["rs_ratio"] > 1.20) &
        (df["vol_ratio"] > 1.0) &
        (breakout_10)
    )
    
    # Consolidation bonus: was the stock in a tight range before breakout?
    has_consolidation = df["consolidation"] < CONSOLIDATION_THRESHOLD
    
    # Signal triggers on any valid setup
    df["edge_active"] = standard_breakout | high_rs_breakout | pullback_edge
    
    # Base Edge score: 3 (core) + 1 (consolidation bonus) for quality ranking
    base_score = (
        (df["rs_ratio"] > RS_THRESHOLD).astype(float) +
        (df["vol_ratio"] > VOL_THRESHOLD).astype(float) +
        df["breakout"].astype(float) +
        has_consolidation.astype(float)
    )
    
    # Add rs_ratio/10 as a tie-breaker so the strongest relative strength stocks are picked first
    df["edge_score"] = base_score + (df["rs_ratio"] / 10.0)
    
    # Boost pullbacks and high_rs breakouts if they don't have a high base score
    df.loc[high_rs_breakout, "edge_score"] = np.maximum(df.loc[high_rs_breakout, "edge_score"], 3.0 + (df["rs_ratio"] / 10.0))
    df.loc[pullback_edge, "edge_score"] = np.maximum(df.loc[pullback_edge, "edge_score"], 2.8 + (df["rs_ratio"] / 10.0))

    df["symbol"] = symbol

    return df


def scan_universe(
    stock_data: dict[str, pd.DataFrame],
    index_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Scan all symbols and return a combined DataFrame of edge signals.
    """
    all_signals = []

    for sym, sdf in stock_data.items():
        if len(sdf) < 40:
            continue
        try:
            signals = compute_edge_signals(sym, sdf, index_df)
            if not signals.empty:
                all_signals.append(signals)
        except Exception:
            pass

    if not all_signals:
        return pd.DataFrame()

    combined = pd.concat(all_signals, ignore_index=False)
    # Don't try to sort index here, tracker can handle it
    return combined
