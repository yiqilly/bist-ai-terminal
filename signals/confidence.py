# ============================================================
# signals/confidence.py — Confidence Score (0-100)
# ============================================================
from data.models import (
    SignalCandidate, RegimeResult,
    SmartMoneyAnalysis, LiquidityAnalysis, ConfidenceScore
)


class ConfidenceEngine:
    """
    7 bileşenden 0-100 arası güven skoru üretir.
    Her bileşen bağımsız ve şeffaf.
    """

    WEIGHTS = {
        "tech":       0.25,
        "news":       0.12,
        "regime":     0.13,
        "breakout":   0.15,
        "volume":     0.12,
        "liquidity":  0.12,
        "flow":       0.11,
    }

    def calculate(
        self,
        candidate: SignalCandidate,
        news_sentiment: float,
        regime: RegimeResult | None,
        smart_money: SmartMoneyAnalysis | None,
        liquidity: LiquidityAnalysis | None,
    ) -> ConfidenceScore:
        w = self.WEIGHTS

        # Teknik (0-1)
        tech = min(candidate.score / 6.0, 1.0)

        # Haber (0-1)
        news = (news_sentiment + 1) / 2

        # Regime (0-1)
        if regime:
            reg = {"TREND": 0.9, "RANGE": 0.6, "RISK_OFF": 0.3, "VOLATILE": 0.2}.get(regime.regime, 0.5)
        else:
            reg = 0.5

        # Breakout (0-1)
        bo = 1.0 if (candidate.breakout and candidate.trend) else (0.5 if candidate.breakout else 0.1)

        # Hacim (0-1)
        vol = min(candidate.volume / 4_000_000, 1.0)

        # Likidite (0-1)
        liq = liquidity.liquidity_score / 10 if liquidity else 0.5

        # Flow (0-1)
        flow = smart_money.flow_score / 10 if smart_money else 0.5

        total = (tech * w["tech"] + news * w["news"] + reg * w["regime"] +
                 bo * w["breakout"] + vol * w["volume"] + liq * w["liquidity"] +
                 flow * w["flow"])

        confidence = round(total / sum(w.values()) * 100, 1)

        return ConfidenceScore(
            symbol=candidate.symbol,
            confidence=min(confidence, 100.0),
            tech_contrib=round(tech * w["tech"] * 100 / sum(w.values()), 1),
            news_contrib=round(news * w["news"] * 100 / sum(w.values()), 1),
            regime_contrib=round(reg  * w["regime"] * 100 / sum(w.values()), 1),
            breakout_contrib=round(bo * w["breakout"] * 100 / sum(w.values()), 1),
            volume_contrib=round(vol  * w["volume"] * 100 / sum(w.values()), 1),
            liquidity_contrib=round(liq * w["liquidity"] * 100 / sum(w.values()), 1),
            flow_contrib=round(flow * w["flow"] * 100 / sum(w.values()), 1),
        )
