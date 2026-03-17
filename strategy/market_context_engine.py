# ============================================================
# strategy/market_context_engine.py
# Market Context Engine — FAZ 2
#
# Piyasa rejimini tespit eder ve UI'ye bütünleşik
# market context (bağlam) sağlar.
#
# Regime türleri:
#   BULL       — güçlü yükseliş trendi
#   WEAK_BULL  — yükseliş eğilimi ama zayıf
#   RANGE      — yatay piyasa
#   WEAK_BEAR  — zayıflama / düşüş başlangıcı
#   BEAR       — güçlü düşüş trendi
#   RISK_OFF   — risk kapanma (belirgin düşüş + volatilite)
#   VOLATILE   — yüksek volatilite / belirsizlik
#
# Metrikler:
#   - market_strength (advancing/declining ratio)
#   - breadth (ad_ratio, net advancing)
#   - momentum (ortalama price momentum)
#   - volatility (ortalama ATR%)
#   - volume bias (up_volume / down_volume)
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from data.models import SignalCandidate, MarketSnapshot


@dataclass
class MarketContext:
    """Tam piyasa bağlamı."""
    regime:       str    = "RANGE"    # BULL | WEAK_BULL | RANGE | WEAK_BEAR | BEAR | RISK_OFF | VOLATILE
    label:        str    = "→ NÖTR"
    description:  str    = ""
    color:        str    = "#94a3b8"  # UI rengi

    # Breadth
    advancing:    int    = 0
    declining:    int    = 0
    unchanged:    int    = 0
    ad_ratio:     float  = 1.0        # advancing / max(declining, 1)
    net_adv:      int    = 0          # advancing - declining
    breadth_pct:  float  = 50.0       # advancing / total * 100

    # Momentum & Volatility
    avg_momentum: float  = 0.0
    avg_score:    float  = 0.0
    volatility:   float  = 1.0        # ortalama ATR%

    # Volume bias
    up_volume:    float  = 0.0
    down_volume:  float  = 0.0
    vol_bias:     float  = 1.0        # up_volume / max(down_volume, 1)

    # Genel güç
    market_strength: float = 50.0
    strength_label:  str   = "NÖTR"

    # Ticaret rehberi
    trade_allowed:   bool  = True
    position_size_adj: float = 1.0    # pozisyon büyüklüğü çarpanı
    alert_level:     str   = "normal" # normal | caution | danger

    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def is_bullish(self) -> bool:
        return self.regime in ("BULL", "WEAK_BULL")

    @property
    def is_bearish(self) -> bool:
        return self.regime in ("BEAR", "WEAK_BEAR", "RISK_OFF")

    @property
    def breadth_label(self) -> str:
        if self.breadth_pct >= 70: return "Geniş Yükseliş"
        if self.breadth_pct >= 55: return "Çoğunluk Yükseliyor"
        if self.breadth_pct >= 45: return "Karma"
        if self.breadth_pct >= 30: return "Çoğunluk Düşüyor"
        return "Geniş Düşüş"


class MarketContextEngine:
    """
    Piyasa bağlamını hesaplar.
    RegimeEngine'in genişletilmiş versiyonu.
    """

    def compute(
        self,
        snapshot: MarketSnapshot,
        candidates: list[SignalCandidate],
    ) -> MarketContext:
        if not snapshot.ticks:
            return MarketContext()

        # ── Breadth ──────────────────────────────────────────
        adv = snapshot.advancing
        dec = snapshot.declining
        unc = snapshot.unchanged
        total = adv + dec + unc or 1
        breadth_pct = adv / total * 100
        ad_ratio    = adv / max(dec, 1)
        net_adv     = adv - dec

        # ── Momentum ─────────────────────────────────────────
        moms  = [c.momentum for c in candidates] if candidates else [0.0]
        avg_mom = sum(moms) / len(moms) if moms else 0.0

        # ── Volatility (ortalama ATR%) ────────────────────────
        atrs = [c.atr / c.price * 100 for c in candidates if c.price > 0]
        avg_vol = sum(atrs) / len(atrs) if atrs else 1.0

        # ── Volume Bias ───────────────────────────────────────
        up_vol   = sum(c.volume for c in candidates if c.momentum > 0)
        down_vol = sum(c.volume for c in candidates if c.momentum < 0)
        vol_bias = up_vol / max(down_vol, 1)

        # ── Avg Score ─────────────────────────────────────────
        scores   = [c.score for c in candidates] if candidates else [0]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # ── Regime Sınıflandırma ──────────────────────────────
        regime, label, desc, color = self._classify(
            breadth_pct, avg_mom, avg_vol, ad_ratio, vol_bias
        )

        # ── Güç Etiketi ───────────────────────────────────────
        ms = snapshot.market_strength
        if ms >= 70:   sl = "GÜÇLÜ BOĞA"
        elif ms >= 55: sl = "YÜKSELİŞ"
        elif ms >= 45: sl = "NÖTR"
        elif ms >= 30: sl = "DÜŞÜŞ"
        else:          sl = "GÜÇLÜ AYI"

        # ── Ticaret Rehberi ───────────────────────────────────
        trade_allowed, ps_adj, alert = self._trade_guide(regime, avg_vol)

        return MarketContext(
            regime=regime, label=label, description=desc, color=color,
            advancing=adv, declining=dec, unchanged=unc,
            ad_ratio=round(ad_ratio, 2), net_adv=net_adv,
            breadth_pct=round(breadth_pct, 1),
            avg_momentum=round(avg_mom, 2),
            avg_score=round(avg_score, 2),
            volatility=round(avg_vol, 2),
            up_volume=up_vol, down_volume=down_vol,
            vol_bias=round(vol_bias, 2),
            market_strength=round(ms, 1),
            strength_label=sl,
            trade_allowed=trade_allowed,
            position_size_adj=ps_adj,
            alert_level=alert,
            updated_at=datetime.now(),
        )

    def _classify(
        self,
        breadth: float,
        mom: float,
        vol: float,
        ad_ratio: float,
        vol_bias: float,
    ) -> tuple[str, str, str, str]:
        # Volatil piyasa önce kontrol et
        if vol > 3.5 and breadth < 40:
            return ("VOLATILE", "⚡ VOLATİL",
                    "Yüksek volatilite + düşüş. Pozisyon büyüklüğü ciddi şekilde küçültülmeli.",
                    "#f59e0b")

        # Risk-off
        if breadth <= 30 and mom <= -1.5:
            return ("RISK_OFF", "🔴 RİSK KAPALI",
                    "Piyasada belirgin satış baskısı. Yeni pozisyon önerilmez.",
                    "#ef4444")

        # Güçlü düşüş
        if breadth <= 38 and mom <= -0.8:
            return ("BEAR", "🔽 AYI PİYASASI",
                    "Piyasa genel düşüş trendinde. Sadece çok güçlü setuplar değerlendir.",
                    "#f87171")

        # Zayıflayan
        if breadth <= 45 and mom < 0:
            return ("WEAK_BEAR", "↘ ZAYIFLAMA",
                    "Piyasa zayıflıyor. Pozisyon boyutlarını küçült, stop'ları sık.",
                    "#fb923c")

        # Güçlü yükseliş
        if breadth >= 65 and mom >= 1.5 and vol_bias >= 1.5:
            return ("BULL", "🚀 GÜÇLÜ BOĞA",
                    "Piyasa güçlü yükseliş trendinde. Momentum alımları destekleniyor.",
                    "#4ade80")

        # Yükseliş eğilimi
        if breadth >= 55 and mom >= 0.5:
            return ("WEAK_BULL", "↗ YÜKSELİŞ EĞİLİMİ",
                    "Genel yükseliş eğilimi var. Seçici alım fırsatları değerlendirilebilir.",
                    "#86efac")

        # Yatay
        return ("RANGE", "↔ YATAY PİYASA",
                "Piyasa yatay seyirde. Kırılım sinyallerine odaklanın.",
                "#94a3b8")

    def _trade_guide(
        self, regime: str, volatility: float
    ) -> tuple[bool, float, str]:
        """(trade_allowed, position_size_adj, alert_level)"""
        guides = {
            "BULL":      (True,  1.2, "normal"),
            "WEAK_BULL": (True,  1.0, "normal"),
            "RANGE":     (True,  0.8, "normal"),
            "WEAK_BEAR": (True,  0.6, "caution"),
            "BEAR":      (True,  0.4, "caution"),
            "RISK_OFF":  (False, 0.0, "danger"),
            "VOLATILE":  (True,  0.3, "danger"),
        }
        base = guides.get(regime, (True, 1.0, "normal"))
        # Ekstra volatilite cezası
        if volatility > 3.0:
            adj = base[1] * 0.7
        else:
            adj = base[1]
        return (base[0], round(adj, 2), base[2])

    # ── Eski API uyumluluğu (RegimeEngine yerine kullanılabilir) ──

    def detect(
        self,
        snapshot: MarketSnapshot,
        candidates: list[SignalCandidate],
    ):
        """RegimeEngine.detect() ile API uyumlu wrapper."""
        ctx = self.compute(snapshot, candidates)
        from data.models import RegimeResult
        return RegimeResult(
            regime       = ctx.regime,
            label        = ctx.label,
            strength     = ctx.market_strength,
            advancing_pct= ctx.breadth_pct,
            avg_momentum = ctx.avg_momentum,
            avg_score    = ctx.avg_score,
            volatility   = ctx.volatility,
            description  = ctx.description,
        )

    def regime_multiplier(self, regime: str) -> float:
        m = {"BULL": 1.3, "WEAK_BULL": 1.1, "RANGE": 0.9,
             "WEAK_BEAR": 0.7, "BEAR": 0.5, "RISK_OFF": 0.3, "VOLATILE": 0.5}
        return m.get(regime, 1.0)
