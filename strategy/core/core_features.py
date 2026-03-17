# ============================================================
# strategy/core/core_features.py
# Sabah momentum penceresi feature'ları (10:00-10:30)
# Gerçek intraday bar bağlanınca da çalışacak şekilde tasarlandı.
# ============================================================
from __future__ import annotations
import random
import math
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from typing import Optional


@dataclass
class MorningBar:
    """10:00-10:30 penceresi için tek bir 5dk bar."""
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class CoreSetupFeatures:
    """
    Eski core stratejinin sabah penceresi feature set'i.
    Tek bir sembol / tek bir gün için hesaplanır.
    """
    symbol: str
    date: date

    # -- Sabah penceresi (10:00-10:30) --
    open_1000: float = 0.0          # 10:00 açılış
    close_1030: float = 0.0         # 10:30 kapanış (giriş fiyatı)
    high_1030: float = 0.0          # 10:00-10:30 en yüksek (breakout referansı)
    low_1030: float = 0.0           # 10:00-10:30 en düşük
    range_1030: float = 0.0         # high - low
    vol_morning: float = 0.0        # 10:00-10:30 toplam hacim

    morning_momentum_pct: float = 0.0   # (close_1030 - open_1000) / open_1000 * 100

    # -- Breakout penceresi (10:35-10:45) --
    breakout_detected: bool = False
    breakout_price: float = 0.0         # kırılan high_1030 seviyesi
    breakout_time: Optional[datetime] = None

    # -- Pullback penceresi (10:45-11:10) --
    pullback_detected: bool = False
    pullback_low: float = 0.0
    pullback_depth_pct: float = 0.0     # geri çekilme %

    # -- Rebreak penceresi (11:10-11:30) --
    rebreak_detected: bool = False
    rebreak_price: float = 0.0
    rebreak_time: Optional[datetime] = None

    # -- Türetilmiş --
    setup_type: str = "None"            # "MorningMomentumBreakout" | "PullbackRebreak" | "None"
    setup_quality: float = 0.0          # 0-10

    def compute_derived(self) -> None:
        """Feature'lardan türetilmiş alanları doldur."""
        if self.open_1000 > 0:
            self.morning_momentum_pct = round(
                (self.close_1030 - self.open_1000) / self.open_1000 * 100, 3)
        self.range_1030 = round(self.high_1030 - self.low_1030, 3)

        # Setup sınıflandırması
        if self.rebreak_detected and self.pullback_detected and self.breakout_detected:
            self.setup_type = "PullbackRebreak"
            self.setup_quality = self._quality_score(base=8.5)
        elif self.breakout_detected and self.morning_momentum_pct >= 0.3:
            self.setup_type = "MorningMomentumBreakout"
            self.setup_quality = self._quality_score(base=6.5)
        elif self.breakout_detected:
            self.setup_type = "BreakoutOnly"
            self.setup_quality = self._quality_score(base=4.0)
        else:
            self.setup_type = "None"
            self.setup_quality = 0.0

    def _quality_score(self, base: float) -> float:
        score = base
        # Momentum katkısı
        score += min(self.morning_momentum_pct * 0.5, 1.5)
        # Hacim katkısı (kaba normalize)
        score += min(self.vol_morning / 2_000_000 * 0.5, 0.5)
        # Rebreak teyidi
        if self.rebreak_detected:
            score += 0.5
        return round(min(score, 10.0), 2)

    @property
    def is_active_setup(self) -> bool:
        return self.setup_type != "None"

    @property
    def has_full_confirmation(self) -> bool:
        return self.breakout_detected and self.pullback_detected and self.rebreak_detected
