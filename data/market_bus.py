# ============================================================
# data/market_bus.py — Merkezi Veri Bus v5
# ============================================================
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from data.adapters.base_adapter import BaseMarketDataAdapter
from data.models import MarketSnapshot


class MarketBus:
    def __init__(self, adapter: BaseMarketDataAdapter, snapshot_interval: float = 1.0):
        self._adapter   = adapter
        self._listeners: list[Callable[[MarketSnapshot], None]] = []
        self._lock      = threading.Lock()
        self._cache     = None
        self._collector_bridge = None
        self._snap_interval = snapshot_interval
        self._source_label  = "MOCK"
        self._connected     = False
        self._last_snap_ts  = datetime.now()
        self._snap_thread: Optional[threading.Thread] = None
        self._snap_stop   = threading.Event()

    def attach_collector(self, bridge, cache) -> None:
        self._collector_bridge = bridge
        self._cache = cache
        self._source_label = "REALTIME"

    def start(self) -> bool:
        if self._collector_bridge and self._cache:
            self._connected = True
            self._snap_stop.clear()
            self._snap_thread = threading.Thread(
                target=self._snapshot_loop, daemon=True, name="market-bus-snap"
            )
            self._snap_thread.start()
            return True
        else:
            connected = self._adapter.connect()
            self._adapter.subscribe(self._get_symbols())
            self._connected = connected
            return connected

    def stop(self) -> None:
        self._snap_stop.set()
        try:
            self._adapter.disconnect()
        except Exception:
            pass
        self._connected = False

    def _snapshot_loop(self) -> None:
        while not self._snap_stop.is_set():
            time.sleep(self._snap_interval)
            if self._snap_stop.is_set():
                break
            if self._cache:
                snap = self._cache.build_snapshot()
                if snap.ticks:
                    try:
                        if hasattr(self._adapter, "_snapshot"):
                            self._adapter._snapshot = snap
                    except Exception:
                        pass
                    self._last_snap_ts = datetime.now()
                    self._notify(snap)

    def add_listener(self, cb: Callable[[MarketSnapshot], None]) -> None:
        with self._lock:
            self._listeners.append(cb)

    def notify_listeners(self) -> None:
        snap = self.get_snapshot()
        self._notify(snap)

    def _notify(self, snap: MarketSnapshot) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(snap)
            except Exception:
                pass

    def get_snapshot(self) -> MarketSnapshot:
        if self._cache:
            return self._cache.build_snapshot()
        return self._adapter.get_latest_snapshot()

    @property
    def is_connected(self) -> bool:
        if self._collector_bridge:
            return self._collector_bridge.collector.is_connected
        return self._connected

    @property
    def source_label(self) -> str:
        if self._collector_bridge:
            col = self._collector_bridge.collector
            return col.__class__.__name__.replace("Collector", "")
        return self._source_label

    @property
    def last_update(self) -> datetime:
        if self._cache:
            return self._cache._last_update
        return self._last_snap_ts

    @property
    def collector_stats(self):
        if self._collector_bridge:
            return self._collector_bridge.collector.stats
        return None

    @property
    def adapter(self) -> BaseMarketDataAdapter:
        return self._adapter

    def _get_symbols(self) -> list[str]:
        from data.symbols import ACTIVE_UNIVERSE
        return ACTIVE_UNIVERSE
