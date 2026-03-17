# ============================================================
# signals/opportunity_scanner.py — Fırsat Tarayıcı v5
# Sektör güç bonusu entegre.
# ============================================================
from __future__ import annotations
from typing import Optional
from data.models import SignalCandidate, RankedSignal, OpportunityCandidate, RegimeResult
from news.news_engine import NewsEngine
from strategy.core.core_regime import AGGRESSIVE, NORMAL_TREND, NORMAL_CHOP, RISK_OFF


class OpportunityScanner:
    def scan(
        self,
        ranked:        list[RankedSignal],
        all_candidates: list[SignalCandidate],
        regime:        RegimeResult | None,
        news_engine:   NewsEngine,
        sectors:       dict | None = None,     # v5: SectorSnapshot dict
        sector_eng     = None,                  # v5: SectorStrengthEngine
    ) -> list[OpportunityCandidate]:
        results = []

        for s in ranked:
            c = s.candidate
            opp_score = self._compute_opp_score(s, regime, c.symbol, sectors, sector_eng)
            reason    = self._build_reason(s, regime, news_engine, c.symbol, sectors, sector_eng)
            action    = self._action(opp_score, s)
            has_news  = news_engine.has_positive_news(c.symbol)

            core_edge = s.core_edge_score
            core_type = s.core_setup_type
            core_ok   = core_type != "None" and core_edge >= 4.0

            results.append(OpportunityCandidate(
                symbol=c.symbol,
                opp_score=round(opp_score, 2),
                quality_label=s.quality_label,
                reason=reason,
                action=action,
                trend=c.trend, breakout=c.breakout,
                has_news_support=has_news,
                combined_score=s.combined_score,
                ai_score=s.ai_score,
                confidence=s.confidence,
                core_edge_score=core_edge,
                core_setup_type=core_type,
                core_compatible=core_ok,
            ))

        # Watchlist adaylar
        symbols_in = {r.symbol for r in results}
        for c in all_candidates:
            if c.symbol in symbols_in: continue
            if c.score >= 2 and c.momentum > 0:
                sec_reason = ""
                if sectors and sector_eng:
                    sec_reason = sector_eng.sector_reason(c.symbol, sectors)
                reason_txt = f"Takip — skor {c.score}, mom {c.momentum:.2f}"
                if sec_reason:
                    reason_txt += f", {sec_reason}"
                results.append(OpportunityCandidate(
                    symbol=c.symbol,
                    opp_score=round(c.score * 0.8, 2),
                    quality_label="Watchlist",
                    reason=reason_txt,
                    action="izle",
                    trend=c.trend, breakout=c.breakout,
                    has_news_support=news_engine.has_positive_news(c.symbol),
                    combined_score=float(c.score),
                    ai_score=0.0, confidence=0.0,
                ))

        results.sort(key=lambda x: x.opp_score, reverse=True)
        return results[:20]

    def _compute_opp_score(self, s, regime, symbol, sectors, sector_eng) -> float:
        base = s.combined_score
        regime_bonus = {
            "TREND": 1.0, "RANGE": 0.0, "RISK_OFF": -2.0, "VOLATILE": -1.5
        }.get(regime.regime if regime else "RANGE", 0.0)
        flow_bonus  = (s.flow_score / 10) * 1.5 if s.flow_score else 0
        liq_bonus   = (s.liquidity_score / 10) * 0.5 if s.liquidity_score else 0
        core_bonus  = (s.core_edge_score / 10) * 1.0

        if s.core_edge and hasattr(s.core_edge, "regime_mode"):
            if s.core_edge.regime_mode == AGGRESSIVE:    core_bonus += 0.5
            elif s.core_edge.regime_mode == NORMAL_CHOP: core_bonus -= 1.0
            elif s.core_edge.regime_mode == RISK_OFF:    core_bonus -= 2.0

        # v5: Sektör bonusu
        sector_bonus = 0.0
        if sectors and sector_eng:
            sector_bonus = sector_eng.fırsat_bonus(symbol, sectors)

        return min(base + regime_bonus + flow_bonus + liq_bonus + core_bonus + sector_bonus, 10.0)

    def _build_reason(self, s, regime, news, symbol, sectors, sector_eng) -> str:
        c = s.candidate
        parts = []
        if c.trend:           parts.append("trend aktif")
        if c.breakout:        parts.append("breakout var")
        if c.volume_confirm:  parts.append("hacim destekli")
        if news.has_positive_news(c.symbol): parts.append("pozitif haber")
        if s.flow_score and s.flow_score >= 6: parts.append("akıllı para girişi")
        if s.core_setup_type == "PullbackRebreak":
            parts.append("pullback+rebreak")
        elif s.core_setup_type == "MorningMomentumBreakout":
            parts.append("sabah setup")
        if regime and regime.regime == "TREND": parts.append("trend piyasa")
        # v5: Sektör katkısı
        if sectors and sector_eng:
            sec_r = sector_eng.sector_reason(symbol, sectors)
            if sec_r: parts.append(sec_r)
        return ", ".join(parts) if parts else "genel takip"

    def _action(self, score: float, s: RankedSignal) -> str:
        threshold = 5.5 if s.core_compatible else 6.0
        if score >= 8.0 and s.confidence >= 70:  return "güçlü aday"
        if score >= threshold:                    return "güçlü aday" if s.candidate.breakout else "izle"
        if score >= 4.0:                          return "izle"
        if score >= 2.5:                          return "erken"
        return "dikkat"
