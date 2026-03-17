# ============================================================
# strategy/core/breakout_rules.py
# Breakout / Pullback / Rebreak tespit mantığı
# Gerçek intraday bar listesi veya mock bar listesi üzerinde çalışır.
# ============================================================
from __future__ import annotations
from datetime import datetime, time
from strategy.core.core_features import MorningBar, CoreSetupFeatures


class BreakoutDetector:
    """
    Sıralı intraday bar listesinden breakout / pullback / rebreak tespiti.

    Pencereler (varsayılan BIST saatleri):
      Morning window  : 10:00 - 10:30
      Breakout window : 10:30 - 10:45
      Pullback window : 10:45 - 11:10
      Rebreak window  : 11:10 - 11:30
    """

    # Saat sınırları — ileride config'e taşınabilir
    T_MORN_START  = time(10, 0)
    T_MORN_END    = time(10, 30)
    T_BO_END      = time(10, 45)
    T_PB_END      = time(11, 10)
    T_RB_END      = time(11, 30)

    # Pullback eşiği: high_1030'a ne kadar yaklaşmalı?
    PULLBACK_THRESHOLD = 0.003   # %0.3

    def detect(
        self,
        bars: list[MorningBar],
        features: CoreSetupFeatures,
    ) -> CoreSetupFeatures:
        """
        Bar listesinden feature'ları doldur.
        features: zaten simge ve tarihi dolu CoreSetupFeatures nesnesi.
        """
        morning = [b for b in bars if self.T_MORN_START <= b.timestamp.time() <= self.T_MORN_END]
        bo_bars = [b for b in bars if self.T_MORN_END < b.timestamp.time() <= self.T_BO_END]
        pb_bars = [b for b in bars if self.T_BO_END   < b.timestamp.time() <= self.T_PB_END]
        rb_bars = [b for b in bars if self.T_PB_END   < b.timestamp.time() <= self.T_RB_END]

        # Sabah penceresi
        if not morning:
            features.compute_derived()
            return features

        features.open_1000 = morning[0].open
        features.close_1030 = morning[-1].close
        features.high_1030  = max(b.high for b in morning)
        features.low_1030   = min(b.low  for b in morning)
        features.vol_morning = sum(b.volume for b in morning)

        ref_high = features.high_1030

        # Breakout (10:30-10:45): herhangi bir close > high_1030
        for b in bo_bars:
            if b.close > ref_high:
                features.breakout_detected = True
                features.breakout_price    = b.close
                features.breakout_time     = b.timestamp
                break

        # Pullback (10:45-11:10): fiyat ref_high'a PULLBACK_THRESHOLD içinde geri çekilmeli
        if features.breakout_detected and pb_bars:
            min_close = min(b.close for b in pb_bars)
            depth = (features.breakout_price - min_close) / features.breakout_price
            if depth >= self.PULLBACK_THRESHOLD:
                features.pullback_detected    = True
                features.pullback_low         = min_close
                features.pullback_depth_pct   = round(depth * 100, 3)

        # Rebreak (11:10-11:30): tekrar ref_high üzerine kapanış
        if features.pullback_detected and rb_bars:
            for b in rb_bars:
                if b.close > ref_high:
                    features.rebreak_detected = True
                    features.rebreak_price    = b.close
                    features.rebreak_time     = b.timestamp
                    break

        features.compute_derived()
        return features
