# ============================================================
# strategy/strategy_router.py
# Regime-Switching Strategy Router — v2 (Unified Pipeline)
#
# Market Regime → Doğru Strateji Motoru → RouterSignal
#
# Tek sinyal kaynağı: tüm trade kararları buradan çıkar.
# UnifiedRegimeEngine çıktısını tüketir.
#
# Rejim → Strateji eşlemesi:
#   BULL / WEAK_BULL  → BullBreakoutStrategy
#   RANGE             → RangeSectorRotationStrategy
#   VOLATILE          → VolatilityBreakoutStrategy
#   BEAR / RISK_OFF   → no trade
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Union

from strategy.bull_breakout_strategy      import (
    BullBreakoutStrategy, BullSignal, BullSignalState, STRATEGY_TYPE as BULL_TYPE
)
from strategy.range_sector_rotation_strategy import (
    RangeSectorRotationStrategy, RotationSignal, RotationState,
    STRATEGY_TYPE as RANGE_TYPE
)
from strategy.volatility_breakout_strategy  import (
    VolatilityBreakoutStrategy, VolSignal, VolSignalState, STRATEGY_TYPE as VOL_TYPE
)
from strategy.edge_multi_strategy import (
    EdgeMultiStrategy, EdgeSignal, STRATEGY_TYPE as EDGE_TYPE
)

# Birleşik sinyal tipi
AnySignal = Union[BullSignal, RotationSignal, VolSignal, EdgeSignal]

# Rejim → Strateji tipi eşlemesi
REGIME_STRATEGY_MAP = {
    "BULL":       BULL_TYPE,
    "WEAK_BULL":  BULL_TYPE,
    "RANGE":      RANGE_TYPE,
    "VOLATILE":   VOL_TYPE,
    "EDGE":       EDGE_TYPE,  # Yeni Edge Multi-Strategy Rejimi
    # BEAR / RISK_OFF → no trade (haritada yok)
}


@dataclass
class RouterSignal:
    """
    Strategy Router'dan dışarıya çıkan standart sinyal.
    UI, TradeSignalEngine ve Backtest bu nesneyi kullanır.
    """
    symbol:        str
    regime:        str   = "RANGE"
    strategy_type: str   = ""    # BULL_BREAKOUT | RANGE_REVERSION | VOLATILE_BREAKOUT
    setup_type:    str   = ""    # BREAKOUT | PULLBACK_REBREAK | ...

    # Pozisyon seviyeleri
    entry:         float = 0.0
    stop:          float = 0.0
    target:        float = 0.0
    daily_atr:     float = 0.0

    # Kalite göstergeleri
    sector_str:    float = 0.0
    rs_score:      float = 0.0
    rsi:           float = 50.0
    rr_ratio:      float = 0.0

    # Meta
    is_active:     bool  = False
    detail:        str   = ""
    updated_at:    datetime = field(default_factory=datetime.now)

    @classmethod
    def from_bull(cls, sig: BullSignal, regime: str) -> "RouterSignal":
        rr = (sig.target-sig.entry)/(sig.entry-sig.stop) if sig.entry>sig.stop else 0
        return cls(
            symbol=sig.symbol, regime=regime,
            strategy_type=sig.strategy_type,
            setup_type=sig.setup_type.value,
            entry=sig.entry, stop=sig.stop, target=sig.target,
            daily_atr=sig.daily_atr,
            sector_str=sig.sector_str, rs_score=sig.rs_score,
            rsi=sig.rsi, rr_ratio=rr,
            is_active=sig.is_buy_signal(), detail=sig.detail,
        )

    @classmethod
    def from_range(cls, sig: RotationSignal, regime: str) -> "RouterSignal":
        rr = (sig.target-sig.entry)/(sig.entry-sig.stop) if sig.entry>sig.stop else 0
        return cls(
            symbol=sig.symbol, regime=regime,
            strategy_type=sig.strategy_type,
            setup_type=sig.setup_type.value,
            entry=sig.entry, stop=sig.stop, target=sig.target,
            daily_atr=sig.daily_atr,
            sector_str=sig.sector_str, rs_score=sig.rs_score,
            rsi=sig.rsi, rr_ratio=rr,
            is_active=sig.is_buy_signal(), detail=sig.detail,
        )

    @classmethod
    def from_vol(cls, sig: VolSignal, regime: str) -> "RouterSignal":
        rr = (sig.target-sig.entry)/(sig.entry-sig.stop) if sig.entry>sig.stop else 0
        return cls(
            symbol=sig.symbol, regime=regime,
            strategy_type=sig.strategy_type,
            setup_type=sig.setup_type.value,
            entry=sig.entry, stop=sig.stop, target=sig.target,
            daily_atr=sig.daily_atr,
            sector_str=sig.sector_str, rs_score=sig.rs_score,
            rr_ratio=rr, is_active=sig.is_buy_signal(), detail=sig.detail,
        )

    @classmethod
    def from_edge(cls, sig: EdgeSignal, regime: str) -> "RouterSignal":
        rr = (sig.target-sig.entry)/(sig.entry-sig.stop) if sig.entry>sig.stop else 0
        return cls(
            symbol=sig.symbol, regime=regime,
            strategy_type=sig.strategy_type,
            setup_type=sig.setup_type.value,
            entry=sig.entry, stop=sig.stop, target=sig.target,
            daily_atr=sig.daily_atr,
            sector_str=sig.sector_str, rs_score=sig.rs_score,
            rsi=sig.rsi, rr_ratio=rr,
            is_active=sig.is_buy_signal(), detail=sig.detail,
        )


class StrategyRouter:
    """
    Piyasa rejimine göre doğru strateji motorunu seçer
    ve ortak RouterSignal nesneleri döner.

    v2: Unified Pipeline — tek sinyal kaynağı.
    Tüm RouterSignal'ler dahili olarak izlenir.

    Kullanım:
        router = StrategyRouter()

        # Her bar'da:
        rsig = router.on_bar(sym, bar, regime_str, ctx)
        buys = router.get_active_buys()
    """

    def __init__(self):
        self._bull  = BullBreakoutStrategy()
        self._range = RangeSectorRotationStrategy()
        self._vol   = VolatilityBreakoutStrategy()
        self._edge  = EdgeMultiStrategy()
        self._current_regime = "RANGE"

        # Dahili sinyal izleme — her sembol için son sinyal
        self._all_signals: dict[str, RouterSignal] = {}

    # ── Ana metod ────────────────────────────────────────────
    def on_bar(
        self,
        symbol: str,
        bar,
        regime: str,
        ctx: dict,
    ) -> Optional[RouterSignal]:
        """
        Tek sembol için bir bar işler.
        Aktif strateji motorunu çalıştırır, RouterSignal döner.
        Ayrıca dahili sinyal izlemesini günceller.
        """
        # UnifiedRegime nesnesi geldiyse string'e çevir
        if hasattr(regime, 'regime'):
            regime = regime.regime

        self._current_regime = regime
        strategy_type = REGIME_STRATEGY_MAP.get(regime)

        if strategy_type is None:
            # BEAR / RISK_OFF → trade yok
            return None

        rsig = None

        if strategy_type == BULL_TYPE:
            sig = self._bull.on_bar(symbol, bar, ctx)
            if sig is not None:
                rsig = RouterSignal.from_bull(sig, regime)

        elif strategy_type == RANGE_TYPE:
            sig = self._range.on_bar(symbol, bar, ctx)
            if sig is not None:
                rsig = RouterSignal.from_range(sig, regime)

        elif strategy_type == VOL_TYPE:
            sig = self._vol.on_bar(symbol, bar, ctx)
            if sig is not None:
                rsig = RouterSignal.from_vol(sig, regime)

        elif strategy_type == EDGE_TYPE:
            sig = self._edge.on_bar(symbol, bar, ctx)
            if sig is not None:
                rsig = RouterSignal.from_edge(sig, regime)

        # Dahili sinyal izleme
        if rsig is not None:
            self._all_signals[symbol] = rsig

        return rsig

    # ── Toplu sorgular ───────────────────────────────────────

    def get_all_signals(self) -> dict[str, RouterSignal]:
        """Tüm izlenen sinyalleri döner (sym → RouterSignal)."""
        return dict(self._all_signals)

    def get_active_buys(self) -> list[RouterSignal]:
        """Aktif (is_active=True) BUY sinyallerini döner."""
        return [s for s in self._all_signals.values() if s.is_active]

    def get_setup_signals(self) -> list[RouterSignal]:
        """Setup aşamasındaki sinyaller (entry>0 ama henüz is_active=False)."""
        return [
            s for s in self._all_signals.values()
            if not s.is_active and s.entry > 0
        ]

    def get_watching_signals(self) -> list[RouterSignal]:
        """İzleme aşamasındaki sinyaller (entry=0, henüz setup oluşmamış)."""
        return [
            s for s in self._all_signals.values()
            if not s.is_active and s.entry == 0 and s.strategy_type
        ]

    def get_active_buy_signals(self, regime: str) -> list[RouterSignal]:
        """Mevcut rejime göre aktif BUY sinyallerini getir (eski API uyumu)."""
        if hasattr(regime, 'regime'):
            regime = regime.regime
        st = REGIME_STRATEGY_MAP.get(regime)
        if st == BULL_TYPE:
            return [RouterSignal.from_bull(s, regime)
                    for s in self._bull.get_buy_signals()]
        if st == RANGE_TYPE:
            return [RouterSignal.from_range(s, regime)
                    for s in self._range.get_buy_signals()]
        if st == VOL_TYPE:
            return [RouterSignal.from_vol(s, regime)
                    for s in self._vol.get_buy_signals()]
        if st == EDGE_TYPE:
            return [RouterSignal.from_edge(s, regime)
                    for s in self._edge.get_buy_signals()]
        return []

    def get_active_strategy_type(self, regime: str) -> Optional[str]:
        if hasattr(regime, 'regime'):
            regime = regime.regime
        return REGIME_STRATEGY_MAP.get(regime)

    def reset_day(self):
        """Gün başında tüm strateji motorlarını sıfırla."""
        self._bull.reset_day()
        self._range.reset_day()
        self._vol.reset_day()
        self._edge.reset_day()
        self._all_signals.clear()

    # ── Durum özeti (UI için) ─────────────────────────────────
    def status_summary(self, regime: str) -> dict:
        if hasattr(regime, 'regime'):
            regime = regime.regime
        st = REGIME_STRATEGY_MAP.get(regime, "NO_TRADE")
        bull_buys  = len(self._bull.get_buy_signals())
        range_buys = len(self._range.get_buy_signals())
        vol_buys   = len(self._vol.get_buy_signals())
        edge_buys  = len(self._edge.get_buy_signals())
        return {
            "regime":          regime,
            "active_strategy": st,
            "bull_signals":    bull_buys,
            "range_signals":   range_buys,
            "vol_signals":     vol_buys,
            "edge_signals":    edge_buys,
            "total_signals":   bull_buys + range_buys + vol_buys + edge_buys,
            "trade_allowed":   st is not None,
        }
