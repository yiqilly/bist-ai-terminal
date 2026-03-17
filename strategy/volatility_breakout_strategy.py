# ============================================================
# strategy/volatility_breakout_strategy.py
# VOLATILE Rejim → Volatilite Breakout Stratejisi
#
# Mantık:
#   - Piyasa VOLATILE: ATR spike + hacim spike
#   - Normal breakout değil, yüksek enerji kırılımı
#   - Daha sert teyit: 2 ardışık güçlü bar
#   - Stop daha geniş (volatiliteye orantılı)
#   - Günde max 1-2 trade (seçici)
# ============================================================
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import Enum
from typing import Optional


# ── Sabitler ────────────────────────────────────────────────
ENTRY_START        = time(10, 10)
ENTRY_END          = time(11, 30)   # dar pencere — volatile günde erken hareket

ATR_SPIKE_MULT     = 1.20   # günlük ATR'nin 1.2x'i → spike (BIST'e uygun)
VOL_SPIKE_MULT     = 1.80   # hacim ortalamasının 1.8x'i → spike
ATR_STOP_MULT      = 1.20   # geniş stop (volatilite yüksek)
ATR_TARGET_MULT    = 2.40   # hedef 2R (geniş stop nedeniyle daha büyük)
ATR_TRAIL_MULT     = 0.80
RR_MIN             = 1.8
CONFIRM_BARS       = 1       # volatile'de hız önemli, 1 bar teyit
MAX_DAILY_TRADES   = 2       # günde max 2 trade
STRATEGY_TYPE      = "VOLATILE_BREAKOUT"


class VolSetupType(str, Enum):
    NONE            = "NONE"
    ENERGY_BREAKOUT = "ENERGY_BREAKOUT"   # güçlü hacim + momentum kırılım
    ATR_EXPANSION   = "ATR_EXPANSION"     # ATR genişlemesi ile kırılım


class VolSignalState(str, Enum):
    IDLE    = "IDLE"
    SETUP   = "SETUP"
    SIGNAL  = "SIGNAL"
    REJECT  = "REJECT"


@dataclass
class VolSignal:
    symbol:        str
    state:         VolSignalState = VolSignalState.IDLE
    setup_type:    VolSetupType   = VolSetupType.NONE
    strategy_type: str            = STRATEGY_TYPE

    entry:         float = 0.0
    stop:          float = 0.0
    target:        float = 0.0
    daily_atr:     float = 0.0

    sector_str:    float = 0.0
    rs_score:      float = 0.0
    atr_spike:     float = 0.0   # güncel ATR / baz ATR
    vol_spike:     float = 0.0   # güncel hacim / ortalama hacim

    confirm_count: int   = 0
    reject_count:  int   = 0
    persist_count: int   = 0
    detail:        str   = ""

    def is_buy_signal(self) -> bool:
        return self.state == VolSignalState.SIGNAL

    def reset(self):
        self.state         = VolSignalState.IDLE
        self.setup_type    = VolSetupType.NONE
        self.confirm_count = 0
        self.persist_count = 0
        self.entry = self.stop = self.target = 0.0


class VolatilityBreakoutStrategy:
    """
    VOLATILE rejim için yüksek enerji breakout stratejisi.

    ctx içeriği:
        sector_strength: float
        rs_vs_index:     float
        ema9_daily:      float
        ema21_daily:     float
        daily_atr:       float   ← günlük ATR baz
        intraday_atr:    float   ← anlık 5dk ATR (spike tespiti için)
        vol_ma:          float
        intraday_bars:   list[Bar]
        daily_open:      float   ← günün açılış fiyatı
    """

    def __init__(self):
        self._signals:    dict[str, VolSignal] = {}
        self._day_trades: dict[str, int]       = {}   # gün başına trade sayısı

    def on_bar(self, symbol: str, bar, ctx: dict) -> Optional[VolSignal]:
        sig = self._get_or_create(symbol)

        # Gün değişimi
        today = bar.timestamp.date()
        if hasattr(sig, '_date') and sig._date != today:
            sig.reset()
            self._day_trades[today] = self._day_trades.get(today, 0)
        sig._date = today

        bar_t = bar.timestamp.time()

        # Günlük trade limiti
        day_cnt = self._day_trades.get(today, 0)

        # REJECT cooldown
        if sig.state == VolSignalState.REJECT:
            sig.reject_count += 1
            if sig.reject_count >= 6:
                sig.reset()
            return sig

        # Pencere dışı
        if not (ENTRY_START <= bar_t <= ENTRY_END):
            if sig.state == VolSignalState.SIGNAL:
                sig.persist_count += 1
                if sig.persist_count > 12:
                    sig.reset()
            return sig

        # Günlük limit
        if day_cnt >= MAX_DAILY_TRADES:
            return sig

        # ── Filtreler ─────────────────────────────────────────

        sec_str     = float(ctx.get('sector_strength', 0))
        rs_val      = float(ctx.get('rs_vs_index',    0))
        datr        = float(ctx.get('daily_atr',      bar.close*0.03))
        intraday_atr= float(ctx.get('intraday_atr',   datr/10))
        vol_ma      = float(ctx.get('vol_ma',         0))
        e9          = float(ctx.get('ema9_daily',     0))
        e21         = float(ctx.get('ema21_daily',    0))

        sig.daily_atr  = datr
        sig.sector_str = sec_str
        sig.rs_score   = rs_val

        # 1. Trend gereksinimi: volatile'de sadece trend yönünde
        trend_up = e9 > e21 if (e9 > 0 and e21 > 0) else False
        if not trend_up:
            sig.state = VolSignalState.IDLE; return sig

        # 2. Sektör liderliği (volatile'de seçici)
        if sec_str < 65:
            sig.state = VolSignalState.IDLE; return sig

        # 3. RS pozitif
        if rs_val < 0:
            sig.state = VolSignalState.IDLE; return sig

        # 4. ATR spike tespiti (anlık volatilite artışı)
        atr_ratio = intraday_atr / (datr/10) if datr > 0 else 1.0
        atr_spike_ok = atr_ratio >= ATR_SPIKE_MULT
        sig.atr_spike = atr_ratio

        # 5. Hacim spike
        vol_ratio = bar.volume / vol_ma if vol_ma > 0 else 1.0
        vol_spike_ok = vol_ratio >= VOL_SPIKE_MULT
        sig.vol_spike = vol_ratio

        # Her ikisi de tetiklenmeli
        if not (atr_spike_ok and vol_spike_ok):
            sig.state = VolSignalState.IDLE; return sig

        # 6. Fiyat yukarı kırılım (opening range veya gün high'ı üzerine)
        ib = ctx.get('intraday_bars', [])
        if len(ib) >= 3:
            recent_high = max(b.high for b in ib[-5:-1])
            breakout_up = bar.close > recent_high
        else:
            breakout_up = bar.close > bar.open

        if not breakout_up:
            sig.state = VolSignalState.IDLE; return sig

        # Setup belirlendi
        if atr_ratio >= ATR_SPIKE_MULT * 1.3:
            setup = VolSetupType.ATR_EXPANSION
        else:
            setup = VolSetupType.ENERGY_BREAKOUT

        sig.setup_type = setup
        sig.detail = (f"{setup.value} ATR×{atr_ratio:.1f} "
                      f"Vol×{vol_ratio:.1f}")

        # ── State machine ─────────────────────────────────────
        if sig.state == VolSignalState.SIGNAL:
            sig.persist_count += 1
            if sig.persist_count > 12:
                sig.reset()
            return sig

        if sig.state == VolSignalState.IDLE:
            sig.state         = VolSignalState.SETUP
            sig.confirm_count = 1
            return sig

        if sig.state == VolSignalState.SETUP:
            sig.confirm_count += 1
            if sig.confirm_count >= CONFIRM_BARS:
                # Geniş stop — volatiliteye orantılı
                entry  = bar.close
                stop   = entry - datr * ATR_STOP_MULT
                target = entry + datr * ATR_TARGET_MULT
                risk   = entry - stop
                if risk > 0 and (target-entry)/risk >= RR_MIN and risk/entry <= 0.15:
                    sig.state         = VolSignalState.SIGNAL
                    sig.entry         = entry
                    sig.stop          = stop
                    sig.target        = target
                    sig.persist_count = 0
                    self._day_trades[today] = day_cnt + 1
                else:
                    sig.state        = VolSignalState.REJECT
                    sig.reject_count = 0

        return sig

    def get_buy_signals(self) -> list[VolSignal]:
        return [s for s in self._signals.values()
                if s.state == VolSignalState.SIGNAL]

    def reset_day(self):
        for s in self._signals.values():
            s.reset()

    def _get_or_create(self, sym: str) -> VolSignal:
        if sym not in self._signals:
            self._signals[sym] = VolSignal(symbol=sym)
        return self._signals[sym]
