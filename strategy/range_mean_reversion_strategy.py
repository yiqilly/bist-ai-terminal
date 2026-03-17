# ============================================================
# strategy/range_mean_reversion_strategy.py
# RANGE Rejim → Mean Reversion Stratejisi
#
# Mantık:
#   - Fiyat intraday VWAP'tan uzaklaşmış (aşağı)
#   - RSI aşırı satış bölgesinde (< 40)
#   - Satış momentumu zayıflıyor (son barlarda hacim düşüyor)
#   - Dönüş mumu / reclaim sinyali geliyor
#   - Hedef: VWAP'a geri dönüş
# ============================================================
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import Enum
from typing import Optional


# ── Sabitler ────────────────────────────────────────────────
ENTRY_START    = time(10, 30)   # RANGE'de giriş daha geç başlar
ENTRY_END      = time(14, 30)   # gün ortası fırsatlar

RSI_OVERSOLD   = 42.0           # bu altına düşmüş → potansiyel dönüş
RSI_MAX        = 58.0           # aşırı alımda değil
VWAP_DEV_MIN   = 0.005          # VWAP'tan en az %0.5 uzaklaşma
VWAP_DEV_MAX   = 0.035          # ama çok uzak değil (dip değil mean rev)
VOL_FADE_BARS  = 3              # son 3 barda hacim azalmalı
ATR_STOP_MULT  = 0.45           # sıkı stop (mean rev için)
ATR_TARGET_MULT= 1.50           # hedef: ATR bazlı
RR_MIN         = 1.5
CONFIRM_BARS   = 2
STRATEGY_TYPE  = "RANGE_REVERSION"


class MeanRevSetupType(str, Enum):
    NONE          = "NONE"
    VWAP_RECLAIM  = "VWAP_RECLAIM"    # VWAP altı → reclaim
    OVERSOLD_BOUNCE = "OVERSOLD_BOUNCE"  # RSI aşırı satım + dönüş mumu


class MeanRevState(str, Enum):
    IDLE    = "IDLE"
    SETUP   = "SETUP"
    SIGNAL  = "SIGNAL"
    REJECT  = "REJECT"


@dataclass
class MeanRevSignal:
    symbol:        str
    state:         MeanRevState    = MeanRevState.IDLE
    setup_type:    MeanRevSetupType= MeanRevSetupType.NONE
    strategy_type: str             = STRATEGY_TYPE

    entry:         float = 0.0
    stop:          float = 0.0
    target:        float = 0.0
    vwap_target:   float = 0.0   # VWAP hedefi
    daily_atr:     float = 0.0

    sector_str:    float = 0.0
    rsi:           float = 50.0
    vwap_dev_pct:  float = 0.0   # VWAP'tan uzaklaşma %

    confirm_count: int   = 0
    reject_count:  int   = 0
    persist_count: int   = 0
    detail:        str   = ""

    def is_buy_signal(self) -> bool:
        return self.state == MeanRevState.SIGNAL

    def reset(self):
        self.state         = MeanRevState.IDLE
        self.setup_type    = MeanRevSetupType.NONE
        self.confirm_count = 0
        self.persist_count = 0
        self.entry = self.stop = self.target = 0.0


class RangeMeanReversionStrategy:
    """
    RANGE rejim için Mean Reversion stratejisi.

    ctx içeriği (on_bar):
        vwap_value:      float   ← intraday VWAP (caller hesaplar)
        rsi_intraday:    float   ← kısa vadeli RSI (14-bar 5m)
        sector_strength: float
        daily_atr:       float
        intraday_bars:   list[Bar]
    """

    def __init__(self):
        self._signals: dict[str, MeanRevSignal] = {}

    def on_bar(self, symbol: str, bar, ctx: dict) -> Optional[MeanRevSignal]:
        sig = self._get_or_create(symbol)

        # Gün değişimi
        if hasattr(sig, '_date') and sig._date != bar.timestamp.date():
            sig.reset()
        sig._date = bar.timestamp.date()

        bar_t = bar.timestamp.time()

        # REJECT cooldown
        if sig.state == MeanRevState.REJECT:
            sig.reject_count += 1
            if sig.reject_count >= 6:
                sig.reset()
            return sig

        # Pencere dışı
        if not (ENTRY_START <= bar_t <= ENTRY_END):
            if sig.state == MeanRevState.SIGNAL:
                sig.persist_count += 1
                if sig.persist_count > 48:
                    sig.reset()
            return sig

        # ── Filtreler ─────────────────────────────────────────

        vwap    = float(ctx.get('vwap_value',   0))
        rsi     = float(ctx.get('rsi_intraday', 50))
        datr    = float(ctx.get('daily_atr',    bar.close*0.025))
        sec_str = float(ctx.get('sector_strength', 50))

        sig.daily_atr  = datr
        sig.sector_str = sec_str
        sig.rsi        = rsi

        # 1. RANGE rejimde orta güçlü sektör (aşırı zayıf değil)
        if sec_str < 35 or sec_str > 70:
            sig.state = MeanRevState.IDLE; return sig

        # 2. Fiyat VWAP altında — ama çok uzak değil
        if vwap <= 0:
            sig.state = MeanRevState.IDLE; return sig
        dev = (vwap - bar.close) / vwap   # pozitif = fiyat VWAP altında
        if not (VWAP_DEV_MIN <= dev <= VWAP_DEV_MAX):
            sig.state = MeanRevState.IDLE; return sig
        sig.vwap_dev_pct = dev * 100
        sig.vwap_target  = vwap

        # 3. RSI aşırı satım bölgesi
        if not (rsi < RSI_OVERSOLD):
            sig.state = MeanRevState.IDLE; return sig

        # 4. Hacim fade: son barlarda satış zayıflıyor mu? (opsiyonel bonus)
        ib = ctx.get('intraday_bars', [])
        recent = [b for b in ib if b.timestamp.time() >= ENTRY_START][-VOL_FADE_BARS-1:]
        vol_fade = (len(recent) >= 2 and
                    recent[-1].volume < recent[0].volume * 1.2)

        # 5. Dönüş göstergesi: fiyat düşmekten duruyor mu?
        # Gevşetildi: sadece yakın kapanış veya yukarı bar yeterli
        lower_wick  = (bar.close - bar.low) / (bar.high - bar.low + 0.001)
        not_falling = bar.close >= bar.open * 0.999   # düşüş durdu
        reversal    = (not_falling or lower_wick > 0.4)

        # Setup tespiti — koşulları gevşet
        if dev >= VWAP_DEV_MIN and rsi < RSI_OVERSOLD and reversal:
            setup = MeanRevSetupType.VWAP_RECLAIM
            detail = f"VWAPreclaim dev={dev*100:.2f}% RSI={rsi:.0f}"
        elif rsi < RSI_OVERSOLD * 0.90 and dev >= VWAP_DEV_MIN * 0.8:
            # Aşırı satım — dev biraz daha az olsa da olur
            setup = MeanRevSetupType.OVERSOLD_BOUNCE
            detail = f"Oversold RSI={rsi:.0f} dev={dev*100:.2f}%"
        else:
            sig.state = MeanRevState.IDLE; return sig

        sig.setup_type = setup
        sig.detail     = detail

        # ── State machine ─────────────────────────────────────
        if sig.state == MeanRevState.SIGNAL:
            sig.persist_count += 1
            return sig

        if sig.state == MeanRevState.IDLE:
            sig.state         = MeanRevState.SETUP
            sig.confirm_count = 1
            return sig

        if sig.state == MeanRevState.SETUP:
            sig.confirm_count += 1
            if sig.confirm_count >= CONFIRM_BARS:
                entry  = bar.close
                stop   = entry - datr * ATR_STOP_MULT
                # Hedef: VWAP veya ATR bazlı (hangisi yakınsa)
                vwap_tgt  = vwap
                atr_tgt   = entry + datr * ATR_TARGET_MULT
                target    = max(vwap_tgt, atr_tgt)
                risk      = entry - stop
                if risk > 0 and (target-entry)/risk >= RR_MIN and risk/entry <= 0.12:
                    sig.state         = MeanRevState.SIGNAL
                    sig.entry         = entry
                    sig.stop          = stop
                    sig.target        = target
                    sig.persist_count = 0
                else:
                    sig.state        = MeanRevState.REJECT
                    sig.reject_count = 0

        return sig

    def get_buy_signals(self) -> list[MeanRevSignal]:
        return [s for s in self._signals.values()
                if s.state == MeanRevState.SIGNAL]

    def reset_day(self):
        for s in self._signals.values():
            s.reset()

    def _get_or_create(self, sym: str) -> MeanRevSignal:
        if sym not in self._signals:
            self._signals[sym] = MeanRevSignal(symbol=sym)
        return self._signals[sym]
