# ============================================================
# strategy/regime.py — Market Regime Detection
# ============================================================
from data.models import RegimeResult, SignalCandidate, MarketSnapshot


class RegimeEngine:
    """
    Piyasa rejimini tespit eder.
    Regimes: TREND | RANGE | RISK_OFF | VOLATILE
    """

    def detect(
        self,
        snapshot: MarketSnapshot,
        candidates: list[SignalCandidate],
    ) -> RegimeResult:
        advancing_pct = snapshot.market_strength
        avg_momentum  = self._avg_momentum(candidates)
        avg_score     = self._avg_score(candidates)
        volatility    = self._avg_volatility(candidates)

        regime, label, desc = self._classify(
            advancing_pct, avg_momentum, avg_score, volatility
        )
        return RegimeResult(
            regime=regime,
            label=label,
            strength=advancing_pct,
            advancing_pct=advancing_pct,
            avg_momentum=avg_momentum,
            avg_score=avg_score,
            volatility=volatility,
            description=desc,
        )

    def _classify(
        self,
        adv_pct: float,
        avg_mom: float,
        avg_score: float,
        volatility: float,
    ) -> tuple[str, str, str]:
        if volatility > 3.0 and adv_pct < 40:
            return ("VOLATILE", "⚡ VOLATİL",
                    "Piyasada yüksek volatilite. Pozisyon büyüklüğü küçültülmeli.")
        if adv_pct >= 65 and avg_mom >= 1.5:
            return ("TREND", "🔼 GÜÇLÜ TREND",
                    "Piyasa güçlü yükseliş trendinde. Momentum alımları destekleniyor.")
        if adv_pct >= 55 and avg_mom >= 0.5:
            return ("TREND", "↗ YÜKSELIŞ EĞİLİMİ",
                    "Genel yükseliş eğilimi mevcut. Seçici alım fırsatları var.")
        if adv_pct <= 35 and avg_mom <= -1.0:
            return ("RISK_OFF", "🔽 RİSK KAPALI",
                    "Piyasada risk kapanma var. Dikkatli olunmalı, stop sıkılaştırılmalı.")
        if 40 <= adv_pct <= 60 and abs(avg_mom) < 1.0:
            return ("RANGE", "↔ YATAY PİYASA",
                    "Piyasa yatay seyirde. Breakout sinyalleri daha anlamlı.")
        return ("RANGE", "→ NÖTR",
                "Piyasada net yön yok. Yüksek skorlu sinyallere odaklanın.")

    def _avg_momentum(self, candidates: list[SignalCandidate]) -> float:
        if not candidates:
            return 0.0
        return sum(c.momentum for c in candidates) / len(candidates)

    def _avg_score(self, candidates: list[SignalCandidate]) -> float:
        if not candidates:
            return 0.0
        return sum(c.score for c in candidates) / len(candidates)

    def _avg_volatility(self, candidates: list[SignalCandidate]) -> float:
        if not candidates:
            return 1.0
        atrs = [c.atr / c.price * 100 for c in candidates if c.price > 0]
        return sum(atrs) / len(atrs) if atrs else 1.0

    def regime_multiplier(self, regime: str) -> float:
        """Ranking'de kullanılacak rejim çarpanı"""
        return {"TREND": 1.2, "RANGE": 1.0, "RISK_OFF": 0.7, "VOLATILE": 0.6}.get(regime, 1.0)
