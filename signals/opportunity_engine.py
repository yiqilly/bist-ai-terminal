# ============================================================
# signals/opportunity_engine.py
# Opportunity Engine — FAZ 5
#
# Scanner değil — yüksek kalite setup ayıkçısı.
# Az sayıda ama çok kaliteli fırsat üretir.
#
# Setup türleri:
#   BREAKOUT           — direnç kırılımı + hacim
#   PULLBACK_REBREAK   — çekilme + destek rebreak
#   SECTOR_LEADER      — güçlü sektörde öne çıkan
#   MOMENTUM_SURGE     — güçlü momentum + RS+
#
# Filtreler (hepsi birden sağlanmalı):
#   trend = True
#   breakout = True
#   volume_confirmation = True
#   sector_strength >= 55
#   market_strength >= 50
#   RS > 0
#   combined_score >= 5.0
#   liquidity_score >= 5
#   risk_reward >= 1.8
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from data.models import RankedSignal, SignalCandidate, MarketSnapshot


@dataclass
class Opportunity:
    symbol:         str
    setup_type:     str    = "UNKNOWN"    # BREAKOUT | PULLBACK_REBREAK | SECTOR_LEADER | MOMENTUM_SURGE
    opp_score:      float  = 0.0          # 0-10
    confidence:     float  = 0.0          # 0-100
    quality_label:  str    = "B"          # A+ | A | B
    action:         str    = "izle"       # güçlü aday | izle | erken
    reason:         str    = ""

    # Fiyat seviyeleri
    entry:          float  = 0.0
    stop:           float  = 0.0
    target:         float  = 0.0
    rr_ratio:       float  = 0.0

    # Filtre detayları
    trend:          bool   = False
    breakout:       bool   = False
    volume_ok:      bool   = False
    rs_positive:    bool   = False
    sector_ok:      bool   = False
    market_ok:      bool   = False

    # Sektör
    sector_name:    str    = "—"
    sector_strength: float = 0.0
    rs_vs_index:    float  = 0.0

    # Scores
    combined_score: float  = 0.0
    flow_score:     float  = 0.0

    @property
    def filter_count(self) -> int:
        """Kaç filtre geçildi."""
        return sum([self.trend, self.breakout, self.volume_ok,
                    self.rs_positive, self.sector_ok, self.market_ok])

    @property
    def color(self) -> str:
        colors = {"A+": "#4ade80", "A": "#86efac", "B": "#fbbf24"}
        return colors.get(self.quality_label, "#94a3b8")


class OpportunityEngine:
    """
    Scanner'ın ürettiği ranked sinyallerden yüksek kalite
    fırsatları ayıklar.
    """

    # Minimum eşikler
    MIN_SECTOR_STRENGTH = 55.0
    MIN_MARKET_STRENGTH = 50.0
    MIN_RR_RATIO        = 1.8
    MIN_COMBINED        = 5.0
    MIN_FLOW            = 4.0

    def scan(
        self,
        ranked:       list[RankedSignal],
        snapshot:     MarketSnapshot,
        sectors:      dict,              # sektör adı → SectorSnapshot
        rs_results:   dict,              # symbol → RSResult
        market_ctx,                      # MarketContext
        max_results:  int = 10,
    ) -> list[Opportunity]:
        """
        Döndürür: kaliteye göre sıralı Opportunity listesi (max_results adet).
        """
        opportunities = []

        for rsig in ranked:
            opp = self._evaluate(rsig, snapshot, sectors, rs_results, market_ctx)
            if opp is not None:
                opportunities.append(opp)

        # Skora göre sırala
        opportunities.sort(key=lambda o: o.opp_score, reverse=True)
        return opportunities[:max_results]

    def _evaluate(
        self,
        rsig:       RankedSignal,
        snapshot:   MarketSnapshot,
        sectors:    dict,
        rs_results: dict,
        market_ctx,
    ) -> Optional[Opportunity]:
        c    = rsig.candidate
        risk = rsig.risk

        # ── Sektör bilgisi ────────────────────────────────────
        from data.sector_map import get_sector
        sec_name = get_sector(c.symbol)
        sec_ss   = sectors.get(sec_name)
        sec_str  = sec_ss.strength if sec_ss else 0.0

        # ── RS bilgisi ────────────────────────────────────────
        rs = rs_results.get(c.symbol)
        rs_val = rs.rs_vs_index if rs else 0.0

        # ── Market strength ───────────────────────────────────
        mkt_str = snapshot.market_strength if snapshot else 50.0

        # ── Filtreler ─────────────────────────────────────────
        f_trend   = c.trend
        f_breakout= c.breakout
        f_volume  = c.volume_confirm
        f_rs      = rs_val > 0
        f_sector  = sec_str >= self.MIN_SECTOR_STRENGTH
        f_market  = mkt_str >= self.MIN_MARKET_STRENGTH
        f_rr      = risk.rr_ratio >= self.MIN_RR_RATIO
        f_score   = rsig.combined_score >= self.MIN_COMBINED
        f_flow    = (rsig.flow_score or 0) >= self.MIN_FLOW

        n_filters = sum([f_trend, f_breakout, f_volume, f_rs,
                         f_sector, f_market, f_rr, f_score, f_flow])

        # En az 5 filtre geçmeli
        if n_filters < 5:
            return None

        # ── Setup türü ────────────────────────────────────────
        setup_type = self._detect_setup(c, rsig, sec_str, rs_val)

        # ── Opportunity score (0-10) ──────────────────────────
        base  = rsig.combined_score * 0.5           # 0-5
        bonus = 0.0
        if f_breakout:  bonus += 1.0
        if f_rs:        bonus += 0.8
        if f_sector:    bonus += 0.7
        if f_flow:      bonus += 0.5
        if f_volume:    bonus += 0.5
        if n_filters >= 8: bonus += 0.5             # full confirmation bonus
        opp_score = round(min(10.0, base + bonus), 2)

        # ── Kalite ───────────────────────────────────────────
        if n_filters >= 8 and opp_score >= 7.5: ql = "A+"
        elif n_filters >= 6 and opp_score >= 6: ql = "A"
        else:                                    ql = "B"

        # ── Aksiyon önerisi ───────────────────────────────────
        if ql == "A+" and f_breakout and f_rs:
            action = "güçlü aday"
        elif n_filters >= 6:
            action = "izle"
        else:
            action = "erken"

        # ── Sebep metni ───────────────────────────────────────
        reason = self._build_reason(
            c, setup_type, f_breakout, f_rs, f_sector,
            f_volume, sec_name, sec_str, rs_val, rsig
        )

        return Opportunity(
            symbol        = c.symbol,
            setup_type    = setup_type,
            opp_score     = opp_score,
            confidence    = rsig.confidence,
            quality_label = ql,
            action        = action,
            reason        = reason,
            entry         = risk.entry,
            stop          = risk.stop,
            target        = risk.target,
            rr_ratio      = risk.rr_ratio,
            trend         = f_trend,
            breakout      = f_breakout,
            volume_ok     = f_volume,
            rs_positive   = f_rs,
            sector_ok     = f_sector,
            market_ok     = f_market,
            sector_name   = sec_name,
            sector_strength = sec_str,
            rs_vs_index   = rs_val,
            combined_score = rsig.combined_score,
            flow_score    = rsig.flow_score or 0.0,
        )

    def _detect_setup(
        self,
        c: SignalCandidate,
        rsig: RankedSignal,
        sec_str: float,
        rs_val: float,
    ) -> str:
        # Core setup tipini kullan (varsa)
        if hasattr(rsig, 'core_setup_type') and rsig.core_setup_type not in ("None", None, ""):
            st = rsig.core_setup_type
            if "Pullback" in st or "Rebreak" in st:
                return "PULLBACK_REBREAK"
            if "Breakout" in st or "Momentum" in st:
                return "BREAKOUT"

        # Kural bazlı
        if c.breakout and c.volume_confirm and c.trend:
            if sec_str >= 65 and rs_val > 0.5:
                return "SECTOR_LEADER"
            return "BREAKOUT"
        if c.trend and c.momentum > 2.0 and rs_val > 0:
            return "MOMENTUM_SURGE"
        if c.trend and c.breakout:
            return "PULLBACK_REBREAK"
        return "BREAKOUT"

    def _build_reason(
        self, c, setup_type, f_breakout, f_rs, f_sector,
        f_volume, sec_name, sec_str, rs_val, rsig
    ) -> str:
        parts = []
        setup_labels = {
            "BREAKOUT":        "Kırılım",
            "PULLBACK_REBREAK":"Çekilme+Rebreak",
            "SECTOR_LEADER":   "Sektör Lideri",
            "MOMENTUM_SURGE":  "Momentum Artışı",
        }
        parts.append(setup_labels.get(setup_type, setup_type))
        if f_breakout:  parts.append("kırılım")
        if f_rs:        parts.append(f"RS+{rs_val:.1f}")
        if f_sector:    parts.append(f"{sec_name}({sec_str:.0f})")
        if f_volume:    parts.append("hacim onayı")
        if c.rsi > 55:  parts.append(f"RSI={c.rsi:.0f}")
        if rsig.flow_score and rsig.flow_score >= 6:
            parts.append("akıllı para")
        return " | ".join(parts[:5])
