# ============================================================
# strategy/core/setup_detector.py
# Canlı terminalden (veya mock'tan) tek sembol için
# CoreSetupFeatures üretir. Mock + gerçek veri destekli.
# ============================================================
from __future__ import annotations
import random
import math
from datetime import datetime, date, time, timedelta
from typing import Optional

from strategy.core.core_features import CoreSetupFeatures, MorningBar
from strategy.core.breakout_rules import BreakoutDetector
from data.models import SignalCandidate


class SetupDetector:
    """
    Bir sembol için günlük CoreSetupFeatures üretir.

    İki mod:
      A) detect_from_bars(symbol, bars)  — gerçek intraday bar listesi
      B) detect_from_candidate(cand)     — mevcut SignalCandidate'ten mock türetme
    """

    def __init__(self):
        self._detector = BreakoutDetector()
        self._cache: dict[str, CoreSetupFeatures] = {}

    # ── A) Gerçek Veri ─────────────────────────────────────
    def detect_from_bars(
        self,
        symbol: str,
        bars: list[MorningBar],
        as_of: Optional[date] = None,
    ) -> CoreSetupFeatures:
        """
        Gerçek intraday bar listesinden setup tespit et.
        Matriks IQ bağlandığında bu metod çağrılacak.
        """
        today = as_of or date.today()
        features = CoreSetupFeatures(symbol=symbol, date=today)
        return self._detector.detect(bars, features)

    # ── B) Mock Türetme ─────────────────────────────────────
    def detect_from_candidate(
        self,
        cand: SignalCandidate,
    ) -> CoreSetupFeatures:
        """
        Mevcut SignalCandidate feature'larından tutarlı mock
        CoreSetupFeatures üretir. Gerçek veri olmadığında çalışır.
        Rastgelelik değil, deterministik türetme kullanır.
        """
        key = cand.symbol
        if key in self._cache:
            return self._cache[key]

        feat = self._derive_mock(cand)
        self._cache[key] = feat
        return feat

    def invalidate_cache(self, symbol: Optional[str] = None) -> None:
        """Yeni bar geldiğinde çağrılır."""
        if symbol:
            self._cache.pop(symbol, None)
        else:
            self._cache.clear()

    # ── Mock türetme mantığı ────────────────────────────────
    def _derive_mock(self, c: SignalCandidate) -> CoreSetupFeatures:
        """
        SignalCandidate'in teknik özelliklerinden mantıklı,
        tekrarlanabilir sabah penceresi feature'ları türet.
        """
        # Belirleyici seed: sembol adı + günün tarihi
        seed = hash(c.symbol + str(date.today())) & 0xFFFFFF
        rng  = random.Random(seed)

        # Sabah fiyatları (anlık fiyattan türetilmiş)
        open_1000  = c.price * rng.uniform(0.990, 1.005)
        # Momentum: trend/breakout güçlüyse pozitif, değilse daha düşük
        mom_bias = 0.005 if (c.trend and c.breakout) else 0.001
        close_1030 = open_1000 * (1 + rng.gauss(mom_bias, 0.003))
        high_1030  = max(open_1000, close_1030) * rng.uniform(1.001, 1.006)
        low_1030   = min(open_1000, close_1030) * rng.uniform(0.994, 0.999)
        vol_morning = c.volume * rng.uniform(0.25, 0.40)

        feat = CoreSetupFeatures(
            symbol=c.symbol,
            date=date.today(),
            open_1000=round(open_1000, 2),
            close_1030=round(close_1030, 2),
            high_1030=round(high_1030, 2),
            low_1030=round(low_1030, 2),
            vol_morning=round(vol_morning),
        )

        # Breakout: score>=4 ve trend varsa büyük olasılıkla breakout
        bo_prob = 0.85 if (c.score >= 5 and c.trend and c.breakout) else (
                  0.60 if (c.score >= 3 and c.breakout) else 0.25)
        if rng.random() < bo_prob:
            feat.breakout_detected = True
            feat.breakout_price    = round(high_1030 * rng.uniform(1.001, 1.004), 2)
            feat.breakout_time     = datetime.now().replace(hour=10, minute=37, second=0)

            # Pullback: NORMAL_TREND'de daha sık, volume_confirm ile uyumlu
            pb_prob = 0.80 if c.volume_confirm else 0.45
            if rng.random() < pb_prob:
                depth = rng.uniform(0.003, 0.010)
                feat.pullback_detected  = True
                feat.pullback_low       = round(feat.breakout_price * (1 - depth), 2)
                feat.pullback_depth_pct = round(depth * 100, 3)

                # Rebreak: pullback sonrası teyit
                rb_prob = 0.75 if (c.score >= 5 and c.momentum > 1.0) else 0.45
                if rng.random() < rb_prob:
                    feat.rebreak_detected = True
                    feat.rebreak_price    = round(high_1030 * rng.uniform(1.002, 1.006), 2)
                    feat.rebreak_time     = datetime.now().replace(hour=11, minute=18, second=0)

        feat.compute_derived()
        return feat
