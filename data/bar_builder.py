# ============================================================
# data/bar_builder.py
# Tick → OHLCV Bar Builder
#
# Her sembol × timeframe kombinasyonu için bağımsız buffer.
# TradingView'dan direkt candle stream geldiğinde bu modül
# bypass edilir (borsapy subscribe_chart kullanılır).
# Sadece tick-from-quote durumunda aktif olur.
#
# Desteklenen timeframe'ler: 1m, 5m, 15m, 30m, 1h
# ============================================================
from __future__ import annotations

import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Callable, Optional

from data.collectors.base_collector import NormalizedQuote, NormalizedBar


# ── Timeframe → dakika ──────────────────────────────────────

_TF_MINUTES: dict[str, int] = {
    "1m":  1,
    "5m":  5,
    "15m": 15,
    "30m": 30,
    "1h":  60,
    "4h":  240,
    "1d":  1440,
}


def _bar_start(ts: datetime, tf_minutes: int) -> datetime:
    """
    Bir timestamp'ın ait olduğu bar'ın başlangıç zamanını döndür.
    Örnek: 10:37:22 için 5m bar → 10:35:00
    """
    total_min = ts.hour * 60 + ts.minute
    rounded   = (total_min // tf_minutes) * tf_minutes
    return ts.replace(
        hour=rounded // 60,
        minute=rounded % 60,
        second=0,
        microsecond=0,
    )


# ── Açık Bar Buffer ─────────────────────────────────────────

class _OpenBar:
    """Henüz kapanmamış, aktif inşa edilen bar."""
    __slots__ = ("symbol", "timeframe", "tf_min",
                 "start_time", "open", "high", "low", "close", "volume",
                 "source")

    def __init__(self, symbol: str, tf: str, tf_min: int,
                 start: datetime, price: float, volume: float, source: str):
        self.symbol     = symbol
        self.timeframe  = tf
        self.tf_min     = tf_min
        self.start_time = start
        self.open       = price
        self.high       = price
        self.low        = price
        self.close      = price
        self.volume     = volume
        self.source     = source

    def update(self, price: float, volume: float) -> None:
        self.close   = price
        self.volume += volume
        if price > self.high: self.high = price
        if price < self.low:  self.low  = price

    def to_normalized(self, is_closed: bool = False) -> NormalizedBar:
        return NormalizedBar(
            symbol=self.symbol,
            timeframe=self.timeframe,
            open=round(self.open,  2),
            high=round(self.high,  2),
            low= round(self.low,   2),
            close=round(self.close, 2),
            volume=self.volume,
            start_time=self.start_time,
            is_closed=is_closed,
            source=self.source,
        )


# ── Ana Bar Builder ─────────────────────────────────────────

class BarBuilder:
    """
    Tick (NormalizedQuote) akışından 1m / 5m bar üretir.

    Kullanım:
        builder = BarBuilder(timeframes=["1m", "5m"], max_bars=200)
        builder.on_bar(my_callback)
        builder.on_tick(quote)     # Her quote gelişinde çağır

    Callback:
        def my_callback(bar: NormalizedBar) -> None:
            ...  # bar.is_closed == True → kapanmış bar
                 # bar.is_closed == False → mevcut anlık durum (opsiyonel)
    """

    def __init__(
        self,
        timeframes: list[str] | None = None,
        max_bars:   int   = 200,
        emit_live:  bool  = False,   # Her tick'te açık bar'ı da yayınla
    ):
        self._timeframes = timeframes or ["1m", "5m"]
        self._max_bars   = max_bars
        self._emit_live  = emit_live
        self._lock       = threading.Lock()

        # (symbol, tf) → _OpenBar
        self._open:  dict[tuple[str, str], _OpenBar]     = {}
        # (symbol, tf) → deque[NormalizedBar]  (kapalı barlar)
        self._closed: dict[tuple[str, str], deque]        = defaultdict(
            lambda: deque(maxlen=max_bars)
        )

        self._callbacks: list[Callable[[NormalizedBar], None]] = []

        # Geçersiz timeframe'leri filtrele
        self._tf_minutes: dict[str, int] = {
            tf: _TF_MINUTES[tf]
            for tf in self._timeframes
            if tf in _TF_MINUTES
        }

    # ── Callback ─────────────────────────────────────────────

    def on_bar(self, cb: Callable[[NormalizedBar], None]) -> None:
        self._callbacks.append(cb)

    # ── Ana giriş noktası ────────────────────────────────────

    def on_tick(self, quote: NormalizedQuote) -> None:
        """
        Her quote gelişinde çağır.
        Gerekirse mevcut bar'ı kapatır, yeni bar açar.
        """
        with self._lock:
            for tf, tf_min in self._tf_minutes.items():
                self._process(quote, tf, tf_min)

    # ── İşleme ──────────────────────────────────────────────

    def _process(self, q: NormalizedQuote, tf: str, tf_min: int) -> None:
        key        = (q.symbol, tf)
        bar_start  = _bar_start(q.timestamp, tf_min)
        price      = q.last
        volume     = q.volume

        if key not in self._open:
            # İlk tick — yeni bar aç
            self._open[key] = _OpenBar(
                q.symbol, tf, tf_min, bar_start, price, volume, q.source
            )
        else:
            current = self._open[key]

            if bar_start > current.start_time:
                # Bar sınırını geçtik → mevcut bar'ı kapat, yeni aç
                closed = current.to_normalized(is_closed=True)
                self._closed[key].append(closed)
                self._emit(closed)

                # Yeni bar
                self._open[key] = _OpenBar(
                    q.symbol, tf, tf_min, bar_start, price, volume, q.source
                )
            else:
                # Aynı bar → güncelle
                current.update(price, volume)
                if self._emit_live:
                    self._emit(current.to_normalized(is_closed=False))

    def _emit(self, bar: NormalizedBar) -> None:
        for cb in self._callbacks:
            try:
                cb(bar)
            except Exception as e:
                pass  # Callback hataları bar builder'ı durdurmamalı

    # ── Sorgu ────────────────────────────────────────────────

    def get_bars(self, symbol: str, tf: str, n: int = 50) -> list[NormalizedBar]:
        """Son n kapalı bar'ı döndür."""
        key   = (symbol, tf)
        bars  = list(self._closed.get(key, []))
        return bars[-n:] if len(bars) > n else bars

    def get_current_bar(self, symbol: str, tf: str) -> Optional[NormalizedBar]:
        """Şu an açık (henüz kapanmamış) bar'ı döndür."""
        key = (symbol, tf)
        ob  = self._open.get(key)
        return ob.to_normalized(is_closed=False) if ob else None

    def symbol_count(self) -> int:
        return len({k[0] for k in self._open})

    def bar_count(self, symbol: str, tf: str) -> int:
        return len(self._closed.get((symbol, tf), []))

    def flush(self, symbol: str | None = None) -> list[NormalizedBar]:
        """
        Açık barları zorla kapat (gün sonu / test için).
        symbol=None → tüm semboller.
        """
        flushed: list[NormalizedBar] = []
        with self._lock:
            keys = (
                [k for k in self._open if k[0] == symbol]
                if symbol else list(self._open.keys())
            )
            for key in keys:
                ob = self._open.pop(key)
                bar = ob.to_normalized(is_closed=True)
                self._closed[key].append(bar)
                flushed.append(bar)
                self._emit(bar)
        return flushed
