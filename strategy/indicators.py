# ============================================================
# strategy/indicators.py — v6.3.0 (Clean Bridge)
# Technical Analysis Bridge Layer
#
# BU MODÜL:
#   - Kodlama pratiklerini korumak için tasarlanmıştır.
#   - Arka planda IndicatorEngine (C-Speed) kullanır.
# ============================================================
from typing import Optional
from strategy.indicator_engine import IndicatorEngine

# Global bridge reference (main.py'den set_cache ile inject edilir)
_cache = None

def set_cache(cache_obj) -> None:
    global _cache
    _cache = cache_obj

def _get_cache():
    if not _cache:
        raise RuntimeError("Indicators must be initialized with set_cache(cache)")
    return _cache

def compute_rsi(adapter, symbol: str, period: int = 14) -> float:
    return _get_cache().compute_rsi(symbol, period)

def compute_ema(adapter, symbol: str, period: int) -> float:
    return _get_cache().compute_ema(symbol, period)

def compute_atr(adapter, symbol: str, period: int = 14) -> float:
    return _get_cache().compute_atr(symbol, period)

def compute_momentum(adapter, symbol: str, period: int = 10) -> float:
    return _get_cache().compute_momentum(symbol, period)

def compute_all(adapter, symbol: str) -> dict:
    """Tek seferde tüm indikatörleri döndür (optimizasyon)."""
    c = _get_cache()
    return {
        "rsi":      c.compute_rsi(symbol),
        "ema9":     c.compute_ema(symbol, 9),
        "ema21":    c.compute_ema(symbol, 21),
        "atr":      c.compute_atr(symbol),
        "momentum": c.compute_momentum(symbol),
    }
