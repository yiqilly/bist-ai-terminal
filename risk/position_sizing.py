# ============================================================
# risk/position_sizing.py — Pozisyon Boyutu v4
# Core Regime de dahil — CHOP/RISK_OFF → sıfır
# ============================================================
from __future__ import annotations
import math
from config import POSITION_SIZING
from data.models import RiskProfile, PositionSize, LiquidityAnalysis, RegimeResult

# Type-only import (circular import önlemi)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from strategy.core.core_regime import CoreRegimeResult


class PositionSizer:
    def __init__(self):
        cfg = POSITION_SIZING
        self._capital       = cfg["total_capital"]
        # Eski key (max_risk_per_trade_pct) ve yeni key (risk_per_trade_pct) uyumlu
        self._max_risk_pct  = cfg.get("risk_per_trade_pct",
                              cfg.get("max_risk_per_trade_pct", 1.2))

    def calculate(
        self,
        symbol: str,
        risk: RiskProfile,
        liquidity: "LiquidityAnalysis | None" = None,
        regime: "RegimeResult | None" = None,
        confidence: float = 50.0,
        core_regime: "CoreRegimeResult | None" = None,
    ) -> PositionSize:
        entry = risk.entry
        stop  = risk.stop
        risk_per_share = max(entry - stop, 0.01)

        base_risk_tl = self._capital * (self._max_risk_pct / 100)

        # Core regime override (CHOP/RISK_OFF → sıfır)
        if core_regime and not core_regime.trade_allowed:
            return self._zero_size(symbol, entry, stop, risk_per_share,
                                    f"İşlem yok ({core_regime.label})")

        # Core regime position factor (AGGRESSIVE → 1.1x)
        core_factor = core_regime.position_factor if core_regime else 1.0

        # Terminal regime cezası
        regime_factor = 1.0
        if regime:
            regime_factor = {"TREND": 1.0, "RANGE": 0.85, "RISK_OFF": 0.5, "VOLATILE": 0.4}.get(
                regime.regime, 0.85)

        # Likidite cezası
        liq_factor = 1.0
        if liquidity:
            if liquidity.execution_quality == "Kötü":  liq_factor = 0.5
            elif liquidity.execution_quality == "Orta": liq_factor = 0.75

        # Confidence
        conf_factor = 1.1 if confidence >= 80 else (0.8 if confidence < 40 else 1.0)

        adjusted = base_risk_tl * regime_factor * liq_factor * conf_factor * core_factor
        lots = max(1, math.floor(adjusted / risk_per_share))
        if liquidity:
            lots = min(lots, liquidity.lot_feasibility)

        total_cost = round(lots * entry, 2)
        total_risk = round(lots * risk_per_share, 2)
        port_risk  = round(total_risk / self._capital * 100, 2)

        note = self._note(regime_factor, liq_factor, conf_factor, core_factor, port_risk)

        return PositionSize(
            symbol=symbol, entry=entry, stop=stop,
            suggested_lots=lots,
            risk_per_share=round(risk_per_share, 2),
            total_risk_tl=total_risk,
            total_cost_tl=total_cost,
            portfolio_risk_pct=port_risk,
            sizing_note=note,
        )

    def _zero_size(self, symbol, entry, stop, rps, note) -> PositionSize:
        return PositionSize(
            symbol=symbol, entry=entry, stop=stop, suggested_lots=0,
            risk_per_share=round(rps,2), total_risk_tl=0.0,
            total_cost_tl=0.0, portfolio_risk_pct=0.0, sizing_note=note,
        )

    def _note(self, reg, liq, conf, core, port_risk) -> str:
        parts = []
        if core > 1.0:           parts.append("✓ Agresif mod — boyut artırıldı")
        if reg < 0.6:            parts.append("Zayıf rejim → boyut azaltıldı")
        if liq < 0.8:            parts.append("Likidite cezası uygulandı")
        if conf < 0.85:          parts.append("Düşük güven → boyut küçültüldü")
        if port_risk > 2.5:      parts.append("⚠ Portföy riski yüksek")
        return " | ".join(parts) if parts else "✓ Uygun boyut"
