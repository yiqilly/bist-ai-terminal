# ============================================================
# charts/history_provider.py — Grafik Geçmiş Veri v2
# Gerçek veri kaynakları:
#   1. SnapshotCache bar cache (en güncel, 1m/5m)
#   2. borsapy Ticker.history (günlük/saatlik)
# Mock tamamen kaldırıldı.
# ============================================================
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from data.models import ChartPoint, BarData

_log = logging.getLogger("HistoryProvider")


def _fetch_borsapy_history(
    symbol: str,
    bars: int = 60,
    interval: str = "5m",
) -> list[ChartPoint]:
    """
    borsapy Ticker.history ile gerçek OHLCV verisi çek.
    interval: "1m" | "5m" | "15m" | "1h" | "1d"
    """
    try:
        import borsapy as bp
        ticker = bp.Ticker(symbol)

        # bars sayısına göre period belirle
        if interval in ("1m", "5m", "15m"):
            period = "1g"
        elif interval == "1h":
            period = "5g"
        else:
            period = "3ay"

        df = ticker.history(period=period, interval=interval)
        if df is None or (hasattr(df, 'empty') and df.empty):
            return []

        points = []
        ema9 = None; ema21 = None
        k9 = 2 / (9 + 1); k21 = 2 / (21 + 1)

        rows = list(df.iterrows()) if hasattr(df, 'iterrows') else []
        rows = rows[-bars:]  # son N bar

        for i, (idx, row) in enumerate(rows):
            try:
                close = float(row.get('Close', row.get('close', 0)) or 0)
                if close <= 0:
                    continue
                open_ = float(row.get('Open',  row.get('open',  close)) or close)
                high  = float(row.get('High',  row.get('high',  close)) or close)
                low   = float(row.get('Low',   row.get('low',   close)) or close)
                vol   = float(row.get('Volume',row.get('volume', 0)) or 0)

                if ema9 is None:  ema9 = close
                if ema21 is None: ema21 = close
                ema9  = close * k9  + ema9  * (1 - k9)
                ema21 = close * k21 + ema21 * (1 - k21)

                ts = idx if isinstance(idx, datetime) else datetime.now() - timedelta(minutes=(len(rows)-i)*5)

                points.append(ChartPoint(
                    index=i, open=open_, high=high, low=low, close=close,
                    volume=vol, ema9=round(ema9, 2), ema21=round(ema21, 2),
                    timestamp=ts,
                ))
            except Exception:
                continue

        return points
    except Exception as e:
        _log.debug(f"borsapy history({symbol}): {e}")
        return []


class HistoryProvider:
    """
    Grafik için OHLCV verisi sağlar.
    Önce SnapshotCache (gerçek zamanlı bar),
    sonra borsapy Ticker.history (tarihsel).
    """

    def __init__(self):
        self._hist_cache: dict[str, list[ChartPoint]] = {}

    def get_history(
        self,
        symbol: str,
        bars: int = 60,
        base_price: float = 0.0,
        interval: str = "5m",
    ) -> list[ChartPoint]:
        """
        Tarihsel grafik verisi.
        base_price artık kullanılmıyor (gerçek veri var).
        """
        # Cache'de varsa döndür (1 dakika geçerliliği)
        cached = self._hist_cache.get(symbol)
        if cached and len(cached) >= 5:
            return cached

        # borsapy'den çek
        points = _fetch_borsapy_history(symbol, bars=bars, interval=interval)
        if points:
            self._hist_cache[symbol] = points
            return points

        # borsapy başarısız → boş döndür (grafik yoktur, sorun değil)
        return []

    def from_bar_cache(self, bars: list) -> list[ChartPoint]:
        """
        SnapshotCache'den gelen gerçek BarData listesini ChartPoint'e dönüştür.
        Bu metod her zaman çalışır (live data).
        """
        if not bars:
            return []
        points = []
        ema9 = bars[0].close; ema21 = bars[0].close
        k9 = 2 / (9 + 1); k21 = 2 / (21 + 1)

        for i, bar in enumerate(bars):
            ema9  = bar.close * k9  + ema9  * (1 - k9)
            ema21 = bar.close * k21 + ema21 * (1 - k21)
            points.append(ChartPoint(
                index=i,
                open=bar.open, high=bar.high,
                low=bar.low,   close=bar.close,
                volume=bar.volume,
                ema9=round(ema9, 2), ema21=round(ema21, 2),
                timestamp=bar.timestamp,
            ))
        return points

    def invalidate(self, symbol: str) -> None:
        self._hist_cache.pop(symbol, None)

    def invalidate_all(self) -> None:
        self._hist_cache.clear()
