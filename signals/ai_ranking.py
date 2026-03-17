# ============================================================
# signals/ai_ranking.py — AI / Weighted Ranking Engine
# ============================================================
from config import AI_WEIGHTS
from data.models import SignalCandidate, RegimeResult
from strategy.regime import RegimeEngine


class AIRankingEngine:
    """
    Explainable weighted ranking.
    Her feature normalize edilip ağırlıklı toplanır.
    Gelecekte ML modeli bu sınıfa entegre edilebilir.
    """

    def score(
        self,
        candidate: SignalCandidate,
        regime: RegimeResult | None,
        news_sentiment: float = 0.0,
        all_candidates: list[SignalCandidate] | None = None,
    ) -> dict:
        w = AI_WEIGHTS
        features = {}

        # 1. Breakout strength (0-1)
        features["breakout_strength"] = 1.0 if candidate.breakout else 0.0

        # 2. Volume surge (0-1)
        features["volume_surge"] = min(candidate.volume / 3_000_000, 1.0)

        # 3. RSI zone quality (0-1) — ideal zone: 60-68
        rsi = candidate.rsi
        if 60 <= rsi <= 68:
            features["rsi_zone"] = 1.0
        elif 55 <= rsi < 60 or 68 < rsi <= 72:
            features["rsi_zone"] = 0.6
        elif 45 <= rsi < 55:
            features["rsi_zone"] = 0.3
        else:
            features["rsi_zone"] = 0.1

        # 4. EMA structure (0-1)
        if candidate.ema9 > 0 and candidate.ema21 > 0:
            ema_diff = (candidate.ema9 - candidate.ema21) / candidate.ema21
            features["ema_structure"] = min(max(ema_diff * 50 + 0.5, 0), 1.0)
        else:
            features["ema_structure"] = 0.5

        # 5. Momentum (0-1)
        mom = candidate.momentum
        features["momentum"] = min(max((mom + 5) / 10, 0), 1.0)

        # 6. Regime fit (0-1)
        if regime:
            rm = RegimeEngine().regime_multiplier(regime.regime)
            features["regime_fit"] = min(rm / 1.2, 1.0)
        else:
            features["regime_fit"] = 0.5

        # 7. News sentiment (0-1)
        features["news_sentiment"] = min(max((news_sentiment + 1) / 2, 0), 1.0)

        # 8. Relative strength vs peers (0-1)
        if all_candidates:
            scores = [c.score for c in all_candidates]
            max_s = max(scores) if scores else 6
            features["relative_strength"] = candidate.score / max_s if max_s > 0 else 0.5
        else:
            features["relative_strength"] = candidate.score / 6

        # Ağırlıklı toplam
        ai_score = sum(features[k] * w.get(k, 0) for k in features)
        # 0-10 skalaya çevir
        ai_score_10 = round(ai_score * 10 / sum(w.values()), 2)

        confidence = round(ai_score / sum(w.values()) * 100, 1)

        quality_label = self._quality_label(ai_score_10)

        return {
            "ai_score": ai_score_10,
            "confidence": confidence,
            "quality_label": quality_label,
            "features": features,
        }

    def _quality_label(self, score: float) -> str:
        if score >= 7.5:
            return "Elite"
        elif score >= 5.5:
            return "Strong"
        elif score >= 3.5:
            return "Watchlist"
        return "Weak"
