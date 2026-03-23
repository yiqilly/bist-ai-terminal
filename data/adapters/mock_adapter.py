# ============================================================
# data/adapters/mock_adapter.py — Mock Veri Adaptörü (v2)
# ============================================================
import random
import threading
import time
from datetime import datetime
from data.adapters.base_adapter import BaseMarketDataAdapter
from data.models import MarketSnapshot, MarketTick, BarData
from data.symbols import ACTIVE_UNIVERSE


class MockMarketDataAdapter(BaseMarketDataAdapter):
    # Base prices for core BIST30 (fallback for others)
    BASE_PRICES: dict[str, float] = {
        "AKBNK": 55.0,  "ARCLK": 190.0, "ASELS": 105.0, "BIMAS": 430.0,
        "DOHOL": 30.0,  "EKGYO": 100.0, "EREGL": 70.0,  "FROTO": 1400.0,
        "GARAN": 110.0, "GUBRF": 200.0, "HALKB": 25.0,  "ISCTR": 55.0,
        "KCHOL": 200.0, "KOZAA": 45.0,  "KOZAL": 180.0, "KRDMD": 28.0,
        "MGROS": 340.0, "ODAS":  50.0,  "PETKM": 30.0,  "PGSUS": 900.0,
        "SAHOL": 105.0, "SASA":  2.5,   "SISE":  45.0,  "SOKM":  70.0,
        "TAVHL": 200.0, "TCELL": 95.0,  "THYAO": 300.0, "TKFEN": 95.0,
        "TOASO": 400.0, "TUPRS": 200.0,
    }

    def __init__(self, update_interval: float = 2.0):
        super().__init__()
        self._update_interval = update_interval
        # Initialize prices for all symbols in the active universe
        self._prices: dict[str, float] = {
            s: self.BASE_PRICES.get(s, 100.0) for s in ACTIVE_UNIVERSE
        }
        self._prev_prices: dict[str, float] = dict(self._prices)
        self._volumes: dict[str, float] = {s: random.uniform(1e6, 5e6) for s in ACTIVE_UNIVERSE}
        self._rsi: dict[str, float] = {s: random.uniform(45, 78) for s in ACTIVE_UNIVERSE}
        self._momentum: dict[str, float] = {s: random.uniform(-3, 3) for s in ACTIVE_UNIVERSE}
        self._atr: dict[str, float] = {s: p * 0.015 for s, p in self._prices.items()}
        self._subscribed: list[str] = []
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._snapshot = MarketSnapshot()

    def connect(self) -> bool:
        self._connected = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        return True

    def disconnect(self) -> None:
        self._stop_event.set()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def subscribe(self, symbols: list[str]) -> None:
        self._subscribed = symbols

    def unsubscribe(self, symbols: list[str]) -> None:
        self._subscribed = [s for s in self._subscribed if s not in symbols]

    def get_latest_snapshot(self) -> MarketSnapshot:
        return self._snapshot

    def _update_loop(self) -> None:
        while not self._stop_event.is_set():
            self._tick_all()
            time.sleep(self._update_interval)

    def _tick_all(self) -> None:
        now = datetime.now()
        advancing = declining = 0
        ticks: dict[str, MarketTick] = {}
        bars: dict[str, BarData] = {}

        for symbol in ACTIVE_UNIVERSE:
            prev = self._prices[symbol]
            self._prev_prices[symbol] = prev

            change_pct = random.gauss(0, 0.003)
            new_price = round(prev * (1 + change_pct), 2)
            self._prices[symbol] = new_price

            self._rsi[symbol] = max(10, min(90, self._rsi[symbol] + random.gauss(0, 0.8)))
            self._momentum[symbol] = round(self._momentum[symbol] * 0.9 + change_pct * 100 * 0.1, 3)
            self._volumes[symbol] = round(self._volumes[symbol] * random.uniform(0.95, 1.05), 0)

            ticks[symbol] = MarketTick(
                symbol=symbol, price=new_price,
                bid=round(new_price * 0.9995, 2), ask=round(new_price * 1.0005, 2),
                volume=self._volumes[symbol], timestamp=now,
            )
            bars[symbol] = BarData(
                symbol=symbol,
                open=round(prev, 2),
                high=round(max(prev, new_price) * 1.002, 2),
                low=round(min(prev, new_price) * 0.998, 2),
                close=new_price, volume=self._volumes[symbol], timestamp=now,
            )
            if new_price > prev: advancing += 1
            elif new_price < prev: declining += 1
            self._emit_tick(ticks[symbol])

        self._snapshot = MarketSnapshot(
            ticks=ticks, bars=bars, timestamp=now,
            advancing=advancing, declining=declining,
            unchanged=len(ACTIVE_UNIVERSE) - advancing - declining,
        )

    def get_rsi(self, symbol: str) -> float:
        return round(self._rsi.get(symbol, 50.0), 1)

    def get_momentum(self, symbol: str) -> float:
        return self._momentum.get(symbol, 0.0)

    def get_atr(self, symbol: str) -> float:
        return round(self._atr.get(symbol, 1.0), 2)

    def get_ema(self, symbol: str, period: int = 9) -> float:
        price = self._prices.get(symbol, 100.0)
        offset = 0.98 if period == 9 else 0.96
        return round(price * offset, 2)

    def get_prev_price(self, symbol: str) -> float:
        return self._prev_prices.get(symbol, self._prices.get(symbol, 0.0))
