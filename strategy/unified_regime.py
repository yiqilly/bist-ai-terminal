# ============================================================
# strategy/unified_regime.py — Unified Regime Engine
#
# Tek kaynak: MarketContextEngine + RegimeEngine + CoreRegime
# birleştirildi.
#
# 6 rejim:
#   BULL, WEAK_BULL, RANGE, VOLATILE, BEAR, RISK_OFF
#
# Çıktı:
#   UnifiedRegime — tüm strateji, scoring ve UI katmanları
#   bu nesneyi kullanır.
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from data.models import MarketSnapshot, SignalCandidate


# ── Rejim sabitleri ──────────────────────────────────────────

BULL      = "BULL"
WEAK_BULL = "WEAK_BULL"
RANGE     = "RANGE"
VOLATILE  = "VOLATILE"
BEAR      = "BEAR"
RISK_OFF  = "RISK_OFF"
EDGE      = "EDGE"

ALL_REGIMES = [BULL, WEAK_BULL, RANGE, VOLATILE, BEAR, RISK_OFF, EDGE]


# ── Rejim sonuç nesnesi ─────────────────────────────────────

@dataclass
class UnifiedRegime:
    """Tüm sisteme dağıtılan tek rejim nesnesi."""
    regime:          str             # BULL / WEAK_BULL / RANGE / VOLATILE / BEAR / RISK_OFF
    label:           str             # Gösterim metni (emoji + Türkçe)
    strength:        float           # 0-100 — piyasa gücü
    color:           str             # UI rengi

    # Metriklere erişim
    breadth_pct:     float = 0.0     # yükselen oranı %
    avg_momentum:    float = 0.0     # ortalama momentum %
    avg_score:       float = 0.0     # ortalama sinyal skoru
    volatility:      float = 0.0     # ortalama range/ATR

    # Trade kararları
    trade_allowed:   bool  = True    # BEAR / RISK_OFF → False
    position_factor: float = 1.0     # pozisyon boyut çarpanı
    pullback_required: bool = False  # WEAK_BULL → pullback beklenir

    # Rehber metinler
    description:     str   = ""
    guidance:        str   = ""

    # ── MarketContextPanel uyumluluk alanları ────────────
    market_strength: float = 0.0     # = strength (alias)
    strength_label:  str   = ""
    advancing:       int   = 0
    declining:       int   = 0
    unchanged:       int   = 0
    breadth_label:   str   = ""
    vol_bias:        float = 0.5
    ad_ratio:        float = 1.0
    position_size_adj: float = 1.0

    # Zaman damgası
    updated_at:      datetime = field(default_factory=datetime.now)

    # ── Uyumluluk yardımcıları ──────────────────────────────

    def to_regime_result(self):
        """Eski RegimeResult API'si ile uyumluluk."""
        from data.models import RegimeResult
        return RegimeResult(
            regime        = self.regime,
            label         = self.label,
            strength      = self.strength,
            advancing_pct = self.breadth_pct,
            avg_momentum  = self.avg_momentum,
            avg_score     = self.avg_score,
            volatility    = self.volatility,
            description   = self.description,
        )

    def to_core_regime(self):
        """CoreRegimeResult uyumluluğu (edge scoring için)."""
        from strategy.core.core_regime import CoreRegimeResult
        from strategy.core.core_regime import (
            AGGRESSIVE, NORMAL_TREND, NORMAL_CHOP, RISK_OFF as CR_RISK_OFF,
        )
        mapping = {
            BULL:      (AGGRESSIVE,   True,  1.1, False),
            WEAK_BULL: (NORMAL_TREND, True,  1.0, True),
            RANGE:     (NORMAL_CHOP,  False, 0.0, False),
            VOLATILE:  (CR_RISK_OFF,  False, 0.0, False),
            BEAR:      (NORMAL_CHOP,  False, 0.0, False),
            RISK_OFF:  (CR_RISK_OFF,  False, 0.0, False),
            EDGE:      (AGGRESSIVE,   True,  1.1, False),
        }
        mode, allowed, factor, pb = mapping.get(
            self.regime, (NORMAL_CHOP, False, 0.0, False)
        )
        return CoreRegimeResult(
            mode=mode,
            label=self.label,
            trade_allowed=allowed,
            position_factor=factor,
            pullback_required=pb,
            description=self.description,
            source_regime=self.regime,
        )


# ── Rejim sınıflandırma eşikleri ────────────────────────────

_THRESHOLDS = {
    "bull_breadth":       65.0,   # BULL: yükselen oran ≥ %65
    "bull_momentum":       0.8,   # BULL: ort momentum ≥ %0.8
    "weak_bull_breadth":  55.0,
    "weak_bull_momentum":  0.3,
    "bear_breadth":       35.0,   # BEAR: yükselen oran ≤ %35
    "bear_momentum":      -0.5,
    "risk_off_breadth":   25.0,
    "risk_off_momentum":  -1.0,
    "volatile_range":      1.8,   # VOLATILE: ort range/ATR ≥ 1.8
}


# ── Unified Regime Engine ────────────────────────────────────

class UnifiedRegimeEngine:
    """
    Piyasa snapshot + adaylar → tek UnifiedRegime nesnesi.

    Üç eski engine'i birleştirir:
      - MarketContextEngine   (breadth, momentum, volatility, volume)
      - RegimeEngine          (advancing_pct, momentum, score)
      - CoreRegimeClassifier  (AGGRESSIVE / NORMAL_TREND / CHOP / RISK_OFF)
    """

    def __init__(self):
        self._prev_regime: str = RANGE
        self._regime_hold_count: int = 0
        self._MIN_HOLD_TICKS = 3       # rejim flip koruması

    def compute(
        self,
        snapshot: MarketSnapshot,
        candidates: list[SignalCandidate],
    ) -> UnifiedRegime:
        """Her tick'te çağrılır. Piyasa rejimini sınıflandırır."""
        # ── 1. Breadth (yükselen/düşen) ─────────────────────
        total = snapshot.advancing + snapshot.declining + snapshot.unchanged
        if total == 0:
            return self._build(RANGE, breadth=50.0, momentum=0.0,
                               score=0.0, volatility=0.0)

        breadth_pct = snapshot.advancing / total * 100

        # ── Ortalama momentum ve skor ─────────────────────
        avg_mom = 0.0
        avg_sc = 0.0
        if candidates:
            # Tip kontrolü ve filtreleme (lint yardımı)
            momenta = [float(c.momentum) for c in candidates if hasattr(c, 'momentum') and c.momentum != 0]
            scores  = [float(c.score) for c in candidates if hasattr(c, 'score')]
            if momenta: avg_mom = sum(momenta) / len(momenta)
            if scores:  avg_sc  = sum(scores)  / len(scores)

        # ── 3. Volatilite (ortalama price range / fiyat) ─────
        ranges = []
        for sym, bar in snapshot.bars.items():
            if bar.high > 0 and bar.low > 0 and bar.close > 0:
                r = float((bar.high - bar.low) / bar.close * 100)
                ranges.append(r)
        avg_range = sum(ranges) / len(ranges) if ranges else 0.0

        # ── 4. Volume bias (hacim yükselen tarafta mı?) ──────
        vol_up = 0.0
        vol_dn = 0.0
        for c in candidates:
            c_vol = float(getattr(c, 'volume', 0.0))
            if getattr(c, 'momentum', 0.0) > 0:
                vol_up += c_vol
            else:
                vol_dn += c_vol
        vol_total = vol_up + vol_dn
        vol_bias = float(vol_up / vol_total) if vol_total > 0 else 0.5

        # ── 5. Rejim sınıflandırma ───────────────────────────
        t = _THRESHOLDS

        # --- EDGE STRATEJİSİ OTOMATİK GEÇİŞ (RS & Momentum Bazlı) ---
        # Eskiden sadece 10:00-10:15 arasıydı, şimdi gün boyu RS ve Momentum güçlüyse aktif.
        is_edge_worthy = (breadth_pct > 60 and avg_mom > 0.5) or (avg_sc > 7.0)

        if is_edge_worthy:
            raw_regime = EDGE
        elif avg_range >= t["volatile_range"] and breadth_pct < 45:
            raw_regime = VOLATILE
        elif (breadth_pct >= t["bull_breadth"] and
              avg_mom >= t["bull_momentum"]):
            raw_regime = BULL
        elif (breadth_pct >= t["weak_bull_breadth"] and
              avg_mom >= t["weak_bull_momentum"]):
            raw_regime = WEAK_BULL
        elif (breadth_pct <= t["risk_off_breadth"] and
              avg_mom <= t["risk_off_momentum"]):
            raw_regime = RISK_OFF
        elif (breadth_pct <= t["bear_breadth"] and
              avg_mom <= t["bear_momentum"]):
            raw_regime = BEAR
        else:
            raw_regime = RANGE

        # ── 6. Rejim stabilizasyonu (flip koruması) ──────────
        if raw_regime != self._prev_regime:
            self._regime_hold_count += 1
            if self._regime_hold_count < self._MIN_HOLD_TICKS:
                raw_regime = self._prev_regime   # henüz geçiş yapma
            else:
                self._regime_hold_count = 0
                self._prev_regime = raw_regime
        else:
            self._regime_hold_count = 0

        return self._build(
            raw_regime,
            breadth=breadth_pct,
            momentum=avg_mom,
            score=avg_sc,
            volatility=avg_range,
            vol_bias=vol_bias,
            snap_adv=snapshot.advancing,
            snap_dec=snapshot.declining,
            snap_unch=snapshot.unchanged,
        )

    # ── Builder ──────────────────────────────────────────────

    def _build(
        self,
        regime: str,
        breadth: float,
        momentum: float,
        score: float,
        volatility: float,
        vol_bias: float = 0.5,
        snap_adv: int = 0,
        snap_dec: int = 0,
        snap_unch: int = 0,
    ) -> UnifiedRegime:
        cfg = _REGIME_CFG[regime]

        # Piyasa gücü hesabı (0-100)
        strength = self._calc_strength(breadth, momentum, vol_bias)

        # Strength label
        if strength >= 70:
            str_label = "Güçlü"
        elif strength >= 50:
            str_label = "Normal"
        elif strength >= 30:
            str_label = "Zayıf"
        else:
            str_label = "Çok Zayıf"

        # Breadth label
        if breadth >= 65:
            br_label = "Geniş Katılım"
        elif breadth >= 50:
            br_label = "Dengeli"
        elif breadth >= 35:
            br_label = "Darılan"
        else:
            br_label = "Zayıf Katılım"

        # A/D ratio
        ad_ratio = snap_adv / snap_dec if snap_dec > 0 else (2.0 if snap_adv > 0 else 1.0)

        return UnifiedRegime(
            regime          = regime,
            label           = str(cfg["label"]),
            strength        = float(round(strength, 1)),
            color           = str(cfg["color"]),
            breadth_pct     = float(round(breadth, 1)),
            avg_momentum    = float(round(momentum, 3)),
            avg_score       = float(round(score, 2)),
            volatility      = float(round(volatility, 3)),
            trade_allowed   = bool(cfg["trade_allowed"]),
            position_factor = float(cfg["position_factor"]),
            pullback_required = bool(cfg["pullback_required"]),
            description     = str(cfg["description"]),
            guidance        = str(cfg["guidance"]),
            # MarketContextPanel uyumluluk
            market_strength = float(round(strength, 1)),
            strength_label  = str_label,
            advancing       = snap_adv,
            declining       = snap_dec,
            unchanged       = snap_unch,
            breadth_label   = br_label,
            vol_bias        = float(round(vol_bias, 2)),
            ad_ratio        = float(round(ad_ratio, 2)),
            position_size_adj = float(cfg["position_factor"]),
        )

    def _calc_strength(
        self, breadth: float, momentum: float, vol_bias: float,
    ) -> float:
        """Piyasa gücü 0-100 — breadth, momentum, vol_bias birleşimi."""
        b_score = min(breadth, 100.0)                            # 0-100
        m_score = min(max((momentum + 3) / 6 * 100, 0), 100)    # -3..+3 → 0-100
        v_score = vol_bias * 100                                  # 0-100
        return b_score * 0.50 + m_score * 0.30 + v_score * 0.20


# ── Rejim konfigürasyonu ─────────────────────────────────────

_REGIME_CFG = {
    BULL: {
        "label":            "🟢 BULL",
        "color":            "#22c55e",
        "trade_allowed":    True,
        "position_factor":  1.1,
        "pullback_required": False,
        "description":      "Güçlü yükseliş — geniş katılım, güçlü momentum.",
        "guidance":         "Breakout stratejisi aktif. Tam pozisyon boyutu.",
    },
    WEAK_BULL: {
        "label":            "🔵 WEAK BULL",
        "color":            "#3b82f6",
        "trade_allowed":    True,
        "position_factor":  0.85,
        "pullback_required": True,
        "description":      "Zayıf yükseliş — pullback teyidi gerekli.",
        "guidance":         "Pullback sonrası breakout bekle. Boyut azaltıldı.",
    },
    RANGE: {
        "label":            "🟡 RANGE",
        "color":            "#eab308",
        "trade_allowed":    True,
        "position_factor":  0.7,
        "pullback_required": False,
        "description":      "Yatay piyasa — sektör rotasyonu aktif.",
        "guidance":         "Sektör liderini seç. Dar stop, hızlı çıkış.",
    },
    VOLATILE: {
        "label":            "🟠 VOLATILE",
        "color":            "#f97316",
        "trade_allowed":    True,
        "position_factor":  0.5,
        "pullback_required": False,
        "description":      "Yüksek volatilite — küçük pozisyon, geniş stop.",
        "guidance":         "ATR filtresi sıkı. Sadece güçlü breakout.",
    },
    BEAR: {
        "label":            "🔴 BEAR",
        "color":            "#ef4444",
        "trade_allowed":    False,
        "position_factor":  0.0,
        "pullback_required": False,
        "description":      "Düşüş trendi — işlem yapma.",
        "guidance":         "Piyasa zayıf. Pozisyon açmaktan kaçın.",
    },
    RISK_OFF: {
        "label":            "⛔ RISK OFF",
        "color":            "#dc2626",
        "trade_allowed":    False,
        "position_factor":  0.0,
        "pullback_required": False,
        "description":      "Risk kaçışı — piyasadan uzak dur.",
        "guidance":         "Tüm sinyaller devre dışı.",
    },
    EDGE: {
        "label":            "🦈 SHARK (EDGE)",
        "color":            "#a855f7", # Mor (Edge/Shark rengi)
        "trade_allowed":    True,
        "position_factor":  1.1,
        "pullback_required": False,
        "description":      "Sabah açılış seansı — Edge Stratejisi devrede.",
        "guidance":         "Yüksek hacim ve RS liderlerini takip et.",
    },
}
