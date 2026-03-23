# ============================================================
# strategy/edge_multi.py — BIST v2 Edge Strateji Motoru
#
# CORE_EDGE  → %80 sermaye, 1-30 gün tutma
#   · RS > 1.15 (endeksi geçiyor)
#   · Konsolidasyon (ATR dar, < %5)
#   · Hacim sivri ucu (vol > 1.5x ortalama)
#   · Durak: 2×ATR | Hedef: 5×ATR
#
# SWING_EDGE → %20 sermaye, gün içi vur-kaç
#   · RSI3 < 15 (aşırı satım zıplaması)
#   · VEYA güçlü Gap-Up + RS > 1.05
#   · Durak: 1×ATR | Hedef: 1.5×ATR
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from config import (
    CORE_RS_THRESHOLD, CORE_CONSOLIDATION_THRESHOLD, CORE_VOL_THRESHOLD,
    CORE_STOP_ATR, CORE_TARGET_ATR,
    SWING_RSI3_THRESHOLD, SWING_GAP_RS_THRESHOLD,
    SWING_STOP_ATR, SWING_TARGET_ATR,
    CORE_WEIGHT, SWING_WEIGHT,
)


class SetupType(str, Enum):
    NONE       = "NONE"
    CORE_EDGE  = "CORE_EDGE"
    SWING_EDGE = "SWING_EDGE"


@dataclass
class EdgeSignal:
    symbol:      str
    setup_type:  SetupType = SetupType.NONE
    is_signal:   bool      = False

    # Fiyat seviyeleri
    entry:      float = 0.0
    stop:       float = 0.0
    target:     float = 0.0
    daily_atr:  float = 0.0
    rr_ratio:   float = 0.0

    # Meta
    rs_score:   float = 0.0
    rsi3:       float = 50.0
    sector_str: float = 0.0
    detail:     str   = ""

    # Pozisyon ağırlığı (sermayenin kaçı)
    weight:     float = 0.0

    _date: Optional[date] = field(default=None, repr=False)

    def reset(self):
        self.is_signal  = False
        self.setup_type = SetupType.NONE
        self.entry = self.stop = self.target = 0.0
        self.rr_ratio = 0.0
        self.weight = 0.0
        self.detail = ""


class EdgeMultiStrategy:
    """
    CORE_EDGE + SWING_EDGE strateji motoru.

    Her 5 dakikalık barda on_bar() çağrılır.
    Sinyal üretince EdgeSignal.is_signal = True döner.
    """

    def __init__(self):
        self._signals: dict[str, EdgeSignal] = {}

    def on_bar(self, symbol: str, bar, ctx: dict) -> EdgeSignal:
        """
        bar: timestamp, open, high, low, close, volume alanları olan nesne
        ctx: {
            'rs_vs_index':    float,  # hisse / endeks göreli güç
            'sector_strength': float, # sektör gücü (0-100)
            'daily_atr':      float,  # günlük ATR
            'rsi_3':          float,  # 3 günlük RSI
            'ema9_daily':     float,
            'ema21_daily':    float,
            'vol_ma':         float,  # hacim ortalaması
            'intraday_vol':   float,  # gün içi hacim
            'vol_spike':      bool,
            'gap_up':         bool,
        }
        """
        sig = self._get_or_create(symbol)

        # Gün dönüşümünde sıfırla
        bar_date = bar.timestamp.date()
        if sig._date and sig._date != bar_date:
            sig.reset()
        sig._date = bar_date

        # Zaten sinyal verilmişse güncelleme
        if sig.is_signal:
            return sig

        # ── Context ──────────────────────────────────────────
        rs         = float(ctx.get("rs_vs_index", 0))
        sec_str    = float(ctx.get("sector_strength", 0))
        atr        = float(ctx.get("daily_atr", bar.close * 0.03))
        rsi3       = float(ctx.get("rsi_3", 50))
        e9         = float(ctx.get("ema9_daily", 0))
        e21        = float(ctx.get("ema21_daily", 0))
        vol_ma     = float(ctx.get("vol_ma", 0))
        intra_vol  = float(ctx.get("intraday_vol", bar.volume))
        vol_spike  = bool(ctx.get("vol_spike", False))
        gap_up     = bool(ctx.get("gap_up", False))

        # Trend filtresi — EMA9 > EMA21
        is_uptrend = (e9 > e21) if (e9 > 0 and e21 > 0) else True
        if not is_uptrend:
            return sig

        # ── CORE_EDGE (öncelikli) ─────────────────────────────
        if rs >= CORE_RS_THRESHOLD:
            is_consol  = (atr / bar.close) < CORE_CONSOLIDATION_THRESHOLD
            is_vol_ok  = (intra_vol > vol_ma * CORE_VOL_THRESHOLD) or vol_spike

            if is_consol and is_vol_ok:
                sig.is_signal  = True
                sig.setup_type = SetupType.CORE_EDGE
                sig.entry      = bar.close
                sig.stop       = bar.close - (atr * CORE_STOP_ATR)
                sig.target     = bar.close + (atr * CORE_TARGET_ATR)
                sig.daily_atr  = atr
                sig.rs_score   = rs
                sig.rsi3       = rsi3
                sig.sector_str = sec_str
                sig.weight     = CORE_WEIGHT
                sig.rr_ratio   = round(CORE_TARGET_ATR / CORE_STOP_ATR, 2)
                sig.detail     = (
                    f"CORE EDGE | RS:{rs:.2f} | "
                    f"ATR/P:{atr/bar.close*100:.1f}% | "
                    f"Vol:{intra_vol/vol_ma:.1f}x"
                ) if vol_ma > 0 else f"CORE EDGE | RS:{rs:.2f}"
                return sig

        # ── SWING_EDGE ─────────────────────────────────────────
        is_swing = (rsi3 < SWING_RSI3_THRESHOLD) or (gap_up and rs > SWING_GAP_RS_THRESHOLD)

        if is_swing:
            sig.is_signal  = True
            sig.setup_type = SetupType.SWING_EDGE
            sig.entry      = bar.close
            sig.stop       = bar.close - (atr * SWING_STOP_ATR)
            sig.target     = bar.close + (atr * SWING_TARGET_ATR)
            sig.daily_atr  = atr
            sig.rs_score   = rs
            sig.rsi3       = rsi3
            sig.sector_str = sec_str
            sig.weight     = SWING_WEIGHT
            sig.rr_ratio   = round(SWING_TARGET_ATR / SWING_STOP_ATR, 2)

            if rsi3 < SWING_RSI3_THRESHOLD:
                sig.detail = f"SWING EDGE | RSI3:{rsi3:.1f} (aşırı satım)"
            else:
                sig.detail = f"SWING EDGE | Gap-Up + RS:{rs:.2f}"
            return sig

        return sig

    # ── Yardımcılar ──────────────────────────────────────────

    def get_signals(self) -> list[EdgeSignal]:
        return [s for s in self._signals.values() if s.is_signal]

    def get_all(self) -> list[EdgeSignal]:
        return list(self._signals.values())

    def reset_day(self):
        for s in self._signals.values():
            s.reset()

    def _get_or_create(self, sym: str) -> EdgeSignal:
        if sym not in self._signals:
            self._signals[sym] = EdgeSignal(symbol=sym)
        return self._signals[sym]
