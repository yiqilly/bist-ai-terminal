# ============================================================
# strategy/core/core_regime.py
# Eski backtest'teki AGGRESSIVE / NORMAL_TREND / NORMAL_CHOP / RISK_OFF
# sınıflandırması — mevcut RegimeResult ile uyumlu bir köprü kurar.
# ============================================================
from __future__ import annotations
from dataclasses import dataclass
from data.models import RegimeResult


# ── Core Regime Tipleri ─────────────────────────────────────
AGGRESSIVE   = "AGGRESSIVE"
NORMAL_TREND = "NORMAL_TREND"
NORMAL_CHOP  = "NORMAL_CHOP"
RISK_OFF     = "RISK_OFF"


@dataclass
class CoreRegimeResult:
    """
    Backtest modelinden türeyen 4-durum core regime.
    """
    mode: str                   # AGGRESSIVE | NORMAL_TREND | NORMAL_CHOP | RISK_OFF
    label: str                  # Gösterim metni
    trade_allowed: bool         # CHOP ve RISK_OFF = False
    position_factor: float      # Boyut çarpanı (0.0 – 1.2)
    pullback_required: bool     # NORMAL_TREND'de pullback şart
    description: str = ""

    # Unified field (mevcut RegimeResult ile eşleşme)
    source_regime: str = ""     # terminaldeki karşılık (TREND/RANGE/RISK_OFF/VOLATILE)


# ── Birleşik Sonuç ──────────────────────────────────────────
@dataclass
class UnifiedRegimeResult:
    """
    Core regime + terminal regime = tek nesne.
    Scoring ve position sizing bu nesneyi kullanır.
    """
    core:     CoreRegimeResult
    terminal: RegimeResult
    blended_strength: float     # 0-100


# ── Sınıflandırma Motoru ────────────────────────────────────
class CoreRegimeClassifier:
    """
    Piyasa metriklerinden core regime üretir.
    Girdi: terminal RegimeResult (mevcut regime engine'den gelen).
    Ayrıca raw metriklerle de çağrılabilir.
    """

    # Eşikler (eski backtest parametrelerine yakın)
    THRESHOLDS = {
        "breadth_pos_aggressive": 0.65,     # advancing / total
        "breadth_pos_trend":      0.50,
        "avg_momentum_aggressive": 1.5,     # ortalama momentum %
        "avg_momentum_trend":      0.5,
        "breadth_vol_aggressive":  0.55,    # hacim artı oranı
        "avg_range_risk_off":      2.5,     # ortalama range %
    }

    def from_terminal_regime(self, regime: RegimeResult) -> CoreRegimeResult:
        """
        Mevcut terminaldeki RegimeResult'tan core mode türet.
        Bu yöntem, gerçek intraday metrik olmadığında kullanılır.
        """
        # Terminal → Core dönüşüm tablosu
        mapping = {
            "TREND":    self._map_trend(regime),
            "RANGE":    NORMAL_CHOP,
            "RISK_OFF": RISK_OFF,
            "VOLATILE": RISK_OFF,
        }
        mode = mapping.get(regime.regime, NORMAL_CHOP)
        return self._build(mode, regime.regime)

    def from_metrics(
        self,
        breadth_pos: float,
        avg_momentum: float,
        breadth_vol_up: float,
        avg_range_pct: float,
    ) -> CoreRegimeResult:
        """
        Ham metriklerden direct sınıflandırma.
        Gerçek bağlantı olduğunda kullanılır.
        """
        t = self.THRESHOLDS

        if avg_range_pct >= t["avg_range_risk_off"]:
            mode = RISK_OFF
        elif (breadth_pos >= t["breadth_pos_aggressive"] and
              avg_momentum >= t["avg_momentum_aggressive"] and
              breadth_vol_up >= t["breadth_vol_aggressive"]):
            mode = AGGRESSIVE
        elif (breadth_pos >= t["breadth_pos_trend"] and
              avg_momentum >= t["avg_momentum_trend"]):
            mode = NORMAL_TREND
        else:
            mode = NORMAL_CHOP

        return self._build(mode, "")

    def unify(
        self,
        core: CoreRegimeResult,
        terminal: RegimeResult,
    ) -> UnifiedRegimeResult:
        """İkisini birleştir."""
        blended = (core.position_factor * 50 +
                   (terminal.strength / 100) * 50)
        return UnifiedRegimeResult(
            core=core,
            terminal=terminal,
            blended_strength=round(blended, 1),
        )

    # ── İç yardımcılar ─────────────────────────────────────
    def _map_trend(self, regime: RegimeResult) -> str:
        """TREND rejimini güce göre AGGRESSIVE veya NORMAL_TREND'e ayır."""
        if regime.strength >= 70 and regime.avg_momentum >= 1.5:
            return AGGRESSIVE
        return NORMAL_TREND

    def _build(self, mode: str, source: str) -> CoreRegimeResult:
        cfg = {
            AGGRESSIVE:   ("🟢 AGRESİF",  True,  1.1, False, "Geniş katılım, güçlü momentum. Fazladan aday."),
            NORMAL_TREND: ("🔵 TREND",     True,  1.0, True,  "Trend aktif, pullback teyidi bekleniyor."),
            NORMAL_CHOP:  ("🟡 CHOP",      False, 0.0, False, "Yatay piyasa — işlem yapma."),
            RISK_OFF:     ("🔴 RİSK-OFF",  False, 0.0, False, "Piyasa risk kaçışı — işlem yapma."),
        }
        label, allowed, factor, pb_req, desc = cfg[mode]
        return CoreRegimeResult(
            mode=mode, label=label, trade_allowed=allowed,
            position_factor=factor, pullback_required=pb_req,
            description=desc, source_regime=source,
        )
