# ============================================================
# data/snapshot_cache.py — v3
# Merkezi Snapshot Cache
#
# DEĞİŞİKLİKLER:
#   - İndikatör hesaplamaları IndicatorEngine'e taşındı (Circular dep fix)
#   - EMA, RSI, ATR optimizasyonu
# ============================================================
from __future__ import annotations

import math
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from data.models import MarketTick, BarData, MarketSnapshot
from strategy.indicator_engine import IndicatorEngine


# ── Güvenli change_pct hesabı ────────────────────────────────

_MAX_CHANGE_PCT = 25.0   # Gerçekçi sınır: BIST devre kesici ~%20 + buffer
_MIN_PREV_CLOSE_RATIO = 0.50  # prev_close, last'in en az %50'si olmalı (2x fark)

def _safe_change_pct(last: float, prev_close: float) -> Optional[float]:
    """
    Güvenli change_pct hesabı.
    Şüpheli prev_close değerlerini reddeder.

    BIST devre kesici limiti: günlük ±%20.
    Burada ±25% olarak tanımlıyoruz (buffer + haftalık hareketler).

    Döndürür: float veya None (hesaplanamadıysa)
    """
    if last <= 0 or prev_close <= 0:
        return None

    # prev_close makul aralıkta mı?
    # Bir günde fiyat 2x veya 0.5x olması çok nadir — bunların üstü hata
    ratio = last / prev_close
    if ratio > 2.5 or ratio < 0.40:
        # prev_close çok farklı → güvenilmez (ör. split/hata/yanlış sembol)
        return None

    pct = (last - prev_close) / prev_close * 100

    # Günlük sınırı aş → şüpheli
    if abs(pct) > _MAX_CHANGE_PCT:
        return None

    # Manual round 3 digits to avoid linter ndigits=None error
    return float(int(pct * 1000) / 1000.0)


# ── Sembol Normalize ─────────────────────────────────────────

def _normalize_symbol(raw: str) -> str:
    """BIST:SASA, IST:THYAO → SASA, THYAO"""
    if ":" in raw:
        return raw.split(":")[-1].strip().upper()
    return raw.strip().upper()


# ── SymbolCache ──────────────────────────────────────────────

@dataclass
class SymbolCache:
    """Tek sembol için tüm anlık veriler."""
    symbol:     str

    last:       float = 0.0
    bid:        float = 0.0
    ask:        float = 0.0
    volume:     float = 0.0
    change_pct: float = 0.0
    prev_close: float = 0.0   # önceki kapanış (borsapy'den)
    open_day:   float = 0.0   # gün içi açılış (fallback için)
    high_day:   float = 0.0
    low_day:    float = 0.0
    updated_at: Optional[datetime] = None

    # change_pct güvenilir mi?
    change_pct_reliable: bool = False

    # Bar cache
    bars: dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=200))
    )

    def to_tick(self) -> MarketTick:
        return MarketTick(
            symbol    = self.symbol,
            price     = self.last,
            bid       = self.bid,
            ask       = self.ask,
            volume    = self.volume,
            timestamp = self.updated_at or datetime.now(),
        )

    def latest_bar(self, tf: str = "1m") -> Optional[BarData]:
        b = self.bars.get(tf)
        return b[-1] if b else None

    @property
    def spread(self) -> float:
        if not self.ask or not self.bid:
            return 0.0
        diff = float(self.ask) - float(self.bid)
        return float(int(diff * 10000) / 10000.0)


# ── SnapshotCache ─────────────────────────────────────────────

class SnapshotCache:
    """
    Tüm sembollerin anlık verisini tutan merkezi cache.

    Veri akışı:
        Collector → update_from_quote() / update_from_bar()
        Timer (1s) → build_snapshot() → market_bus.notify()
    """

    def __init__(self, max_bars: int = 200):
        self._data:  dict[str, SymbolCache] = {}
        self._lock   = threading.RLock()
        self._max_bars = max_bars
        self._total_quotes = 0
        self._total_bars   = 0
        self._last_update  = datetime.now()
        self._prev_prices: dict[str, float] = {}

    # ── Veri Güncelleme ──────────────────────────────────────

    def update_from_quote(self, quote) -> None:
        """
        NormalizedQuote geldi → cache güncelle.

        change_pct hesabı güvenli kurallar:
          1. prev_close borsapy'den geldiyse → hesapla
          2. prev_close yoksa open_day'e bak (bar'dan gelir)
          3. İkisi de yoksa quote.change_pct'yi kullan (borsapy'nin kendi hesabı)
          4. Hiçbiri yoksa 0 bırak
          5. Sonuç ±30% sınırını aşıyorsa reddet
        """
        # Sembol normalize (BIST:SASA → SASA)
        sym = _normalize_symbol(quote.symbol)

        with self._lock:
            if sym not in self._data:
                self._data[sym] = SymbolCache(symbol=sym)
            sc = self._data[sym]

            # Önceki fiyatı kaydet (advancing/declining için)
            if sc.last > 0:
                self._prev_prices.setdefault(sym, sc.last)

            # Anlık değerleri güncelle
            sc.last       = quote.last
            sc.bid        = quote.bid
            sc.ask        = quote.ask
            sc.volume     = quote.volume
            sc.updated_at = quote.timestamp

            # Gün içi high/low
            if quote.high_day > 0:
                sc.high_day = quote.high_day
            elif sc.high_day > 0:
                sc.high_day = max(sc.high_day, quote.last)
            else:
                sc.high_day = quote.last

            if quote.low_day > 0:
                sc.low_day = quote.low_day
            elif sc.low_day > 0:
                sc.low_day = min(sc.low_day, quote.last)
            else:
                sc.low_day = quote.last

            # ── prev_close güncelle ──────────────────────────
            if quote.prev_close > 0:
                # Makul aralık kontrolü: prev_close, last'in %33-%300'ü arasında olmalı
                ratio = quote.last / quote.prev_close if quote.prev_close > 0 else 0
                if 0.33 <= ratio <= 3.0:
                    sc.prev_close = quote.prev_close
                # else: şüpheli prev_close, görmezden gel

            # ── change_pct hesabı ────────────────────────────
            self._recalc_change_pct(sc, quote)

            self._total_quotes += 1
            self._last_update   = quote.timestamp

    def _recalc_change_pct(self, sc: SymbolCache, quote) -> None:
        """
        Öncelik sırası:
          1. prev_close ile kendi hesabımız (en güvenilir)
          2. open_day ile yaklaşım (prev_close yoksa)
          3. borsapy'nin gönderdiği change_percent
          4. 0 (bilinmiyor)
        """
        # Öncelik 1: prev_close ile hesapla
        if sc.prev_close > 0:
            pct = _safe_change_pct(sc.last, sc.prev_close)
            if pct is not None:
                sc.change_pct = pct
                sc.change_pct_reliable = True
                return

        # Öncelik 2: open_day ile yaklaşım
        if sc.open_day > 0:
            pct = _safe_change_pct(sc.last, sc.open_day)
            if pct is not None:
                sc.change_pct = pct
                sc.change_pct_reliable = True
                return

        # Öncelik 3: borsapy'nin change_pct'si
        if hasattr(quote, 'change_pct') and quote.change_pct != 0:
            raw = quote.change_pct
            if abs(raw) <= _MAX_CHANGE_PCT:
                sc.change_pct = round(raw, 3)
                sc.change_pct_reliable = True
                return

        # Öncelik 4: 0 bırak (bilinmiyor)
        # Eğer zaten bir değer varsa koru
        if sc.change_pct == 0:
            sc.change_pct_reliable = False

    def update_from_bar(self, bar) -> None:
        """NormalizedBar geldi → bar cache güncelle."""
        sym = _normalize_symbol(bar.symbol)
        tf  = bar.timeframe

        with self._lock:
            if sym not in self._data:
                self._data[sym] = SymbolCache(symbol=sym)
            sc = self._data[sym]

            bd = BarData(
                symbol    = sym,
                open      = bar.open,
                high      = bar.high,
                low       = bar.low,
                close     = bar.close,
                volume    = bar.volume,
                timestamp = bar.start_time,
            )
            sc.bars[tf].append(bd)
            self._total_bars += 1

            # Günlük bar'dan open_day al (prev_close yoksa fallback)
            if tf in ("1d", "D"):
                if sc.open_day == 0 and bar.open > 0:
                    sc.open_day = bar.open
                # Günlük bar'ın open'ı önceki günün close'u gibi davranabilir
                # Ama bu tam doğru değil — sadece yedek olarak kullanıyoruz

            # 1m bar: günlük açılışı bul (gün başı bar)
            if tf == "1m":
                bars_today = list(sc.bars.get("1m", []))
                if bars_today:
                    # Günün ilk barının open'ı → open_day
                    first = bars_today[0]
                    now   = datetime.now()
                    if (now - first.timestamp).total_seconds() < 86400:
                        sc.open_day = first.open

            # Bar'dan last fiyatı da güncelle (bar yoksa quote zaten vardır)
            if sc.last == 0 and bar.close > 0:
                sc.last = bar.close

    # ── Snapshot Üretme ─────────────────────────────────────

    def build_snapshot(self) -> MarketSnapshot:
        with self._lock:
            ticks:    dict[str, MarketTick] = {}
            bars:     dict[str, BarData]    = {}
            advancing: int = 0
            declining: int = 0
            unchanged: int = 0

            for sym, sc in self._data.items():
                if sc.last <= 0 or not sc.updated_at:
                    continue

                tick = sc.to_tick()
                ticks[sym] = tick

                # Yükseliş/Düşüş (change_pct'ye göre)
                if sc.change_pct > 0.05:
                    advancing = advancing + 1
                elif sc.change_pct < -0.05:
                    declining = declining + 1
                else:
                    unchanged = unchanged + 1

                bar = sc.latest_bar("1m") or sc.latest_bar("5m")
                if bar:
                    bars[sym] = bar

            return MarketSnapshot(
                ticks     = ticks,
                bars      = bars,
                timestamp = self._last_update,
                advancing = advancing,
                declining = declining,
                unchanged = unchanged,
            )

    # ── Sembol Sorgulama ─────────────────────────────────────

    def get_symbol(self, symbol: str) -> Optional[SymbolCache]:
        sym = _normalize_symbol(symbol)
        with self._lock:
            return self._data.get(sym)

    def get_change_pct(self, symbol: str) -> float:
        """Güvenilir change_pct döndür."""
        sc = self.get_symbol(symbol)
        return sc.change_pct if sc else 0.0

    def get_bars(self, symbol: str, tf: str = "1m", n: int = 60) -> list[BarData]:
        sym = _normalize_symbol(symbol)
        with self._lock:
            sc = self._data.get(sym)
            if not sc:
                return []
            # deque to list for safe indexing
            bar_list = list(sc.bars.get(tf, []))
            return bar_list[-n:]

    def all_symbols(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())

    def symbol_count(self) -> int:
        return len(self._data)

    def is_stale(self, max_age_sec: float = 10.0) -> bool:
        return (datetime.now() - self._last_update).total_seconds() > max_age_sec

    # ── İndikatör Hesaplama ──────────────────────────────────

    def compute_ema(self, symbol: str, period: int, tf: str = "1m") -> float:
        bars = self.get_bars(symbol, tf, n=period * 4)
        if not bars: return 0.0
        return IndicatorEngine.ema([b.close for b in bars], period)

    def compute_rsi(self, symbol: str, period: int = 14, tf: str = "1m") -> float:
        bars = self.get_bars(symbol, tf, n=period * 3)
        if len(bars) < period + 1:
            sc = self.get_symbol(symbol)
            return 50.0 if not sc else round(max(0.0, min(100.0, 50 + sc.change_pct * 3)), 1)
        return IndicatorEngine.rsi([b.close for b in bars], period)

    def compute_atr(self, symbol: str, period: int = 14, tf: str = "1m") -> float:
        bars = self.get_bars(symbol, tf, n=period * 2)
        if not bars:
            sc = self.get_symbol(symbol)
            return sc.last * 0.012 if sc else 1.0
        return IndicatorEngine.atr([b.high for b in bars], [b.low for b in bars], [b.close for b in bars], period)

    def compute_momentum(self, symbol: str, period: int = 10, tf: str = "1m") -> float:
        bars = self.get_bars(symbol, tf, n=period + 1)
        if len(bars) < 2:
            sc = self.get_symbol(symbol)
            return sc.change_pct if sc else 0.0
        return round((bars[-1].close - bars[0].close) / bars[0].close * 100, 3)

    @property
    def stats(self) -> dict:
        return {
            "symbols":     self.symbol_count(),
            "quotes":      self._total_quotes,
            "bars":        self._total_bars,
            "last_update": self._last_update.strftime("%H:%M:%S"),
            "stale":       self.is_stale(),
        }


