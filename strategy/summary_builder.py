# ============================================================
# strategy/summary_builder.py — Teknik Özet v4
# Core strateji katkısı dahil edildi.
# ============================================================
from __future__ import annotations
from data.models import SignalCandidate, RegimeResult, SmartMoneyAnalysis, LiquidityAnalysis

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from strategy.core.core_features import CoreSetupFeatures
    from strategy.core.edge_score    import CoreEdgeScore


class TechnicalSummaryBuilder:
    def build(
        self,
        candidate: SignalCandidate,
        regime: RegimeResult | None = None,
        smart_money: SmartMoneyAnalysis | None = None,
        liquidity: LiquidityAnalysis | None = None,
        news_sentiment: float = 0.0,
        core_setup: "CoreSetupFeatures | None" = None,
        core_edge:  "CoreEdgeScore | None"    = None,
    ) -> str:
        c = candidate
        parts = []

        # Trend + EMA
        if c.trend and c.ema9 > c.ema21:
            parts.append("Trend pozitif ve EMA yapısı destekli")
        elif not c.trend:
            parts.append("Trend zayıf veya yön belirsiz")

        # Momentum
        if c.momentum > 2.0:    parts.append("momentum güçlü")
        elif c.momentum > 0.5:  parts.append("momentum orta")
        elif c.momentum < -1.0: parts.append("momentum negatif")

        # Breakout
        if c.breakout:
            parts.append(f"breakout onayı {'(güçlü)' if c.trend else '(zayıf teyit)'}")
        else:
            parts.append("breakout henüz oluşmamış")

        parts.append("hacim destekli" if c.volume_confirm else "hacim onayı eksik")

        # RSI
        rsi = c.rsi
        if 60 <= rsi <= 68:    rsi_txt = f"RSI uygun bölgede ({rsi:.0f})"
        elif rsi > 72:         rsi_txt = f"RSI aşırı alım ({rsi:.0f}) — takip et"
        elif rsi > 68:         rsi_txt = f"RSI üst sınıra yakın ({rsi:.0f})"
        else:                  rsi_txt = f"RSI nötr ({rsi:.0f})"
        parts.append(rsi_txt)

        base = ", ".join(parts) + "."

        # Ek katmanlar
        addons = []
        if news_sentiment > 0.4:
            addons.append("Pozitif haber akışı sinyali güçlendiriyor.")
        elif news_sentiment < -0.3:
            addons.append("Negatif haber akışı risk oluşturuyor.")

        if smart_money and smart_money.flow_score >= 6:
            addons.append(f"{smart_money.label}.")
        elif smart_money and smart_money.flow_score < 3:
            addons.append("Akıllı para girişi zayıf.")

        if liquidity:
            if liquidity.execution_quality == "İyi":
                addons.append("Likidite yeterli.")
            elif liquidity.execution_quality == "Kötü":
                addons.append("Likidite sınırlı, pozisyon boyutunu küçült.")

        if regime:
            m = {
                "TREND":    f"Piyasa {regime.label} rejiminde — sinyal destekleniyor.",
                "RISK_OFF": f"Piyasa {regime.label} modunda — stop sıkılaştır.",
                "VOLATILE": "Yüksek volatilite — boyut azalt.",
                "RANGE":    f"Yatay piyasa — breakout teyidi kritik.",
            }
            if t := m.get(regime.regime):
                addons.append(t)

        # Core strateji katkısı (v4)
        if core_setup and core_edge:
            if core_setup.setup_type == "PullbackRebreak":
                addons.append(
                    f"Sabah momentum güçlü (%{core_setup.morning_momentum_pct:.2f}), "
                    f"breakout sonrası yeniden teyit var. "
                    f"Core strateji ile uyumlu yapı nedeniyle edge puanı yükseliyor."
                )
            elif core_setup.setup_type == "MorningMomentumBreakout":
                addons.append(
                    f"Sabah breakout tespit edildi (%{core_setup.morning_momentum_pct:.2f} momentum). "
                    f"Core edge {core_edge.edge_score:.1f}/10 — {core_edge.edge_label}."
                )
            elif core_setup.setup_type == "None":
                addons.append("Core setup henüz oluşmamış — sabah penceresi takipte.")

        # Risk
        score = c.score
        if score >= 5 and c.trend and c.breakout and c.volume_confirm:
            verdict = "Risk seviyesi düşük-orta."
        elif score >= 4:
            verdict = "Risk seviyesi orta."
        else:
            verdict = "Risk seviyesi yüksek — ihtiyatlı yaklaşın."

        return base + " " + " ".join(addons) + " " + verdict
