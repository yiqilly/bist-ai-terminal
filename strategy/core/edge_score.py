# ============================================================
# strategy/core/edge_score.py
# Backtest performansından "Core Edge Score" türetir (0-10).
# Hem terminal içinde hem offline kullanılır.
# ============================================================
from __future__ import annotations
from dataclasses import dataclass
from strategy.core.core_features import CoreSetupFeatures
from strategy.core.core_regime   import CoreRegimeResult, AGGRESSIVE, NORMAL_TREND, NORMAL_CHOP, RISK_OFF
from strategy.core.performance_summary import get_historical_stats, CoreBacktestStats


@dataclass
class CoreEdgeScore:
    symbol: str
    edge_score: float           # 0-10
    setup_type: str
    regime_mode: str
    win_rate: float             # tarihsel
    expectancy: float           # tarihsel beklenti %
    profit_factor: float
    edge_label: str             # "Güçlü Edge" / ...
    setup_bonus: float          # setup kalitesinden gelen ek puan
    regime_bonus: float         # regime'den gelen ek/çıkarılan puan
    combined_contribution: float  # combined score'a katkı (0-2 arası)
    note: str = ""

    @property
    def is_valid(self) -> bool:
        return self.edge_score > 0 and self.setup_type != "None"


class EdgeScoreCalculator:
    """
    CoreSetupFeatures + CoreRegimeResult → CoreEdgeScore

    Formül:
      base      = tarihsel win_rate * 10
      setup_q   = setup_quality katkısı (0-2)
      regime_b  = AGGRESSIVE +1.5 / NORMAL_TREND +0.5 / diğer 0
      momentum_b = morning_momentum katkısı (0-0.5)
      confirm_b  = full confirmation bonus (0-1)

      edge_score = clamp(base + setup_q + regime_b + momentum_b + confirm_b, 0, 10)
    """

    def calculate(
        self,
        features: CoreSetupFeatures,
        core_regime: CoreRegimeResult,
    ) -> CoreEdgeScore:

        symbol = features.symbol
        setup  = features.setup_type

        # Trade allowed değilse skor sıfır
        if not core_regime.trade_allowed or setup == "None":
            return self._zero_score(symbol, setup, core_regime.mode)

        # Tarihsel istatistik
        stats = get_historical_stats(setup, core_regime.mode)
        if stats is None:
            # Bilinmeyen kombinasyon — düşük varsayılan
            stats = CoreBacktestStats(
                setup_type=setup, regime_mode=core_regime.mode,
                win_rate=0.48, avg_trade_pct=0.3,
                profit_factor=1.05, trades=20,
            )

        # Base (tarihsel win_rate → 0-10)
        base = stats.win_rate * 10

        # Setup quality katkısı (0-2)
        setup_q = features.setup_quality / 10 * 2

        # Regime bonusu
        regime_b = {AGGRESSIVE: 1.5, NORMAL_TREND: 0.5}.get(core_regime.mode, 0.0)

        # Sabah momentum katkısı (0-0.5)
        mom_b = min(features.morning_momentum_pct * 0.15, 0.5)

        # Full confirmation bonusu
        confirm_b = 1.0 if features.has_full_confirmation else 0.0

        edge = round(min(base + setup_q + regime_b + mom_b + confirm_b, 10.0), 2)

        # combined_score katkısı (0-2)
        contrib = round(edge / 10 * 2, 3)

        return CoreEdgeScore(
            symbol=symbol,
            edge_score=edge,
            setup_type=setup,
            regime_mode=core_regime.mode,
            win_rate=stats.win_rate,
            expectancy=round(stats.expectancy, 3),
            profit_factor=stats.profit_factor,
            edge_label=stats.edge_label,
            setup_bonus=round(setup_q + mom_b + confirm_b, 3),
            regime_bonus=regime_b,
            combined_contribution=contrib,
            note=self._note(features, core_regime, stats),
        )

    def _zero_score(self, symbol, setup, mode) -> CoreEdgeScore:
        return CoreEdgeScore(
            symbol=symbol, edge_score=0.0,
            setup_type=setup, regime_mode=mode,
            win_rate=0.0, expectancy=0.0, profit_factor=0.0,
            edge_label="—", setup_bonus=0.0, regime_bonus=0.0,
            combined_contribution=0.0,
            note=f"Trade allowed değil ({mode})" if mode in (NORMAL_CHOP, RISK_OFF)
                 else "Setup tespit edilmedi",
        )

    def _note(
        self,
        features: CoreSetupFeatures,
        regime: CoreRegimeResult,
        stats: CoreBacktestStats,
    ) -> str:
        parts = []
        if features.morning_momentum_pct >= 0.5:
            parts.append(f"Sabah momentumu güçlü (%{features.morning_momentum_pct:.2f})")
        if features.breakout_detected:
            parts.append("breakout onaylı")
        if features.rebreak_detected:
            parts.append("rebreak teyidi var")
        if regime.mode == AGGRESSIVE:
            parts.append("agresif piyasa — daha fazla aday")
        if stats.win_rate >= 0.65:
            parts.append(f"tarihsel WR={stats.win_rate:.0%}")
        return ", ".join(parts) if parts else "temel setup"
