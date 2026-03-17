# ============================================================
# strategy/router_adapter.py
# RouterSignal → TradeSignal adaptörü — v2 (Unified Pipeline)
#
# StrategyRouter'dan gelen sinyalleri TradeSignal formatına
# dönüştürür. BUY / SETUP / WATCHLIST üç aşama desteklenir.
# ============================================================
from __future__ import annotations
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from strategy.strategy_router import RouterSignal
from signals.trade_signal_engine import TradeSignal, SignalState
from data.sector_map import get_sector

if TYPE_CHECKING:
    from strategy.position_sizer import PositionSizer


def router_to_trade_signal(
    rsig: RouterSignal,
    sizer: Optional["PositionSizer"] = None,
    force_state: Optional[SignalState] = None,
) -> TradeSignal:
    """RouterSignal → TradeSignal dönüşümü."""

    if force_state is not None:
        state = force_state
    elif rsig.is_active:
        state = SignalState.BUY_SIGNAL
    elif rsig.entry > 0:
        state = SignalState.SETUP
    else:
        state = SignalState.WATCHLIST

    strategy_labels = {
        'BULL_BREAKOUT':         f"🟢 BULL | {rsig.setup_type}",
        'RANGE_SECTOR_ROTATION': f"🔵 RANGE | {rsig.setup_type}",
        'VOLATILE_BREAKOUT':     f"🟠 VOL | {rsig.setup_type}",
    }
    reason = strategy_labels.get(rsig.strategy_type, rsig.strategy_type)
    if rsig.detail:
        reason += f" | {rsig.detail[:40]}"

    score = rsig.sector_str * 0.4 + rsig.rs_score * 30 * 0.3
    if score >= 60:    quality = "A+"
    elif score >= 45:  quality = "A"
    elif score >= 30:  quality = "B"
    else:              quality = "Watchlist"

    # Lot hesabı — sizer varsa gerçek, yoksa basit hesap
    lots = 0
    if sizer and rsig.entry > 0 and rsig.stop > 0:
        sizing = sizer.calc(
            entry=rsig.entry, stop=rsig.stop, target=rsig.target)
        lots = sizing.lots if sizing.allowed else 0
        if not sizing.allowed and quality != "Watchlist":
            reason += f" | ✗ {sizing.reject_reason[:30]}"
    elif rsig.entry > 0 and rsig.stop > 0:
        lots = _calc_lots(rsig)

    # UI Criteria generation for Watchlist/Setup panels
    criteria_met = []
    criteria_miss = ["Onay bekleniyor", "Hacim", "Kırılım"]
    if score >= 30:
        criteria_met.append(f"Güçlü RS ({rsig.rs_score:+.2f})")
    if rsig.sector_str >= 50:
        criteria_met.append("Sektör İvmesi")
    if rsig.entry > 0:
        criteria_met.append("Setup Oluştu")
        criteria_miss = ["Hacim teyidi"]
    if rsig.is_active:
        criteria_met = ["Trend", "Breakout", "Hacim", "Risk Onayı"]
        criteria_miss = []


    sig = TradeSignal(
        symbol          = rsig.symbol,
        state           = state,
        entry           = rsig.entry,
        stop            = rsig.stop,
        target          = rsig.target,
        rr_ratio        = rsig.rr_ratio,
        combined_score  = score,
        confidence      = min(100.0, rsig.sector_str),
        quality_label   = quality,
        sector_strength = rsig.sector_str,
        sector_name     = get_sector(rsig.symbol),
        rs_score        = rsig.rs_score,
        reason          = reason,
        buy_issued_at   = rsig.updated_at if rsig.is_active else None,
        criteria_met    = criteria_met,
        criteria_miss   = criteria_miss,
    )

    sig.setup_type    = rsig.setup_type       # type: ignore[attr-defined]
    sig.regime        = rsig.regime           # type: ignore[attr-defined]
    sig.strategy_type = rsig.strategy_type    # type: ignore[attr-defined]
    sig.lots          = lots

    return sig


def _calc_lots(rsig: RouterSignal, capital: float = 100_000.0,
               risk_pct: float = 0.012) -> int:
    if rsig.entry <= 0 or rsig.stop <= 0: return 0
    risk = rsig.entry - rsig.stop
    if risk <= 0: return 0
    return max(1, min(int(capital * risk_pct / risk), 9999))


def filter_router_buys(
    router_signals: dict[str, RouterSignal],
    sizer: Optional["PositionSizer"] = None,
) -> list[TradeSignal]:
    """Aktif BUY sinyallerini TradeSignal listesine dönüştür."""
    result = []
    for sym, rsig in router_signals.items():
        if rsig and rsig.is_active:
            result.append(router_to_trade_signal(rsig, sizer))
    result.sort(key=lambda s: (s.quality_label, -s.rr_ratio))
    return result


def filter_router_setups(
    router_signals: dict[str, RouterSignal],
    sizer: Optional["PositionSizer"] = None,
) -> list[TradeSignal]:
    """Setup aşamasındaki sinyalleri TradeSignal listesine dönüştür."""
    result = []
    for sym, rsig in router_signals.items():
        if rsig and not rsig.is_active and rsig.entry > 0:
            result.append(router_to_trade_signal(
                rsig, sizer, force_state=SignalState.SETUP))
    result.sort(key=lambda s: -s.combined_score)
    return result


def filter_router_watchlist(
    router_signals: dict[str, RouterSignal],
) -> list[TradeSignal]:
    """İzleme aşamasındaki sinyalleri TradeSignal listesine dönüştür."""
    result = []
    for sym, rsig in router_signals.items():
        if rsig and not rsig.is_active:
            result.append(router_to_trade_signal(
                rsig, force_state=SignalState.WATCHLIST))
    result.sort(key=lambda s: -s.combined_score)
    return result
