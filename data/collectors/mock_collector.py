# ============================================================
# data/collectors/mock_collector.py
# Mock Collector — Geliştirme / Test / Offline Mod
#
# borsapy kurulu olmadan çalışır.
# GBM (Geometric Brownian Motion) ile gerçekçi fiyat simülasyonu.
# ============================================================
from __future__ import annotations

import math
import random
import threading
import time
from datetime import datetime

from data.collectors.base_collector import (
    BaseCollector, CollectorState,
    NormalizedQuote, NormalizedBar,
)
from data.bar_builder import BarBuilder


# Aktif evrendeki hisseler için başlangıç fiyatları (yaklaşık gerçek değerler)
_BASE_PRICES: dict[str, float] = {
    "AKBNK": 56.0,   "THYAO": 299.0,  "EREGL": 68.0,   "FROTO": 1350.0,
    "ISCTR": 62.0,   "KCHOL": 215.0,  "BIMAS": 430.0,  "SAHOL": 105.0,
    "ASELS": 105.0,  "TUPRS": 210.0,  "GARAN": 72.0,   "YKBNK": 28.0,
    "SISE":  47.0,   "SASA":  42.0,   "PETKM": 31.0,   "TCELL": 94.0,
    "KOZAL": 180.0,  "KOZAA": 48.0,   "HALKB": 27.0,   "VESTL": 82.0,
    "ENKAI": 55.0,   "ARCLK": 195.0,  "KRDMD": 30.0,   "OTKAR": 1800.0,
    "DOHOL": 30.0,   "GUBRF": 165.0,  "ALARK": 55.0,   "BRYAT": 185.0,
    "CIMSA": 72.0,   "TOASO": 425.0,
}


class MockCollector(BaseCollector):
    """
    Geliştirme ortamı için gerçek veri simüle eden collector.
    GBM + U-şekli intraday volatilite profili.
    """

    SOURCE = "mock"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        cfg = config or {}

        self._interval    = cfg.get("poll_interval_sec", 2.0)
        self._prices: dict[str, float] = {}
        self._volumes: dict[str, float] = {}
        self._sigma  = 0.003   # Tick başına std dev

        tf_list = cfg.get("timeframes", ["1m", "5m"])
        self._bar_builder = BarBuilder(timeframes=tf_list)
        self._bar_builder.on_bar(self._on_built_bar)

        self._stop_event  = threading.Event()
        self._thread: threading.Thread | None = None

    def connect(self) -> bool:
        self._state = CollectorState.CONNECTED
        return True

    def disconnect(self) -> None:
        self._stop_event.set()
        self._state = CollectorState.DISCONNECTED

    def subscribe(self, symbol: str) -> None:
        """Sembole abone ol — fiyat buffer'ını başlat."""
        self._prices[symbol]  = _BASE_PRICES.get(symbol, 100.0)
        self._volumes[symbol] = random.uniform(500_000, 3_000_000)

    def start(self, symbols: list[str]) -> bool:
        ok = super().start(symbols)
        if ok:
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._tick_loop, daemon=True, name="mock-collector"
            )
            self._thread.start()
        return ok

    def _tick_loop(self) -> None:
        while not self._stop_event.is_set():
            now = datetime.now()
            for sym in list(self._prices.keys()):
                self._emit_tick(sym, now)
            time.sleep(self._interval)

    def _emit_tick(self, symbol: str, now: datetime) -> None:
        price = self._prices[symbol]
        vol   = self._volumes[symbol]

        # GBM adımı
        z     = random.gauss(0, 1)
        ret   = self._sigma * z
        price = round(price * math.exp(ret), 2)
        vol   = round(vol * random.uniform(0.97, 1.03))

        self._prices[symbol]  = price
        self._volumes[symbol] = vol

        spread  = round(price * 0.0003, 2)
        quote = NormalizedQuote(
            symbol    = symbol,
            last      = price,
            bid       = round(price - spread / 2, 2),
            ask       = round(price + spread / 2, 2),
            volume    = vol,
            timestamp = now,
            source    = self.SOURCE,
        )

        self._bar_builder.on_tick(quote)
        self._publish_quote(quote)
        self._stats.quotes_received += 1

    def _on_built_bar(self, bar: NormalizedBar) -> None:
        if bar.is_closed:
            self._publish_bar(bar)
            self._stats.bars_received += 1
