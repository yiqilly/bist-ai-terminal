# ============================================================
# risk/risk_dashboard.py
# Risk Dashboard — FAZ 9
#
# Portföy risk metriklerini hesaplar:
#   - open_positions / total_exposure
#   - risk_per_trade
#   - sector_exposure
#   - daily_pnl
#   - max_drawdown_estimate
#   - open_trade_count
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config import POSITION_SIZING


@dataclass
class RiskMetrics:
    total_capital:     float = 100_000.0
    total_exposure:    float = 0.0
    exposure_pct:      float = 0.0       # exposure / capital * 100

    open_count:        int   = 0
    max_open:          int   = 5

    total_pnl_tl:      float = 0.0
    daily_pnl_pct:     float = 0.0

    avg_risk_per_trade: float = 0.0      # ortalama risk TL / sermaye %
    max_drawdown_est:  float  = 0.0      # toplam açık risk % tahmini

    sector_exposure:   dict   = field(default_factory=dict)  # sektör → TL

    # Uyarı seviyeleri
    alert_level:       str   = "normal"   # normal | caution | danger
    messages:          list  = field(default_factory=list)

    @property
    def available_slots(self) -> int:
        return max(0, self.max_open - self.open_count)

    @property
    def is_max_positions(self) -> bool:
        return self.open_count >= self.max_open


class RiskDashboard:
    """
    PositionManager'dan metrikleri hesaplar.
    """

    def __init__(self, capital: float = 100_000.0):
        self._capital = capital

    def compute(self, positions: list, sectors: dict | None = None) -> RiskMetrics:
        """
        positions: list[Position] (position_manager.get_open())
        sectors:   sektör adı → SectorSnapshot (opsiyonel)
        """
        cfg = POSITION_SIZING
        max_open = cfg.get("max_open_positions", 5)
        max_risk_pct = cfg.get("max_portfolio_risk_pct", 10.0)

        open_pos   = [p for p in positions if p.is_open]
        count      = len(open_pos)
        exposure   = sum(p.cost_tl for p in open_pos)
        total_pnl  = sum(p.pnl_tl  for p in open_pos)
        exp_pct    = exposure / self._capital * 100 if self._capital > 0 else 0.0
        daily_pct  = total_pnl / self._capital * 100 if self._capital > 0 else 0.0

        # Ortalama risk per trade
        risks = []
        for p in open_pos:
            if p.entry_price > 0 and p.stop > 0:
                risk_pct = abs(p.entry_price - p.stop) / p.entry_price * 100
                risks.append(risk_pct)
        avg_risk = sum(risks) / len(risks) if risks else 0.0

        # Max drawdown estimate (tüm stoplar tetiklense)
        total_risk_tl = sum(
            abs(p.entry_price - p.stop) * p.lots
            for p in open_pos if p.stop > 0
        )
        mdd_pct = total_risk_tl / self._capital * 100 if self._capital > 0 else 0.0

        # Sektör bazlı exposure
        from data.sector_map import get_sector
        sec_exp: dict[str, float] = {}
        for p in open_pos:
            sec = get_sector(p.symbol)
            sec_exp[sec] = sec_exp.get(sec, 0.0) + p.cost_tl

        # Uyarılar
        msgs = []
        if count >= max_open:
            msgs.append(f"⚠ Maksimum pozisyon sayısına ulaşıldı ({count}/{max_open})")
        if mdd_pct >= max_risk_pct:
            msgs.append(f"🔴 Portföy riski yüksek (%{mdd_pct:.1f})")
        if exp_pct >= 80:
            msgs.append(f"⚠ Sermayenin %{exp_pct:.0f}'ı kullanımda")
        if total_pnl < -self._capital * 0.03:
            msgs.append(f"🔴 Günlük zarar ₺{total_pnl:,.0f}")

        if msgs:
            alert = "danger" if any("🔴" in m for m in msgs) else "caution"
        else:
            alert = "normal"

        return RiskMetrics(
            total_capital      = self._capital,
            total_exposure     = round(exposure, 2),
            exposure_pct       = round(exp_pct, 1),
            open_count         = count,
            max_open           = max_open,
            total_pnl_tl       = round(total_pnl, 2),
            daily_pnl_pct      = round(daily_pct, 2),
            avg_risk_per_trade = round(avg_risk, 2),
            max_drawdown_est   = round(mdd_pct, 2),
            sector_exposure    = {k: round(v, 0) for k, v in sec_exp.items()},
            alert_level        = alert,
            messages           = msgs,
        )
