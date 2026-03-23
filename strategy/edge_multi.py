# ============================================================
# strategy/edge_multi.py — BIST v2 Edge Strateji Motoru
#
# STATE MACHINE (her sembol için):
#
#   IDLE ──(kısmi koşul)──► WATCHING
#   WATCHING ──(tüm koşul)──► CONFIRMING
#   CONFIRMING ──(1 bar teyit)──► SIGNAL  ← AL
#   SIGNAL ──(koşul bozuldu)──► COOLDOWN
#   COOLDOWN ──(N bar sonra)──► IDLE
#
# CORE_EDGE  → %80 sermaye, 1-30 gün tutma
#   · Uptrend (EMA9 > EMA21)
#   · RS > 1.15  (endeksi geçiyor)
#   · Konsolidasyon (ATR/fiyat < %5)
#   · Hacim spike (vol > 1.5× ortalama)
#   Durak: 2×ATR | Hedef: 5×ATR
#
# SWING_EDGE → %20 sermaye, gün içi vur-kaç
#   · RSI3 < 15 (aşırı satım zıplaması)
#   · VEYA Gap-Up + RS > 1.05
#   Durak: 1×ATR | Hedef: 1.5×ATR
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional

from config import (
    CORE_RS_THRESHOLD, CORE_CONSOLIDATION_THRESHOLD, CORE_VOL_THRESHOLD,
    CORE_STOP_ATR, CORE_TARGET_ATR,
    SWING_RSI3_THRESHOLD, SWING_GAP_RS_THRESHOLD,
    SWING_STOP_ATR, SWING_TARGET_ATR,
    CORE_WEIGHT, SWING_WEIGHT,
)


# ── State ────────────────────────────────────────────────────

class EdgeState(str, Enum):
    IDLE       = "IDLE"        # Takipte değil
    WATCHING   = "WATCHING"    # Kısmi koşullar sağlandı, izleniyor
    CONFIRMING = "CONFIRMING"  # Tüm koşullar sağlandı, teyit bekleniyor
    SIGNAL     = "SIGNAL"      # Onaylı AL sinyali
    COOLDOWN   = "COOLDOWN"    # Sinyal sonrası bekleme


class SetupType(str, Enum):
    NONE       = "NONE"
    CORE_EDGE  = "CORE_EDGE"
    SWING_EDGE = "SWING_EDGE"
    NEWS_EDGE  = "NEWS_EDGE"



# ── Sinyal Modeli ────────────────────────────────────────────

@dataclass
class EdgeSignal:
    symbol:     str
    state:      EdgeState = EdgeState.IDLE
    setup_type: SetupType = SetupType.NONE
    is_signal:  bool      = False   # sadece SIGNAL state'inde True

    # Fiyat seviyeleri (SIGNAL anında dondurulur)
    entry:     float = 0.0
    stop:      float = 0.0
    target:    float = 0.0
    daily_atr: float = 0.0
    rr_ratio:  float = 0.0

    # Meta
    rs_score:   float = 0.0
    rsi3:       float = 50.0
    sector_str: float = 0.0
    weight:     float = 0.0
    detail:     str   = ""

    # State sayaçları
    _confirm_bars: int = field(default=0, repr=False)  # CONFIRMING'de geçirilen bar sayısı
    _cooldown_bars: int = field(default=0, repr=False) # COOLDOWN'da geçirilen bar sayısı
    _date: Optional[date] = field(default=None, repr=False)

    # Watchlist için kısmi koşul takibi
    conditions_met:  list = field(default_factory=list)
    conditions_miss: list = field(default_factory=list)

    def set_state(self, new_state: EdgeState):
        if self.state != new_state:
            self.state = new_state
            if new_state == EdgeState.CONFIRMING:
                self._confirm_bars = 0
            if new_state == EdgeState.COOLDOWN:
                self._cooldown_bars = 0
            if new_state in (EdgeState.IDLE, EdgeState.WATCHING):
                self.is_signal = False

    @property
    def state_label(self) -> str:
        labels = {
            EdgeState.IDLE:       "—",
            EdgeState.WATCHING:   "İZLENİYOR",
            EdgeState.CONFIRMING: "TEYİT BEKLENİYOR",
            EdgeState.SIGNAL:     "AL SİNYALİ",
            EdgeState.COOLDOWN:   "BEKLEME",
        }
        return labels.get(self.state, self.state.value)


# ── Strateji Motoru ──────────────────────────────────────────

class EdgeMultiStrategy:
    """
    Her bar'da on_bar() çağrılır.
    Sürekli takip + kademeli onay ile AL sinyali üretir.

    CORE_EDGE öncelikli:
      WATCHING  → uptrend + RS OK (kısmi)
      CONFIRMING → tüm koşullar sağlandı
      SIGNAL    → 1 bar teyit sonrası

    SWING_EDGE:
      CONFIRMING → koşul sağlandı (hız önemli, 1 bar yeterli)
      SIGNAL    → aynı bar'da üretilir (hız kritik)
    """

    COOLDOWN_BARS = 3   # SIGNAL sonrası kaç bar beklenir

    def __init__(self):
        self._signals: dict[str, EdgeSignal] = {}
        self._buy_callbacks: list = []

    def on_bar(self, symbol: str, bar, ctx: dict) -> EdgeSignal:
        sig = self._get_or_create(symbol)

        # Gün dönüşümünde IDLE'a sıfırla
        bar_date = bar.timestamp.date()
        if sig._date and sig._date != bar_date:
            self._reset(sig)
        sig._date = bar_date

        # Context
        rs        = float(ctx.get("rs_vs_index", 1.0))
        sec_str   = float(ctx.get("sector_strength", 50.0))
        atr       = float(ctx.get("daily_atr", bar.close * 0.03))
        rsi3      = float(ctx.get("rsi_3", 50.0))
        e9        = float(ctx.get("ema9_daily", 0.0))
        e21       = float(ctx.get("ema21_daily", 0.0))
        vol_ma    = float(ctx.get("vol_ma", 1.0))
        intra_vol = float(ctx.get("intraday_vol", bar.volume))
        vol_spike = bool(ctx.get("vol_spike", False))
        gap_up    = bool(ctx.get("gap_up", False))

        # Meta her zaman güncellenir
        sig.rs_score   = rs
        sig.rsi3       = rsi3
        sig.sector_str = sec_str

        # ── COOLDOWN ──────────────────────────────────────────
        if sig.state == EdgeState.COOLDOWN:
            sig._cooldown_bars += 1
            if sig._cooldown_bars >= self.COOLDOWN_BARS:
                sig.set_state(EdgeState.IDLE)
            return sig

        # ── CORE koşul kontrolü ───────────────────────────────
        is_uptrend  = (e9 > e21) if (e9 > 0 and e21 > 0) else True
        is_rs_ok    = rs >= CORE_RS_THRESHOLD
        is_consol   = (atr / bar.close) < CORE_CONSOLIDATION_THRESHOLD if bar.close > 0 else False
        is_vol_ok   = (intra_vol > vol_ma * CORE_VOL_THRESHOLD) or vol_spike

        core_partial  = is_uptrend and is_rs_ok              # WATCHING için
        core_all      = core_partial and is_consol and is_vol_ok  # CONFIRMING için

        # Kriter listesi (UI için)
        met, miss = [], []
        
        # Eğer henüz IDLE/WATCHING ise genel tarama göster
        if sig.state in (EdgeState.IDLE, EdgeState.WATCHING) or sig.setup_type == SetupType.CORE_EDGE:
            (met if is_uptrend else miss).append("Uptrend")
            (met if is_rs_ok   else miss).append(f"RS>{CORE_RS_THRESHOLD}")
            (met if is_consol  else miss).append("Konsolidasyon")
            (met if is_vol_ok  else miss).append("Hacim")
            
        if sig.setup_type == SetupType.SWING_EDGE or sig.state in (EdgeState.IDLE, EdgeState.WATCHING):
            if rsi3 < SWING_RSI3_THRESHOLD:
                met.append("Aşırı Satım Dip (RSI3)")
            if gap_up and rs > SWING_GAP_RS_THRESHOLD:
                met.append("Gap-Up Momentum")
                
        sig.conditions_met  = met
        sig.conditions_miss = miss

        # ── SWING koşul kontrolü ─────────────────────────────
        swing_all = (rsi3 < SWING_RSI3_THRESHOLD) or (gap_up and rs > SWING_GAP_RS_THRESHOLD)

        # ── State Machine ─────────────────────────────────────

        if sig.state == EdgeState.IDLE or sig.state == EdgeState.WATCHING:

            if core_all:
                # Tüm CORE koşulları sağlandı → CONFIRMING
                sig.set_state(EdgeState.CONFIRMING)
                sig.setup_type = SetupType.CORE_EDGE
                sig.weight     = CORE_WEIGHT

            elif swing_all and sig.state != EdgeState.WATCHING:
                # SWING koşulu sağlandı → hemen CONFIRMING (1 bar yeterli)
                sig.set_state(EdgeState.CONFIRMING)
                sig.setup_type = SetupType.SWING_EDGE
                sig.weight     = SWING_WEIGHT

            elif core_partial:
                # Kısmi koşul → WATCHING
                if sig.state == EdgeState.IDLE:
                    sig.set_state(EdgeState.WATCHING)
                    sig.setup_type = SetupType.CORE_EDGE

            else:
                # Hiç koşul yok → IDLE'a dön
                if sig.state == EdgeState.WATCHING:
                    sig.set_state(EdgeState.IDLE)
                    sig.setup_type = SetupType.NONE

        elif sig.state == EdgeState.CONFIRMING:
            sig._confirm_bars += 1

            # Koşullar hâlâ sağlanıyor mu?
            if sig.setup_type == SetupType.CORE_EDGE:
                still_ok = core_all
            elif sig.setup_type == SetupType.SWING_EDGE:
                still_ok = swing_all
            else:
                still_ok = True  # NEWS_EDGE veya diğer durumlar için geçici onay


            if not still_ok:
                # Koşullar bozuldu → geri dön
                sig.set_state(EdgeState.WATCHING if core_partial else EdgeState.IDLE)
                return sig

            # 1 bar teyit sonrası → SIGNAL
            if sig._confirm_bars >= 1:
                sig.set_state(EdgeState.SIGNAL)
                sig.is_signal = True

                # Fiyat seviyelerini dondur
                if sig.setup_type == SetupType.CORE_EDGE:
                    sig.entry    = bar.close
                    sig.stop     = bar.close - (atr * CORE_STOP_ATR)
                    sig.target   = bar.close + (atr * CORE_TARGET_ATR)
                    sig.rr_ratio = round(CORE_TARGET_ATR / CORE_STOP_ATR, 2)
                    sig.detail   = (
                        f"CORE EDGE | RS:{rs:.2f} | "
                        f"ATR/P:{atr/bar.close*100:.1f}% | "
                        f"Vol:{intra_vol/vol_ma:.1f}x"
                    ) if vol_ma > 0 else f"CORE EDGE | RS:{rs:.2f}"
                else:
                    sig.entry    = bar.close
                    sig.stop     = bar.close - (atr * SWING_STOP_ATR)
                    sig.target   = bar.close + (atr * SWING_TARGET_ATR)
                    sig.rr_ratio = round(SWING_TARGET_ATR / SWING_STOP_ATR, 2)
                    sig.detail   = (
                        f"SWING EDGE | RSI3:{rsi3:.1f} (aşırı satım)"
                        if rsi3 < SWING_RSI3_THRESHOLD
                        else f"SWING EDGE | Gap-Up + RS:{rs:.2f}"
                    )
                sig.daily_atr = atr

                # Callback
                for cb in self._buy_callbacks:
                    try: cb(sig)
                    except Exception: pass

        elif sig.state == EdgeState.SIGNAL:
            # Sinyal aktif — koşullar bozulunca COOLDOWN
            if sig.setup_type == SetupType.CORE_EDGE:
                still_ok = core_all
            elif sig.setup_type == SetupType.SWING_EDGE:
                still_ok = swing_all
            else:
                still_ok = True  # NEWS_EDGE için koşul bozulması portfolio/news_engine tarafından yapılır

            if not still_ok:
                sig.is_signal = False
                sig.set_state(EdgeState.COOLDOWN)

        return sig

    # ── Yardımcılar ──────────────────────────────────────────

    def _reset(self, sig: EdgeSignal):
        sig.state          = EdgeState.IDLE
        sig.setup_type     = SetupType.NONE
        sig.is_signal      = False
        sig.entry = sig.stop = sig.target = 0.0
        sig.weight = sig.rr_ratio = 0.0
        sig.detail = ""
        sig._confirm_bars  = 0
        sig._cooldown_bars = 0
        sig.conditions_met  = []
        sig.conditions_miss = []

    def _get_or_create(self, sym: str) -> EdgeSignal:
        if sym not in self._signals:
            self._signals[sym] = EdgeSignal(symbol=sym)
        return self._signals[sym]

    def on_buy_signal(self, cb):
        self._buy_callbacks.append(cb)

    def get_signals(self) -> list[EdgeSignal]:
        return [s for s in self._signals.values() if s.is_signal]

    def get_watching(self) -> list[EdgeSignal]:
        return [s for s in self._signals.values()
                if s.state in (EdgeState.WATCHING, EdgeState.CONFIRMING)]

    def get_all_active(self) -> list[EdgeSignal]:
        return [s for s in self._signals.values()
                if s.state != EdgeState.IDLE]
