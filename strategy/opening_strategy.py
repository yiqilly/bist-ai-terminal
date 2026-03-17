# ============================================================
# strategy/opening_strategy.py
# BIST HYBRID OPENING MOMENTUM STRATEGY
# ============================================================
#
# Ana mantık:
#   - 10:00-10:10 → veri toplama, sinyal üretme
#   - 10:10-10:30 → aktif tarama penceresi
#   - Gün boyu sürekli tarama yok
#
# Pipeline (her 5m bar):
#   Snapshot güncelle
#   → VWAP (intraday, 10:00'dan kümülatif)
#   → Liquidity filtre (score >= 7)
#   → Market context filtre (BULL/WEAK_BULL/RANGE)
#   → Sector strength filtre (>= 60)
#   → RS filtre (> 0)
#   → Setup tespiti (BREAKOUT / PULLBACK_REBREAK / MOMENTUM_SURGE)
#   → Trend filtre (EMA9 > EMA21, fiyat > VWAP)
#   → RSI filtre (58-72)
#   → State machine (WATCHLIST→SETUP→BUY_SIGNAL)
#   → BUY_SIGNAL → sonraki bar open'da entry
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, date
from enum import Enum
from typing import Optional
import math


# ══════════════════════════════════════════════════════════════
# SABITLER
# ══════════════════════════════════════════════════════════════
WINDOW_START      = time(10, 10)   # sinyal penceresi başlangıcı
WINDOW_END        = time(10, 30)   # sinyal penceresi sonu
DATA_FORM_END     = time(10, 10)   # bu saate kadar sadece veri topla
EOD_CLOSE         = time(17, 25)   # gün sonu çıkış

# Setup parametreleri
MAX_PULLBACK_BARS = 3              # pullback için max bar sayısı
PULLBACK_EMA9_MAX = 0.005         # pullback EMA9 altına en fazla %0.5 inebilir
REBREAK_VOL_MIN   = 1.2           # rebreak hacmi pullback hacminin en az 1.2x'i

# Filtreler
SECTOR_STR_MIN    = 60.0
SECTOR_STR_HARD   = 50.0          # bu altında kesinlikle no trade
RS_MIN            = 0.0
LIQUIDITY_MIN     = 7.0
RSI_MIN           = 58.0
RSI_MAX           = 72.0
RR_MIN            = 1.8

# State machine
CONFIRM_BARS      = 3             # BUY için 3 bar (15 dk) teyit
BUY_PERSIST_BARS  = 6             # BUY_SIGNAL en az 6 bar yaşar (30 dk)
REJECT_BARS       = 12            # REJECT sonrası 12 bar cooldown (60 dk)

# Risk
ATR_STOP_MULT     = 1.5           # stop = entry - ATR * 1.8
ATR_TARGET_MULT   = 3.0           # target = entry + ATR * 2.7  (≈1.5R)
ATR_TRAIL_MULT    = 0.8
MAX_POSITIONS     = 3


# ══════════════════════════════════════════════════════════════
# SETUP TÜRÜ
# ══════════════════════════════════════════════════════════════
class SetupType(str, Enum):
    NONE             = "NONE"
    BREAKOUT         = "BREAKOUT"
    PULLBACK_REBREAK = "PULLBACK_REBREAK"
    MOMENTUM_SURGE   = "MOMENTUM_SURGE"


# ══════════════════════════════════════════════════════════════
# SIGNAL STATE
# ══════════════════════════════════════════════════════════════
class SigState(str, Enum):
    WATCHLIST  = "WATCHLIST"
    SETUP      = "SETUP"
    BUY_SIGNAL = "BUY_SIGNAL"
    IN_POSITION= "IN_POSITION"
    REJECT     = "REJECT"
    CLOSED     = "CLOSED"


# ══════════════════════════════════════════════════════════════
# BAR (her 5m bar için)
# ══════════════════════════════════════════════════════════════
@dataclass
class Bar:
    timestamp: datetime
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float

    @property
    def t(self) -> time:
        return self.timestamp.time()

    @property
    def d(self) -> date:
        return self.timestamp.date()


# ══════════════════════════════════════════════════════════════
# INTRADAY VWAP (her gün 10:00'da sıfırlanır)
# ══════════════════════════════════════════════════════════════
class IntradayVWAP:
    """
    10:00'dan itibaren kümülatif VWAP.
    Her yeni gün sıfırlanır.
    """
    def __init__(self):
        self._date:    Optional[date] = None
        self._cum_tv:  float = 0.0   # cumulative(typical_price × volume)
        self._cum_vol: float = 0.0   # cumulative volume
        self._vwap:    float = 0.0

    def update(self, bar: Bar) -> float:
        # Yeni gün → sıfırla
        if bar.d != self._date:
            self._date    = bar.d
            self._cum_tv  = 0.0
            self._cum_vol = 0.0
            self._vwap    = 0.0

        # 10:00 öncesi hesaplama
        if bar.t < time(10, 0):
            return 0.0

        tp = (bar.high + bar.low + bar.close) / 3.0
        self._cum_tv  += tp * bar.volume
        self._cum_vol += bar.volume
        self._vwap = self._cum_tv / self._cum_vol if self._cum_vol > 0 else bar.close
        return self._vwap

    @property
    def value(self) -> float:
        return self._vwap


# ══════════════════════════════════════════════════════════════
# LIQUIDITY SCORER
# ══════════════════════════════════════════════════════════════
@dataclass
class LiquidityResult:
    score:     float   # 0-10
    ok:        bool    # score >= 7
    reason:    str


class LiquidityScorer:
    """
    Basit intraday likidite skoru.
    Input: mevcut bar hacmi, ortalama hacim, fiyat, ATR
    Output: 0-10 arası skor
    """
    def score(
        self,
        price:    float,
        volume:   float,
        vol_ma:   float,    # 20-bar hacim ortalaması
        atr:      float,
        intraday_vol: float,  # gün içi kümülatif hacim
    ) -> LiquidityResult:

        # 1. Hacim seviyesi (40 puan)
        if vol_ma > 0:
            vol_ratio = volume / vol_ma
        else:
            vol_ratio = 1.0

        if intraday_vol >= 2_000_000:
            vol_s = 4.0
        elif intraday_vol >= 800_000:
            vol_s = 3.0
        elif intraday_vol >= 300_000:
            vol_s = 2.0
        else:
            vol_s = 0.5

        # 2. Spread proxy: ATR/price — düşük = daha likit (30 puan)
        spread_pct = atr / price * 100 if (price > 0 and atr > 0) else 5.0
        if spread_pct < 1.0:
            sp_s = 3.0
        elif spread_pct < 2.0:
            sp_s = 2.0
        elif spread_pct < 3.5:
            sp_s = 1.2
        else:
            sp_s = 0.3

        # 3. Fiyat seviyesi (20 puan) — çok düşük fiyat = yüksek spread
        if price >= 20:
            pr_s = 2.0
        elif price >= 5:
            pr_s = 1.5
        elif price >= 2:
            pr_s = 0.8
        else:
            pr_s = 0.2

        # 4. Anlık hacim oranı (10 puan)
        if vol_ratio >= 2.0:
            vr_s = 1.0
        elif vol_ratio >= 1.0:
            vr_s = 0.7
        else:
            vr_s = 0.3

        raw   = vol_s + sp_s + pr_s + vr_s   # max = 4+3+2+1 = 10
        score = min(round(raw, 2), 10.0)
        ok    = score >= LIQUIDITY_MIN

        if not ok:
            if intraday_vol < 300_000:
                reason = f"Düşük hacim ({intraday_vol:,.0f})"
            elif spread_pct > 3.5:
                reason = f"Geniş spread ({spread_pct:.1f}%)"
            else:
                reason = f"Likidite yetersiz ({score:.1f}/10)"
        else:
            reason = f"OK ({score:.1f}/10)"

        return LiquidityResult(score=score, ok=ok, reason=reason)


# ══════════════════════════════════════════════════════════════
# SETUP DETECTOR (5m bar bazlı, yapı bazlı)
# ══════════════════════════════════════════════════════════════
@dataclass
class SetupResult:
    setup_type:        SetupType = SetupType.NONE
    breakout_price:    float = 0.0   # kırılan direnç seviyesi
    breakout_bar_idx:  int   = -1
    pullback_low:      float = 0.0
    rebreak_price:     float = 0.0
    volume_confirmed:  bool  = False
    surge_strength:    float = 0.0   # MOMENTUM_SURGE için
    detail:            str   = ""


class SetupDetector:
    """
    Gün içi 5m bar listesinden setup tespiti.
    Sadece WINDOW içindeki barları değerlendirir.

    BREAKOUT:
      - 10:00-10:10 arası oluşan opening range (high/low)
      - 10:10-10:30'da fiyat o range high'ını kırar
      - hacim onayı var

    PULLBACK_REBREAK:
      - Önce BREAKOUT oluştu
      - 1-3 bar içinde geri çekilme (ama EMA9'un çok altına inmez)
      - Pullback sırasında hacim düşer
      - Sonra tekrar breakout_high üzerine çıkar, hacim artar

    MOMENTUM_SURGE:
      - Açılışta güçlü hareket (open'dan >%1.5 yukarı)
      - Hacim ortalamanın 2x+
      - Hızlı devam (geri çekilme yok)
    """

    def detect(
        self,
        bars: list[Bar],
        ema9: float,
        vol_ma: float,
    ) -> SetupResult:
        result = SetupResult()

        if not bars:
            return result

        # Sadece gün içi barlar (10:00 sonrası)
        intraday = [b for b in bars if b.t >= time(10, 0)]
        if not intraday:
            return result

        # Opening range: 10:00-10:10 arası ilk 2 bar
        or_bars = [b for b in intraday if b.t < WINDOW_START]
        window_bars = [b for b in intraday if WINDOW_START <= b.t <= WINDOW_END]

        if not or_bars:
            return result

        or_high  = max(b.high  for b in or_bars)
        or_low   = min(b.low   for b in or_bars)
        or_vol   = sum(b.volume for b in or_bars)

        # ── MOMENTUM_SURGE ────────────────────────────────
        if window_bars:
            first_w = window_bars[0]
            open_ref = or_bars[0].open if or_bars else first_w.open
            surge = (first_w.close - open_ref) / open_ref * 100 if open_ref > 0 else 0

            avg_vol = vol_ma if vol_ma > 0 else or_vol
            vol_surge_ratio = first_w.volume / avg_vol if avg_vol > 0 else 1.0

            if surge >= 1.5 and vol_surge_ratio >= 2.0:
                result.setup_type       = SetupType.MOMENTUM_SURGE
                result.breakout_price   = first_w.close
                result.breakout_bar_idx = len(or_bars)
                result.volume_confirmed = True
                result.surge_strength   = surge
                result.detail = f"Surge +{surge:.2f}% vol={vol_surge_ratio:.1f}x"
                return result

        # ── BREAKOUT + PULLBACK_REBREAK ───────────────────
        breakout_bar_idx = -1
        breakout_price   = 0.0

        for i, b in enumerate(window_bars):
            # Hacim onayı: en az vol_ma'nın 1.3x'i
            vol_ok = (vol_ma <= 0) or (b.volume >= vol_ma * 1.3)

            if b.close > or_high and vol_ok:
                breakout_bar_idx = i
                breakout_price   = b.close
                result.breakout_price   = breakout_price
                result.breakout_bar_idx = len(or_bars) + i
                result.volume_confirmed = True
                break

        if breakout_bar_idx < 0:
            return result   # breakout yok

        # Breakout sonrası barlar (pullback/rebreak için)
        post_bo = window_bars[breakout_bar_idx + 1:]

        # Sadece BREAKOUT (pullback yoksa)
        if not post_bo:
            result.setup_type = SetupType.BREAKOUT
            result.detail = f"Breakout >{or_high:.2f}"
            return result

        # PULLBACK tespiti: 1-3 bar içinde geri çekilme
        pb_bars = post_bo[:MAX_PULLBACK_BARS]
        pb_lows  = [b.low   for b in pb_bars]
        pb_vols  = [b.volume for b in pb_bars]
        bo_vol   = window_bars[breakout_bar_idx].volume

        pullback_low     = min(pb_lows) if pb_lows else breakout_price
        pullback_ok      = pullback_low < breakout_price * 0.998   # en az %0.2 geri çekilme
        ema9_floor_ok    = pullback_low >= ema9 * (1 - PULLBACK_EMA9_MAX)
        pb_vol_drop      = all(v < bo_vol for v in pb_vols)        # pullback'te hacim düşmeli

        if not (pullback_ok and ema9_floor_ok and pb_vol_drop):
            # Pullback koşulu sağlanmadı → sadece BREAKOUT
            result.setup_type = SetupType.BREAKOUT
            result.detail = f"Breakout >{or_high:.2f} (no PB)"
            return result

        result.pullback_low = pullback_low

        # REBREAK: pullback sonrası kalan barlarda or_high üzerine kapanış
        rb_bars = post_bo[len(pb_bars):]
        avg_pb_vol = sum(pb_vols) / len(pb_vols) if pb_vols else bo_vol

        for b in rb_bars:
            rb_vol_ok = b.volume >= avg_pb_vol * REBREAK_VOL_MIN
            if b.close > or_high and rb_vol_ok:
                result.setup_type    = SetupType.PULLBACK_REBREAK
                result.rebreak_price = b.close
                result.detail = (f"PullRebreak: BO>{or_high:.2f} "
                                 f"PB_low={pullback_low:.2f} "
                                 f"RB={b.close:.2f}")
                return result

        # Rebreak henüz gelmedi → sadece BREAKOUT dön
        result.setup_type = SetupType.BREAKOUT
        result.detail = f"Breakout >{or_high:.2f} (PB waiting RB)"
        return result


# ══════════════════════════════════════════════════════════════
# SYMBOL STATE — bir hissenin state machine durumu
# ══════════════════════════════════════════════════════════════
@dataclass
class SymbolState:
    symbol:         str
    state:          SigState  = SigState.WATCHLIST
    setup_type:     SetupType = SetupType.NONE

    # BUY_SIGNAL için
    entry_price:    float = 0.0
    stop_price:     float = 0.0
    target_price:   float = 0.0
    signal_bar_idx: int   = 0     # sinyalin oluştuğu bar index'i

    # State persistence sayaçları
    confirm_count:  int   = 0     # SETUP'ta bekleme bar sayısı
    persist_count:  int   = 0     # BUY_SIGNAL'da yaşama bar sayısı
    reject_count:   int   = 0     # REJECT cooldown bar sayısı

    # Scoring
    sector_str:     float = 0.0
    rs_score:       float = 0.0
    liquidity:      float = 0.0
    rsi:            float = 50.0

    # Detail
    detail:         str   = ""
    updated_at:     Optional[datetime] = None

    def reset_to_watchlist(self):
        self.state         = SigState.WATCHLIST
        self.setup_type    = SetupType.NONE
        self.confirm_count = 0
        self.persist_count = 0
        self.entry_price   = 0.0
        self.stop_price    = 0.0
        self.target_price  = 0.0


# ══════════════════════════════════════════════════════════════
# OPENING STRATEGY ENGINE — ana entry point
# ══════════════════════════════════════════════════════════════
class OpeningStrategyEngine:
    """
    BIST Hybrid Opening Momentum Strategy.

    Her 5m bar için çağrılır:
        signals = engine.on_bar(sym, bar, context)

    context içeriği:
        market_regime: str          (BULL/WEAK_BULL/RANGE/BEAR/...)
        sector_strength: float      (0-100)
        rs_vs_index: float          (RS skoru)
        ema9_daily: float           (dünkü kapanışlardan EMA9)
        ema21_daily: float          (dünkü kapanışlardan EMA21)
        rsi_daily: float            (dünkü kapanışlardan RSI14)
        vol_ma: float               (20-bar hacim ortalaması)
        intraday_vol: float         (gün içi kümülatif hacim)
        atr: float                  (ATR14)
        intraday_bars: list[Bar]    (bugünün barları şu ana kadar)
    """

    def __init__(self):
        self._states:    dict[str, SymbolState] = {}
        self._vwaps:     dict[str, IntradayVWAP] = {}
        self._liquidity  = LiquidityScorer()
        self._setup_det  = SetupDetector()
        self._bar_idx:   int = 0   # global bar sayacı

    # ── Ana metod ─────────────────────────────────────────────
    def on_bar(
        self,
        symbol:  str,
        bar:     Bar,
        ctx:     dict,
    ) -> Optional[SymbolState]:
        """
        Bir sembol için yeni bar işle.
        Return: güncel SymbolState (None = ilgisiz)
        """
        self._bar_idx += 1

        # State al / oluştur
        if symbol not in self._states:
            self._states[symbol] = SymbolState(symbol=symbol)
        if symbol not in self._vwaps:
            self._vwaps[symbol] = IntradayVWAP()

        state = self._states[symbol]
        vwap_eng = self._vwaps[symbol]

        # VWAP güncelle (her bar)
        vwap_val = vwap_eng.update(bar)

        # Gün değişimi → WATCHLIST'e sıfırla
        if state.updated_at and state.updated_at.date() != bar.d:
            state.reset_to_watchlist()

        state.updated_at = bar.timestamp

        # ── REJECT cooldown ────────────────────────────────
        if state.state == SigState.REJECT:
            state.reject_count += 1
            if state.reject_count >= REJECT_BARS:
                state.reset_to_watchlist()
            return state

        # ── Pencere dışında → aktif tarama yok ────────────
        in_window = WINDOW_START <= bar.t <= WINDOW_END
        if not in_window:
            # Sadece persist sayacını güncelle
            if state.state == SigState.BUY_SIGNAL:
                state.persist_count += 1
                if state.persist_count > BUY_PERSIST_BARS * 3:
                    # Çok uzun BUY_SIGNAL → düşür
                    state.reset_to_watchlist()
            return state

        # ══ PENCERE İÇİ: tam pipeline ══════════════════════

        # 1. MARKET CONTEXT
        regime = ctx.get('market_regime', 'RANGE')
        if regime in ('BEAR', 'WEAK_BEAR', 'RISK_OFF'):
            if state.state not in (SigState.BUY_SIGNAL, SigState.IN_POSITION):
                state.reset_to_watchlist()
            return state

        # RANGE'de sadece çok güçlü setup'lar (sector_strength >= 70)
        if regime == 'RANGE':
            sector_threshold = 70.0
        else:
            sector_threshold = SECTOR_STR_MIN

        # 2. SECTOR STRENGTH
        sector_str = ctx.get('sector_strength', 0.0)
        state.sector_str = sector_str
        if sector_str < SECTOR_STR_HARD:
            state.reset_to_watchlist()
            return state
        if sector_str < sector_threshold:
            if state.state not in (SigState.BUY_SIGNAL,):
                state.state = SigState.WATCHLIST
            return state

        # 3. RELATIVE STRENGTH
        rs_val = ctx.get('rs_vs_index', 0.0)
        state.rs_score = rs_val
        if rs_val < RS_MIN:
            state.reset_to_watchlist()
            return state

        # 4. LIQUIDITY
        liq = self._liquidity.score(
            price        = bar.close,
            volume       = bar.volume,
            vol_ma       = ctx.get('vol_ma', 0),
            atr          = ctx.get('atr', bar.close * 0.02),
            intraday_vol = ctx.get('intraday_vol', 0),
        )
        state.liquidity = liq.score
        if not liq.ok:
            state.reset_to_watchlist()
            return state

        # 5. TREND — günlük EMA
        ema9_d  = ctx.get('ema9_daily',  0.0)
        ema21_d = ctx.get('ema21_daily', 0.0)
        trend_up = (ema9_d > ema21_d) if (ema9_d > 0 and ema21_d > 0) else False

        # Fiyat VWAP üzerinde mi?
        above_vwap = (bar.close > vwap_val) if vwap_val > 0 else True

        if not trend_up or not above_vwap:
            if state.state not in (SigState.BUY_SIGNAL,):
                state.state = SigState.WATCHLIST
            return state

        # 6. RSI
        rsi_val = ctx.get('rsi_daily', 50.0)
        state.rsi = rsi_val
        if not (RSI_MIN <= rsi_val <= RSI_MAX):
            if state.state not in (SigState.BUY_SIGNAL,):
                state.state = SigState.WATCHLIST
            return state

        # 7. SETUP TESPİTİ
        intraday_bars = ctx.get('intraday_bars', [])
        atr = ctx.get('atr', bar.close * 0.02)
        vol_ma = ctx.get('vol_ma', 0.0)

        setup = self._setup_det.detect(
            bars   = intraday_bars,
            ema9   = ema9_d,
            vol_ma = vol_ma,
        )

        if setup.setup_type == SetupType.NONE:
            state.state = SigState.WATCHLIST
            return state

        state.setup_type = setup.setup_type
        state.detail     = setup.detail

        # ── STATE MACHINE ──────────────────────────────────

        if state.state == SigState.BUY_SIGNAL:
            # BUY yaşıyor — persist sayacı
            state.persist_count += 1
            if state.persist_count >= BUY_PERSIST_BARS * 4:
                # Çok uzun sürdü → kapat
                state.reset_to_watchlist()
            return state

        if state.state == SigState.WATCHLIST:
            # Setup yoksa kalıyoruz
            if setup.setup_type == SetupType.NONE:
                return state
            state.state         = SigState.SETUP
            state.confirm_count = 1
            return state

        if state.state == SigState.SETUP:
            state.confirm_count += 1

            # PULLBACK_REBREAK tüm kriterleri karşıladıysa 1 bar teyit yeterli
            if setup.setup_type == SetupType.PULLBACK_REBREAK:
                needed = 1
            else:
                needed = CONFIRM_BARS

            if state.confirm_count >= needed:
                # Yeterli teyit → BUY_SIGNAL üret
                # Stop/Target hesapla
                entry  = bar.close   # bu bar'ın kapanışı
                stop   = entry - atr * ATR_STOP_MULT
                target = entry + atr * ATR_TARGET_MULT

                # R/R kontrolü
                risk = entry - stop
                if risk > 0:
                    reward = target - entry
                    rr = reward / risk
                else:
                    rr = 0

                if rr >= RR_MIN and risk / entry <= 0.10:
                    state.state         = SigState.BUY_SIGNAL
                    state.entry_price   = entry
                    state.stop_price    = stop
                    state.target_price  = target
                    state.persist_count = 0
                    state.signal_bar_idx= self._bar_idx
                else:
                    # R/R yetersiz → REJECT
                    state.state        = SigState.REJECT
                    state.reject_count = 0
                    state.detail      += f" | R/R={rr:.2f} yetersiz"

            return state

        return state

    # ── Yardımcı metodlar ─────────────────────────────────────
    def get_buy_signals(self) -> list[SymbolState]:
        return [s for s in self._states.values()
                if s.state == SigState.BUY_SIGNAL]

    def get_setup_signals(self) -> list[SymbolState]:
        return [s for s in self._states.values()
                if s.state == SigState.SETUP]

    def get_watchlist(self) -> list[SymbolState]:
        return [s for s in self._states.values()
                if s.state == SigState.WATCHLIST]

    def get_state(self, symbol: str) -> Optional[SymbolState]:
        return self._states.get(symbol)

    def mark_in_position(self, symbol: str):
        if symbol in self._states:
            self._states[symbol].state = SigState.IN_POSITION

    def mark_closed(self, symbol: str):
        if symbol in self._states:
            self._states[symbol].state = SigState.CLOSED
            self._states[symbol].reset_to_watchlist()

    def reset_day(self):
        """Yeni gün başında çağrılır."""
        for s in self._states.values():
            s.reset_to_watchlist()
        self._bar_idx = 0
