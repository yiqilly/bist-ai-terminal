# ============================================================
# strategy/bull_breakout_strategy.py
# BULL Rejim → Opening Range Breakout Stratejisi
#
# Backtestten doğrulanan mantık:
#   - 10:10-10:30 açılış momentum penceresi
#   - Opening range (10:00-10:10) high kırılımı
#   - Pullback → Rebreak setup
#   - Momentum Surge
#   - Günlük ATR bazlı stop/hedef (5dk ATR değil)
#   - Sektör >= 60, RS >= 0.5, fiyat > VWAP
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from enum import Enum
from typing import Optional


# ── Sabitler ────────────────────────────────────────────────
WINDOW_START     = time(10, 10)
WINDOW_END       = time(10, 30)

ATR_STOP_MULT    = 0.70   # stop   = entry - günlük_ATR × 0.70
ATR_TARGET_MULT  = 2.00   # target = entry + günlük_ATR × 2.00  (~2.85R)
ATR_TRAIL_MULT   = 0.50
RR_MIN           = 1.8

SEC_STR_MIN      = 60.0
RS_MIN           = 0.5
LIQUIDITY_MIN    = 7.0
RSI_MIN          = 55.0
RSI_MAX          = 76.0
CONFIRM_BARS     = 2
MAX_PULLBACK_BARS= 3

STRATEGY_TYPE    = "BULL_BREAKOUT"


class BullSetupType(str, Enum):
    NONE             = "NONE"
    BREAKOUT         = "BREAKOUT"
    PULLBACK_REBREAK = "PULLBACK_REBREAK"
    MOMENTUM_SURGE   = "MOMENTUM_SURGE"


class BullSignalState(str, Enum):
    IDLE      = "IDLE"
    WATCHING  = "WATCHING"
    SETUP     = "SETUP"
    SIGNAL    = "SIGNAL"
    REJECT    = "REJECT"


@dataclass
class BullSetupResult:
    setup_type:       BullSetupType = BullSetupType.NONE
    breakout_price:   float = 0.0
    or_high:          float = 0.0
    or_low:           float = 0.0
    volume_confirmed: bool  = False
    surge_pct:        float = 0.0
    detail:           str   = ""


@dataclass
class BullSignal:
    """Strategy Router'a döndürülen sinyal nesnesi."""
    symbol:        str
    state:         BullSignalState = BullSignalState.IDLE
    setup_type:    BullSetupType   = BullSetupType.NONE
    strategy_type: str             = STRATEGY_TYPE

    # Seviyeler (BUY_SIGNAL state'inde dolu)
    entry:         float = 0.0
    stop:          float = 0.0
    target:        float = 0.0
    daily_atr:     float = 0.0

    # Filtre skorları
    sector_str:    float = 0.0
    rs_score:      float = 0.0
    rsi:           float = 50.0
    liquidity:     float = 0.0

    # State persistence
    confirm_count: int   = 0
    persist_count: int   = 0
    reject_count:  int   = 0

    detail:        str   = ""

    def is_buy_signal(self) -> bool:
        return self.state == BullSignalState.SIGNAL

    def reset(self):
        self.state         = BullSignalState.IDLE
        self.setup_type    = BullSetupType.NONE
        self.confirm_count = 0
        self.persist_count = 0
        self.entry = self.stop = self.target = 0.0


class BullBreakoutStrategy:
    """
    BULL rejim için Opening Range Breakout stratejisi.
    Her 5m bar'da on_bar() çağrılır.

    Kullanım:
        strategy = BullBreakoutStrategy()
        signal   = strategy.on_bar(sym, bar, ctx)
        if signal and signal.is_buy_signal():
            # trade aç
    """

    def __init__(self):
        self._signals: dict[str, BullSignal] = {}
        self._vwaps:   dict[str, _VWAPCalc]  = {}

    # ── Ana metod ────────────────────────────────────────────
    def on_bar(self, symbol: str, bar, ctx: dict) -> Optional[BullSignal]:
        """
        ctx içeriği:
            sector_strength: float
            rs_vs_index:     float
            ema9_daily:      float
            ema21_daily:     float
            rsi_daily:       float
            daily_atr:       float   ← günlük ATR (5dk değil)
            vol_ma:          float
            intraday_vol:    float
            intraday_bars:   list[Bar]
        """
        sig = self._get_or_create(symbol)
        vwap_eng = self._vwaps.setdefault(symbol, _VWAPCalc())

        # Gün değişimi → sıfırla
        from datetime import date
        if hasattr(sig, '_date') and sig._date != bar.timestamp.date():
            sig.reset()
        sig._date = bar.timestamp.date()

        # VWAP güncelle
        vwap_val = vwap_eng.update(bar)

        bar_t = bar.timestamp.time()

        # REJECT cooldown
        if sig.state == BullSignalState.REJECT:
            sig.reject_count += 1
            if sig.reject_count >= 12:   # 60 dk cooldown
                sig.reset()
            return sig

        # Pencere dışı
        if not (WINDOW_START <= bar_t <= WINDOW_END):
            if sig.state == BullSignalState.SIGNAL:
                sig.persist_count += 1
                if sig.persist_count > 24:
                    sig.reset()
            return sig

        # ── Filtre katmanı ────────────────────────────────────

        # 1. Sektör gücü
        sec_str = float(ctx.get('sector_strength', 0))
        if sec_str < SEC_STR_MIN:
            sig.state = BullSignalState.IDLE
            return sig
        sig.sector_str = sec_str

        # 2. RS
        rs_val = float(ctx.get('rs_vs_index', 0))
        if rs_val < RS_MIN:
            sig.state = BullSignalState.IDLE
            return sig
        sig.rs_score = rs_val

        # 3. Trend: günlük EMA9 > EMA21
        e9  = float(ctx.get('ema9_daily',  0))
        e21 = float(ctx.get('ema21_daily', 0))
        if e9 <= 0 or e21 <= 0 or e9 <= e21:
            sig.state = BullSignalState.IDLE
            return sig

        # 4. Fiyat > VWAP
        if vwap_val > 0 and bar.close <= vwap_val:
            sig.state = BullSignalState.IDLE
            return sig

        # 5. RSI bandı
        rsi_val = float(ctx.get('rsi_daily', 50))
        if not (RSI_MIN <= rsi_val <= RSI_MAX):
            sig.state = BullSignalState.IDLE
            return sig
        sig.rsi = rsi_val

        # 6. Liquidity
        datr    = float(ctx.get('daily_atr',   bar.close * 0.03))
        iv      = float(ctx.get('intraday_vol', 0))
        vol_ma  = float(ctx.get('vol_ma',       0))
        liq = self._liquidity_score(bar.close, bar.volume, vol_ma, datr, iv)
        if liq < LIQUIDITY_MIN:
            sig.state = BullSignalState.IDLE
            return sig
        sig.liquidity = liq
        sig.daily_atr = datr

        # 7. Setup tespiti
        ib      = ctx.get('intraday_bars', [])
        setup   = self._detect_setup(ib, e9, vol_ma)

        if setup.setup_type == BullSetupType.NONE:
            sig.state = BullSignalState.IDLE
            return sig

        sig.setup_type = setup.setup_type
        sig.detail     = setup.detail

        # ── State machine ─────────────────────────────────────

        if sig.state == BullSignalState.SIGNAL:
            sig.persist_count += 1
            if sig.persist_count > 24:
                sig.reset()
            return sig

        if sig.state == BullSignalState.IDLE:
            sig.state         = BullSignalState.SETUP
            sig.confirm_count = 1
            return sig

        if sig.state == BullSignalState.SETUP:
            sig.confirm_count += 1
            needed = 1 if setup.setup_type == BullSetupType.PULLBACK_REBREAK else CONFIRM_BARS
            if sig.confirm_count >= needed:
                entry  = bar.close
                stop   = entry - datr * ATR_STOP_MULT
                target = entry + datr * ATR_TARGET_MULT
                risk   = entry - stop
                if risk > 0 and (target-entry)/risk >= RR_MIN and risk/entry <= 0.12:
                    sig.state         = BullSignalState.SIGNAL
                    sig.entry         = entry
                    sig.stop          = stop
                    sig.target        = target
                    sig.persist_count = 0
                else:
                    sig.state        = BullSignalState.REJECT
                    sig.reject_count = 0
                    sig.detail      += " | R/R yetersiz"

        return sig

    def get_signals(self) -> list[BullSignal]:
        return list(self._signals.values())

    def get_buy_signals(self) -> list[BullSignal]:
        return [s for s in self._signals.values()
                if s.state == BullSignalState.SIGNAL]

    def reset_day(self):
        for s in self._signals.values():
            s.reset()

    # ── Yardımcılar ──────────────────────────────────────────
    def _get_or_create(self, sym: str) -> BullSignal:
        if sym not in self._signals:
            self._signals[sym] = BullSignal(symbol=sym)
        return self._signals[sym]

    def _liquidity_score(self, price, volume, vol_ma, atr, intraday_vol) -> float:
        spread_pct = atr/price*100 if price > 0 else 5.0
        vol_s = (4.0 if intraday_vol>=2e6 else
                 3.0 if intraday_vol>=8e5 else
                 2.0 if intraday_vol>=3e5 else 0.5)
        sp_s  = (3.0 if spread_pct<1.0 else
                 2.0 if spread_pct<2.0 else
                 1.2 if spread_pct<3.5 else 0.3)
        pr_s  = (2.0 if price>=20 else 1.5 if price>=5 else
                 0.8 if price>=2 else 0.2)
        vr    = volume/vol_ma if vol_ma > 0 else 1.0
        vr_s  = 1.0 if vr>=2.0 else 0.7 if vr>=1.0 else 0.3
        return min(round(vol_s+sp_s+pr_s+vr_s, 2), 10.0)

    def _detect_setup(self, bars: list, ema9: float, vol_ma: float) -> BullSetupResult:
        result = BullSetupResult()
        if not bars: return result

        intraday = [b for b in bars if b.timestamp.time() >= time(10, 0)]
        if not intraday: return result

        or_bars  = [b for b in intraday if b.timestamp.time() < WINDOW_START]
        w_bars   = [b for b in intraday if WINDOW_START <= b.timestamp.time() <= WINDOW_END]
        if not or_bars: return result

        or_high = max(b.high for b in or_bars)
        or_low  = min(b.low  for b in or_bars)
        result.or_high = or_high
        result.or_low  = or_low
        avg_vol = vol_ma if vol_ma > 0 else sum(b.volume for b in or_bars)/len(or_bars)

        # Momentum Surge: açılışta güçlü hareket
        if w_bars:
            first  = w_bars[0]
            ref    = or_bars[0].open if or_bars else first.open
            surge  = (first.close-ref)/ref*100 if ref > 0 else 0
            v_ratio= first.volume/avg_vol if avg_vol > 0 else 1.0
            if surge >= 1.5 and v_ratio >= 2.0:
                result.setup_type       = BullSetupType.MOMENTUM_SURGE
                result.breakout_price   = first.close
                result.volume_confirmed = True
                result.surge_pct        = surge
                result.detail = f"Surge +{surge:.2f}% vol={v_ratio:.1f}x"
                return result

        # Breakout: OR high kırılımı
        bo_idx = -1; bo_price = 0.0
        for i, b in enumerate(w_bars):
            if b.close > or_high and b.volume >= avg_vol*1.3:
                bo_idx = i; bo_price = b.close; break

        if bo_idx < 0: return result
        result.breakout_price   = bo_price
        result.volume_confirmed = True

        post = w_bars[bo_idx+1:]
        if not post:
            result.setup_type = BullSetupType.BREAKOUT
            result.detail = f"Breakout >{or_high:.2f}"
            return result

        # Pullback → Rebreak
        pb = post[:MAX_PULLBACK_BARS]
        if pb:
            pb_low  = min(b.low for b in pb)
            pb_vols = [b.volume for b in pb]
            bo_vol  = w_bars[bo_idx].volume
            depth   = (bo_price-pb_low)/bo_price
            ema_ok  = pb_low >= ema9 * 0.995
            vol_drop= all(v < bo_vol for v in pb_vols)

            if depth >= 0.002 and ema_ok and vol_drop:
                rb_bars = post[len(pb):]
                avg_pb_vol = sum(pb_vols)/len(pb_vols) if pb_vols else bo_vol
                for b in rb_bars:
                    if b.close > or_high and b.volume >= avg_pb_vol*1.2:
                        result.setup_type  = BullSetupType.PULLBACK_REBREAK
                        result.detail = (f"PullRebreak BO>{or_high:.2f} "
                                         f"PB={pb_low:.2f} RB={b.close:.2f}")
                        return result

        result.setup_type = BullSetupType.BREAKOUT
        result.detail = f"Breakout >{or_high:.2f}"
        return result


class _VWAPCalc:
    """Intraday VWAP — her gün 10:00'da sıfırlanır."""
    def __init__(self):
        self._date = None
        self._tv = self._vol = 0.0

    def update(self, bar) -> float:
        if bar.timestamp.date() != self._date:
            self._date = bar.timestamp.date()
            self._tv = self._vol = 0.0
        if bar.timestamp.time() < time(10, 0): return 0.0
        tp = (bar.high+bar.low+bar.close)/3
        self._tv  += tp * bar.volume
        self._vol += bar.volume
        return self._tv/self._vol if self._vol > 0 else bar.close
