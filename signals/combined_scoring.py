# ============================================================
# signals/combined_scoring.py — Birleşik Skor v4
# Core Edge Score entegre edildi.
# ============================================================
from __future__ import annotations
from data.models import SignalCandidate, RankedSignal, RegimeResult
from signals.ai_ranking  import AIRankingEngine
from signals.confidence  import ConfidenceEngine
from news.sentiment      import SentimentScorer
from news.news_engine    import NewsEngine
from strategy.smart_money import SmartMoneyAnalyzer
from strategy.liquidity   import LiquidityAnalyzer
from risk.position_sizing import PositionSizer
from strategy.regime      import RegimeEngine as RegEng

# Core strateji
from strategy.core.setup_detector import SetupDetector
from strategy.core.core_regime    import CoreRegimeClassifier
from strategy.core.edge_score     import EdgeScoreCalculator


class CombinedScorer:
    """
    Final Combined Score:
      technical + ai + news + flow + liquidity + core_edge + regime_adj
    """

    def __init__(self, news_engine: NewsEngine):
        self._ai        = AIRankingEngine()
        self._sent      = SentimentScorer()
        self._sizer     = PositionSizer()
        self._news      = news_engine
        self._smart     = SmartMoneyAnalyzer()
        self._liq_eng   = LiquidityAnalyzer()
        self._conf_eng  = ConfidenceEngine()
        # Core
        self._setup_det = SetupDetector()
        self._core_reg  = CoreRegimeClassifier()
        self._edge_calc = EdgeScoreCalculator()

    def enrich(
        self,
        signal: RankedSignal,
        regime: RegimeResult | None,
        all_candidates: list[SignalCandidate] | None = None,
    ) -> RankedSignal:
        c = signal.candidate

        # ── Mevcut katmanlar ──────────────────────────────
        sm  = self._smart.analyze(c)
        liq = self._liq_eng.analyze(c)

        all_news   = self._news.get_news()
        news_sent  = self._sent.score_for_symbol(c.symbol, all_news)
        news_bonus = self._sent.news_rank_bonus(news_sent)

        ai_result  = self._ai.score(c, regime, news_sent, all_candidates)
        ai_score   = ai_result["ai_score"]

        conf_obj   = self._conf_eng.calculate(c, news_sent, regime, sm, liq)
        confidence = conf_obj.confidence

        # ── Core Edge (v4) ────────────────────────────────
        core_setup  = self._setup_det.detect_from_candidate(c)
        core_regime = self._core_reg.from_terminal_regime(regime) if regime else (
                      self._core_reg._build("NORMAL_CHOP", ""))
        core_edge   = self._edge_calc.calculate(core_setup, core_regime)

        # ── Combined Score ────────────────────────────────
        tech_norm   = c.score / 6.0 * 6.5          # 0-6.5
        regime_adj  = (RegEng().regime_multiplier(regime.regime) - 1.0) * 2.0 if regime else 0.0
        flow_bonus  = sm.flow_score / 10 * 0.8
        liq_bonus   = liq.liquidity_score / 10 * 0.4
        edge_bonus  = core_edge.combined_contribution  # 0-2

        combined = round(
            tech_norm + news_bonus * 1.5 + regime_adj +
            flow_bonus + liq_bonus + edge_bonus,
            2
        )
        combined = max(0.0, min(combined, 10.0))

        # ── Confidence artırımı ──────────────────────────
        if core_setup.has_full_confirmation:
            confidence = min(confidence + 8.0, 100.0)
        elif core_setup.breakout_detected:
            confidence = min(confidence + 4.0, 100.0)

        # ── Alert hints ───────────────────────────────────
        alerts = self._generate_alerts(c, regime, sm, liq, news_sent, ai_score,
                                        core_setup, core_edge, core_regime)

        pos_size = self._sizer.calculate(
            c.symbol, signal.risk, liq, regime, confidence,
            core_regime=core_regime,
        )

        # ── Signal doldur ─────────────────────────────────
        signal.ai_score        = ai_score
        signal.news_score      = round(news_sent, 3)
        signal.combined_score  = combined
        signal.quality_label   = ai_result["quality_label"]
        signal.confidence      = confidence
        signal.flow_score      = sm.flow_score
        signal.liquidity_score = liq.liquidity_score
        signal.position_size   = pos_size
        signal.smart_money     = sm
        signal.liquidity       = liq
        signal.alerts          = alerts
        signal.core_edge_score  = core_edge.edge_score
        signal.core_setup_type  = core_setup.setup_type
        signal.core_compatible  = (core_setup.setup_type != "None" and core_edge.edge_score >= 4.0)
        signal.core_setup       = core_setup
        signal.core_edge        = core_edge
        return signal

    def _generate_alerts(self, c, regime, sm, liq, news_sent, ai_score,
                          core_setup, core_edge, core_regime) -> list[str]:
        hints = []
        # Mevcut uyarılar
        if c.rsi > 72:              hints.append("⚠ RSI yüksek — takip et")
        if not c.volume_confirm:    hints.append("⚠ Hacim onayı zayıf")
        if news_sent > 0.5:         hints.append("✨ Haber desteği güçlü")
        if news_sent < -0.3:        hints.append("⚠ Negatif haber akışı")
        if liq.execution_quality == "Kötü": hints.append("⚠ Likidite sınırlı — boyut küçült")
        if regime and regime.regime == "RISK_OFF": hints.append("🔴 Piyasa risk-off modunda")
        if regime and regime.regime == "VOLATILE": hints.append("⚡ Yüksek volatilite — dikkat")
        if sm.flow_score >= 7:      hints.append("💰 Akıllı para girişi tespit edildi")
        if not c.breakout:          hints.append("⏳ Breakout teyidi bekleniyor")
        if ai_score >= 8:           hints.append("⭐ Yüksek AI skoru")
        # Core uyarılar (v4)
        if core_setup.setup_type == "PullbackRebreak":
            hints.append("🎯 Core: Pullback + Rebreak teyidi")
        elif core_setup.setup_type == "MorningMomentumBreakout":
            hints.append("📈 Core: Sabah Momentum Breakout")
        if core_edge.edge_score >= 7:
            hints.append(f"🏆 Core Edge güçlü ({core_edge.edge_score:.1f})")
        if core_regime.mode == "AGGRESSIVE":
            hints.append("🟢 Agresif piyasa — bonus aday")
        elif not core_regime.trade_allowed:
            hints.append(f"🚫 Core: {core_regime.label} — işlem önerilmez")
        if core_setup.morning_momentum_pct >= 0.5:
            hints.append(f"☀ Sabah momentumu {core_setup.morning_momentum_pct:.2f}%")
        return hints
