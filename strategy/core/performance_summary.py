# ============================================================
# strategy/core/performance_summary.py
# Backtest istatistikleri modeli + setup başına win-rate kaydı
# ============================================================
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class CoreBacktestStats:
    """
    Eski backtest çıktısının modele dönüştürülmüş hali.
    Sabit tablo — gerçek backtest yapıldığında güncellenir.
    """
    setup_type: str
    regime_mode: str

    days_traded: int   = 0
    trades: int        = 0
    win_rate: float    = 0.0    # 0-1
    avg_daily_pct: float = 0.0  # günlük ortalama getiri %
    total_return_pct: float = 0.0
    max_dd_pct: float  = 0.0
    avg_trade_pct: float = 0.0
    profit_factor: float = 0.0   # Gross Win / Gross Loss

    @property
    def expectancy(self) -> float:
        """Beklenti (ör. %0.4 per trade)"""
        if self.trades == 0: return 0.0
        return self.avg_trade_pct * self.win_rate - (
            abs(self.avg_trade_pct) * (1 - self.win_rate) * 0.8)

    @property
    def edge_label(self) -> str:
        if self.win_rate >= 0.65 and self.profit_factor >= 1.5:
            return "Güçlü Edge"
        elif self.win_rate >= 0.55 and self.profit_factor >= 1.2:
            return "Orta Edge"
        elif self.win_rate >= 0.45:
            return "Zayıf Edge"
        return "Edge Yok"


# ── Sabit Tarihsel Profil Tablosu ───────────────────────────
# Gerçek backtest yapılana kadar, strateji dokümantasyonuna
# dayalı temsili değerler. Modüle dahil edildi çünkü
# bu değerler scoring'i etkiliyor.
_HISTORICAL_PROFILES: dict[tuple[str, str], CoreBacktestStats] = {
    ("MorningMomentumBreakout", AGGRESSIVE := "AGGRESSIVE"): CoreBacktestStats(
        setup_type="MorningMomentumBreakout", regime_mode="AGGRESSIVE",
        days_traded=80, trades=64,
        win_rate=0.67, avg_daily_pct=0.82,
        total_return_pct=65.6, max_dd_pct=8.2,
        avg_trade_pct=0.95, profit_factor=1.85,
    ),
    ("MorningMomentumBreakout", "NORMAL_TREND"): CoreBacktestStats(
        setup_type="MorningMomentumBreakout", regime_mode="NORMAL_TREND",
        days_traded=110, trades=72,
        win_rate=0.58, avg_daily_pct=0.51,
        total_return_pct=56.1, max_dd_pct=10.4,
        avg_trade_pct=0.72, profit_factor=1.42,
    ),
    ("PullbackRebreak", "AGGRESSIVE"): CoreBacktestStats(
        setup_type="PullbackRebreak", regime_mode="AGGRESSIVE",
        days_traded=80, trades=48,
        win_rate=0.73, avg_daily_pct=1.05,
        total_return_pct=84.0, max_dd_pct=6.8,
        avg_trade_pct=1.10, profit_factor=2.15,
    ),
    ("PullbackRebreak", "NORMAL_TREND"): CoreBacktestStats(
        setup_type="PullbackRebreak", regime_mode="NORMAL_TREND",
        days_traded=110, trades=55,
        win_rate=0.65, avg_daily_pct=0.68,
        total_return_pct=74.8, max_dd_pct=9.1,
        avg_trade_pct=0.88, profit_factor=1.72,
    ),
    ("BreakoutOnly", "AGGRESSIVE"): CoreBacktestStats(
        setup_type="BreakoutOnly", regime_mode="AGGRESSIVE",
        days_traded=80, trades=60,
        win_rate=0.53, avg_daily_pct=0.31,
        total_return_pct=24.8, max_dd_pct=12.5,
        avg_trade_pct=0.55, profit_factor=1.18,
    ),
    ("BreakoutOnly", "NORMAL_TREND"): CoreBacktestStats(
        setup_type="BreakoutOnly", regime_mode="NORMAL_TREND",
        days_traded=110, trades=66,
        win_rate=0.47, avg_daily_pct=0.12,
        total_return_pct=13.2, max_dd_pct=14.8,
        avg_trade_pct=0.40, profit_factor=1.05,
    ),
}


def get_historical_stats(
    setup_type: str,
    regime_mode: str,
) -> Optional[CoreBacktestStats]:
    """Setup + Regime kombinasyonu için tarihsel istatistik döndür."""
    return _HISTORICAL_PROFILES.get((setup_type, regime_mode))


def get_all_profiles() -> list[CoreBacktestStats]:
    return list(_HISTORICAL_PROFILES.values())
