# ============================================================
# strategy/scanner.py — Piyasa Tarama Motoru v3
# prev_price artık SnapshotCache'den (prev_close) geliyor
# ============================================================
from data.adapters.base_adapter import BaseMarketDataAdapter
from data.adapters.mock_adapter import MockMarketDataAdapter
from data.models import SignalCandidate, MarketSnapshot
from data.symbols import ACTIVE_UNIVERSE
from strategy.indicators import compute_rsi, compute_ema, compute_atr, compute_momentum
from strategy.rules import score_candidate, passes_filter

# Global cache referansı (main.py'den set_cache() ile inject edilir)
_snapshot_cache = None

def set_scanner_cache(cache) -> None:
    global _snapshot_cache
    _snapshot_cache = cache


class MarketScanner:
    def __init__(self, adapter: BaseMarketDataAdapter):
        self._adapter = adapter

    def scan(self, snapshot: MarketSnapshot) -> list[SignalCandidate]:
        candidates = []
        for symbol in ACTIVE_UNIVERSE:
            tick = snapshot.ticks.get(symbol)
            if not tick:
                continue

            rsi      = compute_rsi(self._adapter, symbol)
            ema9     = compute_ema(self._adapter, symbol, 9)
            ema21    = compute_ema(self._adapter, symbol, 21)
            atr      = compute_atr(self._adapter, symbol)
            momentum = compute_momentum(self._adapter, symbol)

            # ── prev_price kaynağı ───────────────────────────
            # Öncelik sırası:
            # 1. SnapshotCache'deki prev_close (borsapy'den gelen gerçek değer)
            # 2. Mock adapter'ın prev_price'ı
            # 3. tick.price (hiçbir şey yoksa — change_pct = 0 olur)
            prev_price = self._get_prev_price(symbol, tick.price)

            trend          = ema9 > ema21
            breakout       = tick.price > ema9
            volume_confirm = tick.volume > 2_000_000

            candidate = SignalCandidate(
                symbol=symbol, price=tick.price, volume=tick.volume,
                rsi=rsi, ema9=ema9, ema21=ema21, atr=atr, momentum=momentum,
                trend=trend, breakout=breakout, volume_confirm=volume_confirm,
                score=0, prev_price=prev_price,
            )
            candidate.score = score_candidate(candidate)
            candidates.append(candidate)
        return candidates

    def _get_prev_price(self, symbol: str, current_price: float) -> float:
        """
        Sembol için önceki kapanış fiyatını al.

        Öncelik:
          1. SnapshotCache.prev_close (gerçek borsapy verisi)
          2. MockAdapter.get_prev_price (mock mod)
          3. current_price (fallback — change_pct sıfır olacak)
        """
        # 1. SnapshotCache
        if _snapshot_cache is not None:
            sc = _snapshot_cache.get_symbol(symbol)
            if sc and sc.prev_close > 0:
                ratio = current_price / sc.prev_close
                if 0.5 <= ratio <= 2.0:   # günlük ±50% sınırı
                    return sc.prev_close

        # 2. Mock adapter — ratio kontrolü ile
        if isinstance(self._adapter, MockMarketDataAdapter):
            prev = self._adapter.get_prev_price(symbol)
            if prev > 0 and current_price > 0:
                ratio = current_price / prev
                if 0.75 <= ratio <= 1.33:  # ±25% sınırı
                    return prev
            # Mock'ta prev_price güvenilir değilse 0 değişim göster
            return current_price

        # 3. Fallback — change_pct = 0
        return current_price

    def get_best_signals(self, snapshot: MarketSnapshot) -> list[SignalCandidate]:
        return sorted(
            [c for c in self.scan(snapshot) if passes_filter(c)],
            key=lambda c: c.score, reverse=True
        )

    def get_momentum_leaders(self, snapshot: MarketSnapshot, top_n: int = 10) -> list[SignalCandidate]:
        return sorted(self.scan(snapshot), key=lambda c: c.momentum, reverse=True)[:top_n]
