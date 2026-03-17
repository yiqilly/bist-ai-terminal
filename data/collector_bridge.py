# ============================================================
# data/collector_bridge.py
# Collector ↔ SnapshotCache ↔ MarketBus Köprüsü v2
# ============================================================
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from data.collectors.base_collector import NormalizedQuote, NormalizedBar, BaseCollector
from data.snapshot_cache import SnapshotCache
from data.models import MarketTick, BarData

_log = logging.getLogger("CollectorBridge")


class CollectorBridge:
    """
    Collector → SnapshotCache akışını sağlar.
    MarketBus'un attach_collector() ile entegre edilir.
    """

    def __init__(self, collector: BaseCollector, cache: SnapshotCache):
        self._collector = collector
        self._cache     = cache
        # Callback'leri bağla
        collector.on_quote(self._on_quote)
        collector.on_bar(self._on_bar)

    def _on_quote(self, quote: NormalizedQuote) -> None:
        self._cache.update_from_quote(quote)

    def _on_bar(self, bar: NormalizedBar) -> None:
        self._cache.update_from_bar(bar)

    def start(self, symbols: list[str]) -> bool:
        return self._collector.start(symbols=symbols)

    def stop(self) -> None:
        self._collector.stop()

    @property
    def collector(self) -> BaseCollector:
        return self._collector

    @property
    def cache(self) -> SnapshotCache:
        return self._cache

    def status(self) -> str:
        s = self._collector.stats
        return (
            f"{self._collector.state} | "
            f"quotes={s.quotes_published} bars={s.bars_published} "
            f"drops={s.throttle_drops}"
        )


# ── Config Yükleme ──────────────────────────────────────────

def load_config(path: str | None = None) -> dict:
    config_path = path or os.path.join(
        os.path.dirname(__file__), "..", "config", "data_sources.yaml"
    )
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return _default_config()
    except FileNotFoundError:
        return _default_config()
    except Exception as e:
        _log.error(f"Config yükleme hatası: {e}")
        return _default_config()


def _default_config() -> dict:
    from data.symbols import ACTIVE_UNIVERSE
    return {
        "active_source": "mock",
        "symbols": ACTIVE_UNIVERSE,
        "timeframes": ["1m", "5m"],
        "borsapy": {"max_ticks_per_second": 10, "reconnect_backoff": [1, 3, 5, 10]},
    }


# ── Collector Factory ────────────────────────────────────────

def make_collector(source: str | None = None, config: dict | None = None) -> BaseCollector:
    cfg = config or load_config()
    src = source or cfg.get("active_source", "mock")

    if src == "borsapy":
        try:
            import borsapy  # noqa
            from data.collectors.tv_collector import TradingViewCollector
            borsapy_cfg = dict(cfg.get("borsapy", {}))
            borsapy_cfg["timeframes"] = cfg.get("timeframes", ["1m", "5m"])
            _log.info("TradingViewCollector (borsapy) oluşturuldu.")
            return TradingViewCollector(config=borsapy_cfg)
        except ImportError:
            _log.warning("borsapy bulunamadı → MockCollector'a geçildi.")
            return _make_mock(cfg)
    elif src in ("mock", "matriks", "csv", "foreks"):
        if src != "mock":
            _log.warning(f"'{src}' henüz implemente edilmedi → Mock kullanılıyor.")
        return _make_mock(cfg)
    else:
        _log.warning(f"Bilinmeyen kaynak '{src}' → Mock.")
        return _make_mock(cfg)


def _make_mock(cfg: dict):
    from data.collectors.mock_collector import MockCollector
    return MockCollector(config={"timeframes": cfg.get("timeframes", ["1m", "5m"])})


def make_realtime_bus(market_bus, source: str | None = None,
                      config: dict | None = None) -> CollectorBridge:
    """
    Collector + SnapshotCache + MarketBus'u birbirine bağlar.
    Döndürülen bridge'i başlatmak için bridge.start(symbols) çağrılır.

    Kullanım (main.py):
        bridge = make_realtime_bus(bus, config=cfg)
        bridge.start(symbols=symbols)
        bus.attach_collector(bridge, bridge.cache)
    """
    cfg       = config or load_config()
    cache     = SnapshotCache()
    collector = make_collector(source=source, config=cfg)
    bridge    = CollectorBridge(collector=collector, cache=cache)
    return bridge
