# ============================================================
# risk/risk_engine.py — Risk Hesaplama Motoru
# ============================================================
from config import RISK
from data.models import SignalCandidate, RiskProfile
from strategy.rules import quality_label


class RiskEngine:
    """
    Her sinyal adayı için ATR tabanlı risk profili hesaplar.
    Entry, Stop, Target, Risk%, R/R otomatik üretilir.
    """

    def __init__(
        self,
        portfolio_value: float = 100_000.0,
        risk_per_trade_pct: float | None = None,
    ):
        self._portfolio_value = portfolio_value
        self._risk_pct = risk_per_trade_pct or RISK["default_risk_pct"]

    def calculate(self, candidate: SignalCandidate) -> RiskProfile:
        entry = candidate.price
        atr = candidate.atr if candidate.atr > 0 else entry * 0.01

        stop = round(entry - RISK["atr_stop_multiplier"] * atr, 2)
        target = round(entry + RISK["atr_target_multiplier"] * atr, 2)

        risk_amount = entry - stop
        reward_amount = target - entry

        risk_pct = round((risk_amount / entry) * 100, 2) if entry > 0 else 0.0
        reward_pct = round((reward_amount / entry) * 100, 2) if entry > 0 else 0.0
        rr_ratio = round(reward_amount / risk_amount, 2) if risk_amount > 0 else 0.0

        quality = quality_label(candidate.score)

        return RiskProfile(
            entry=entry,
            stop=stop,
            target=target,
            risk_pct=risk_pct,
            reward_pct=reward_pct,
            rr_ratio=rr_ratio,
            quality=quality,
        )

    def update_portfolio_value(self, value: float) -> None:
        self._portfolio_value = value
