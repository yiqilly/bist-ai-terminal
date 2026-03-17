# ============================================================
# strategy/edge_backtest/daily_data.py
# Yahoo Finance daily OHLCV downloader for BIST universe
#
# Downloads BIST100 symbols + XU100 index, caches as Parquet.
# ============================================================
from __future__ import annotations

import os
import time as _time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf


# Cache directory next to this file
_CACHE_DIR = Path(__file__).parent / "cache"


def _yf_ticker(symbol: str) -> str:
    """Convert BIST symbol to Yahoo Finance ticker."""
    # Yahoo uses XU100.IS for the BIST100 index
    return f"{symbol}.IS"


def download_daily(
    symbols: list[str],
    start: date,
    end: date,
    cache: bool = True,
    progress: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    Download daily OHLCV for given symbols.

    Returns:
        {symbol: DataFrame} with columns [Open, High, Low, Close, Volume]
        Index is DatetimeIndex.
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    result: dict[str, pd.DataFrame] = {}
    to_download: list[str] = []

    # Check cache first
    if cache:
        for sym in symbols:
            cache_path = _CACHE_DIR / f"{sym}.parquet"
            if cache_path.exists():
                try:
                    df = pd.read_parquet(cache_path)
                    # Check if cache covers our date range
                    if len(df) > 0:
                        cached_start = df.index.min().date()
                        cached_end = df.index.max().date()
                        if cached_start <= start and cached_end >= end - timedelta(days=3):
                            # Filter to requested range
                            mask = (df.index.date >= start) & (df.index.date <= end)
                            result[sym] = df.loc[mask]
                            continue
                except Exception:
                    pass
            to_download.append(sym)
    else:
        to_download = list(symbols)

    if not to_download:
        return result

    # Download in batches to avoid rate limiting
    batch_size = 10
    total = len(to_download)

    for i in range(0, total, batch_size):
        batch = to_download[i:i + batch_size]
        if progress:
            print(f"  Downloading {i+1}-{min(i+batch_size, total)} / {total} symbols...")

        yf_tickers = [_yf_ticker(s) for s in batch]
        ticker_str = " ".join(yf_tickers)

        try:
            data = yf.download(
                ticker_str,
                start=str(start),
                end=str(end + timedelta(days=1)),  # yfinance end is exclusive
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )

            for sym, yf_tick in zip(batch, yf_tickers):
                try:
                    if len(batch) == 1:
                        df = data.copy()
                    else:
                        df = data[yf_tick].copy()

                    # Handle multi-level columns
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.droplevel(0)

                    # Keep only OHLCV
                    needed = ["Open", "High", "Low", "Close", "Volume"]
                    available = [c for c in needed if c in df.columns]
                    if len(available) < 4:
                        continue
                    df = df[available].dropna(subset=["Close"])

                    if len(df) < 20:
                        continue

                    # Cache
                    if cache:
                        cache_path = _CACHE_DIR / f"{sym}.parquet"
                        df.to_parquet(cache_path)

                    # Filter to requested range
                    mask = (df.index.date >= start) & (df.index.date <= end)
                    result[sym] = df.loc[mask]

                except Exception:
                    continue

        except Exception as e:
            if progress:
                print(f"  [!] Batch download error: {e}")

        # Small delay between batches
        if i + batch_size < total:
            _time.sleep(1)

    if progress:
        print(f"  [OK] Loaded {len(result)} / {len(symbols)} symbols")

    return result


def load_bist100_universe() -> list[str]:
    """Return BIST100 symbol list from the project's symbols.py."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from data.symbols import BIST100
    return BIST100


def load_index_and_universe(
    start: date,
    end: date,
    universe: Optional[list[str]] = None,
    cache: bool = True,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """
    Convenience: download XU100 index + all universe symbols.

    Returns:
        (index_df, {symbol: df})
    """
    syms = universe or load_bist100_universe()

    # Download index
    print("[*] Downloading XU100 index...")
    idx_data = download_daily(["XU100"], start, end, cache=cache)
    index_df = idx_data.get("XU100", pd.DataFrame())

    if index_df.empty:
        print("  [!] XU100 download failed, will use equal-weight proxy")

    # Download universe
    print(f"[*] Downloading {len(syms)} BIST symbols...")
    stock_data = download_daily(syms, start, end, cache=cache)

    return index_df, stock_data
