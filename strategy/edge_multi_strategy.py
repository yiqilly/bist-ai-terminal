# ============================================================
# strategy/edge_multi_strategy.py
# Dinamik Edge (Core + Swing) Strateji Motoru
#
# Son test edilen Unified (Paylaşımlı Kasa) yapısını taklit eder.
# Çıktı olarak RouterSignal (BUY) üretir.
# ============================================================
from __future__ import annotations

from dataclasses import dataclass
from datetime import time, date
from enum import Enum
from typing import Optional

from strategy.edge_backtest.edge_signals import RS_THRESHOLD, VOL_THRESHOLD, CONSOLIDATION_THRESHOLD


STRATEGY_TYPE = "EDGE_MULTI"

class EdgeSetupType(str, Enum):
    NONE      = "NONE"
    CORE_EDGE = "CORE_EDGE"
    SWING_EDGE= "SWING_EDGE"

class EdgeSignalState(str, Enum):
    IDLE      = "IDLE"
    SIGNAL    = "SIGNAL"

@dataclass
class EdgeSignal:
    symbol:        str
    state:         EdgeSignalState = EdgeSignalState.IDLE
    setup_type:    EdgeSetupType   = EdgeSetupType.NONE
    strategy_type: str             = STRATEGY_TYPE
    
    entry:         float = 0.0
    stop:          float = 0.0
    target:        float = 0.0
    daily_atr:     float = 0.0
    
    sector_str:    float = 0.0
    rs_score:      float = 0.0
    rsi:           float = 50.0
    detail:        str   = ""

    _date:         Optional[date] = None

    def is_buy_signal(self) -> bool:
        return self.state == EdgeSignalState.SIGNAL

    def reset(self):
        self.state = EdgeSignalState.IDLE
        self.setup_type = EdgeSetupType.NONE
        self.entry = self.stop = self.target = 0.0


class EdgeMultiStrategy:
    """
    Core (Uzun Vade) ve Swing (Kısa Vade Vur-Kaç) mantığını
    intraday bar verileriyle çalışacak şekilde canlı sisteme uyarlayan motor.
    """
    def __init__(self):
        self._signals: dict[str, EdgeSignal] = {}

    def on_bar(self, symbol: str, bar, ctx: dict) -> Optional[EdgeSignal]:
        """
        Her 5 dakikalık barda çalışır.
        Edge sistemi EOD (Günlük Kapanış) bazlı olduğu için,
        asıl kararı 10:00 (piyasa açılışı) barında verir.
        """
        sig = self._get_or_create(symbol)

        # Gün dönüşümlerinde sinyali sıfırla
        if hasattr(sig, '_date') and sig._date != bar.timestamp.date():
            sig.reset()
        sig._date = bar.timestamp.date()

        # Edge stratejisi gün boyu çalışabilir (eskiden sadece 10:15'e kadardı)
        bar_t = bar.timestamp.time()
        # if bar_t > time(10, 15): 
        #     return sig

        if sig.state == EdgeSignalState.SIGNAL:
            return sig

        # ── Context Verilerini Çek ─────────────────────────────────
        sec_str     = float(ctx.get('sector_strength', 0))
        rs_vs_index = float(ctx.get('rs_vs_index', 0))
        atr_14      = float(ctx.get('daily_atr', bar.close * 0.03))
        rsi_3       = float(ctx.get('rsi_3', float(ctx.get('rsi_daily', 50))))
        e9          = float(ctx.get('ema9_daily', 0))
        e21         = float(ctx.get('ema21_daily', 0))
        vol_ma      = float(ctx.get('vol_ma', 0))
        
        # Trend yönü filtresi
        is_uptrend = (e9 > e21) if (e9 > 0 and e21 > 0) else True

        if not is_uptrend:
            return sig  # Düşüş trendinde işleme girme

        # ── CORE STRATEJİ KONTROLÜ (Öncelikli) ────────────────────
        is_core = False
        if rs_vs_index >= RS_THRESHOLD:
            # Consolidation check
            if atr_14 / bar.close < CONSOLIDATION_THRESHOLD:
                # Volume check (Dünün veya açılışın hacmi yüksek mi?)
                intraday_vol = float(ctx.get('intraday_vol', bar.volume))
                if intraday_vol > (vol_ma * 1.5) or ctx.get('vol_spike', False):
                    is_core = True

        if is_core:
            sig.state      = EdgeSignalState.SIGNAL
            sig.setup_type = EdgeSetupType.CORE_EDGE
            sig.entry      = bar.close
            sig.stop       = bar.close - (atr_14 * 2.0)
            sig.target     = bar.close + (atr_14 * 5.0)  # Core (Büyük hedef)
            sig.daily_atr  = atr_14
            sig.rs_score   = rs_vs_index
            sig.detail     = f"CORE EDGE (RS:{rs_vs_index:.2f})"
            return sig

        # ── SWING STRATEJİ KONTROLÜ (Core yoksa vur-kaç) ──────────
        is_swing = False
        if rsi_3 < 15.0: # Aşırı satım zıplaması
            is_swing = True
        elif ctx.get('gap_up', False) and rs_vs_index > 1.05: # Güçlü Gap-Up
            is_swing = True

        if is_swing:
            sig.state      = EdgeSignalState.SIGNAL
            sig.setup_type = EdgeSetupType.SWING_EDGE
            sig.entry      = bar.close
            sig.stop       = bar.close - (atr_14 * 1.0)  # Swing (Dar stop)
            sig.target     = bar.close + (atr_14 * 1.5)  # Swing (Hızlı kâr al)
            sig.daily_atr  = atr_14
            sig.rs_score   = rs_vs_index
            sig.detail     = f"SWING EDGE (RSI3:{rsi_3:.1f})"
            return sig

        return sig

    def get_signals(self) -> list[EdgeSignal]:
        return list(self._signals.values())

    def get_buy_signals(self) -> list[EdgeSignal]:
        return [s for s in self._signals.values() if s.state == EdgeSignalState.SIGNAL]

    def reset_day(self):
        for s in self._signals.values():
            s.reset()

    def _get_or_create(self, sym: str) -> EdgeSignal:
        if sym not in self._signals:
            self._signals[sym] = EdgeSignal(symbol=sym)
        return self._signals[sym]
