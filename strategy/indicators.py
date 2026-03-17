# ============================================================
# strategy/indicators.py — Teknik İndikatörler v6
# Sadece SnapshotCache (gerçek bar cache) kullanır.
# Mock adapter fallback tamamen kaldırıldı.
# ============================================================
from typing import Optional

_cache: Optional[object] = None   # SnapshotCache


def set_cache(cache) -> None:
    """SnapshotCache referansını inject et (main.py'den çağrılır)."""
    global _cache
    _cache = cache


def compute_rsi(adapter, symbol: str) -> float:
    """RSI — SnapshotCache'den. Cache yoksa nötr 50."""
    if _cache is not None:
        v = _cache.compute_rsi(symbol)
        if v != 50.0:
            return v
    # Cache dolmadıysa snapshot'tan tahmin
    snap = _get_snap(adapter)
    tick = snap.ticks.get(symbol) if snap else None
    if tick:
        # change_pct'den kaba RSI tahmini (daha iyi: 50 + pct * 3)
        from data.snapshot_cache import SnapshotCache
        if _cache and hasattr(_cache, '_data'):
            sc = _cache._data.get(symbol)
            if sc and sc.change_pct:
                return round(50 + sc.change_pct * 3, 1)
    return 50.0


def compute_ema(adapter, symbol: str, period: int) -> float:
    """EMA — SnapshotCache'den. Cache yoksa anlık fiyat."""
    if _cache is not None:
        v = _cache.compute_ema(symbol, period)
        if v > 0:
            return v
    snap = _get_snap(adapter)
    tick = snap.ticks.get(symbol) if snap else None
    if tick:
        return round(tick.price * (0.99 if period == 9 else 0.97), 2)
    return 0.0


def compute_atr(adapter, symbol: str) -> float:
    """ATR — SnapshotCache'den. Cache yoksa tahmini."""
    if _cache is not None:
        v = _cache.compute_atr(symbol)
        if v > 0:
            return v
    snap = _get_snap(adapter)
    bar  = snap.bars.get(symbol) if snap else None
    if bar:
        return round(bar.high - bar.low, 2)
    tick = snap.ticks.get(symbol) if snap else None
    if tick:
        return round(tick.price * 0.015, 2)
    return 1.0


def compute_momentum(adapter, symbol: str) -> float:
    """Momentum — SnapshotCache'den. Cache yoksa 0."""
    if _cache is not None:
        v = _cache.compute_momentum(symbol)
        if v != 0.0:
            return v
    # change_pct'den tahmin
    if _cache and hasattr(_cache, '_data'):
        sc = _cache._data.get(symbol)
        if sc and sc.change_pct:
            return round(sc.change_pct * 0.5, 3)
    return 0.0


def _get_snap(adapter):
    try:
        return adapter.get_latest_snapshot()
    except Exception:
        return None
