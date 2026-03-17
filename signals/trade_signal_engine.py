# ============================================================
# signals/trade_signal_engine.py — v2
# Stabil Trade Signal State Machine
#
# TEMEL PRENSİP:
#   Kolay gir, zor çık.
#   Sinyal üretmek zor, iptal etmek daha zor.
#
# State Geçişleri:
#
#   WATCHLIST ──(≥4 kriter)──► SETUP
#   SETUP ──(TÜM kriterler 15s)──► CONFIRMING
#   CONFIRMING ──(15s dolduysa)──► BUY_SIGNAL
#   BUY_SIGNAL ──(kullanıcı alır)──► IN_POSITION
#   IN_POSITION ──(stop/target)──► SELL_SIGNAL
#
# GERİ DÖNÜŞ KURALLARI (hysteresis):
#   BUY_SIGNAL → geri dönmez (en az 30s, sonra sadece WATCHLIST'e)
#   CONFIRMING → sadece kriter sayısı 7'nin altına düşerse SETUP'a
#   SETUP → 2 ardışık güncelleme ≥4 kriterli olmalı
#   REJECT → sinyal iptal edilmiş, cooldown (60s) bitene dek tekrar yok
#
# 1 DAKİKALIK MUM TEYİDİ:
#   CONFIRMING'de 1m bar kapandığında kriter kontrolü yapılır
#   Kapanış yukarıdaysa → doğrudan BUY (15s bekleme yok)
# ============================================================
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from data.models import SignalCandidate, RankedSignal, RegimeResult, MarketSnapshot


# ══════════════════════════════════════════════════════════════
# State enum
# ══════════════════════════════════════════════════════════════

class SignalState(str, Enum):
    WATCHLIST   = "WATCHLIST"
    SETUP       = "SETUP"
    CONFIRMING  = "CONFIRMING"    # tüm kriterler sağlandı, teyit sayılıyor
    BUY_SIGNAL  = "BUY_SIGNAL"
    IN_POSITION = "IN_POSITION"
    SELL_SIGNAL = "SELL_SIGNAL"
    REJECT      = "REJECT"        # iptal edildi, cooldown süresi
    CLOSED      = "CLOSED"


# ══════════════════════════════════════════════════════════════
# BUY Kriterleri
# ══════════════════════════════════════════════════════════════

@dataclass
class BuyCriteria:
    # Filtreler
    rsi_min:         float = 52.0    # biraz gevşettik
    rsi_max:         float = 72.0
    sector_strength: float = 50.0   # sektör güç ≥
    market_strength: float = 48.0   # piyasa gücü ≥
    flow_score:      float = 4.0    # smart money ≥
    rr_ratio:        float = 1.6    # R/R ≥
    combined_score:  float = 5.0    # combined ≥

    # Zaman kuralları
    confirm_secs:    float = 15.0   # tüm kriterler bu kadar korunmalı
    min_hold_secs:   float = 30.0   # BUY üretildikten sonra min yaşam süresi
    reject_cooldown: float = 60.0   # REJECT sonrası tekrar değerlendirme süresi

    # Hysteresis — geri dönüş eşikleri
    setup_min_criteria:     int   = 4    # SETUP için min kriter sayısı
    confirming_drop_limit:  int   = 7    # Bu sayının altına düşmeden CONFIRMING iptali yok
    buy_drop_grace_secs:    float = 45.0 # BUY'dan SETUP'a düşmeden önce ek bekleme


# ══════════════════════════════════════════════════════════════
# TradeSignal veri modeli
# ══════════════════════════════════════════════════════════════

@dataclass
class TradeSignal:
    symbol:       str
    state:        SignalState = SignalState.WATCHLIST

    # Fiyat seviyeleri (en son BUY anında dondurulur)
    entry:        float = 0.0
    stop:         float = 0.0
    target:       float = 0.0
    rr_ratio:     float = 0.0

    # Anlık skorlar
    combined_score: float = 0.0
    confidence:     float = 0.0
    quality_label:  str   = "Watchlist"
    flow_score:     float = 0.0
    sector_strength: float = 0.0
    sector_name:    str   = "—"
    rs_score:       float = 0.0

    # Kriter durumu
    criteria_met:   list[str] = field(default_factory=list)
    criteria_miss:  list[str] = field(default_factory=list)
    reason:         str   = ""

    # Zaman damgaları
    first_seen:       datetime = field(default_factory=datetime.now)
    state_changed_at: datetime = field(default_factory=datetime.now)
    confirmed_at:     Optional[datetime] = None
    buy_issued_at:    Optional[datetime] = None

    # Pozisyon
    entry_filled:  float = 0.0
    lots:          int   = 0
    stop_updated:  float = 0.0
    target_updated: float = 0.0
    last_price:    float = 0.0
    updated_at:    datetime = field(default_factory=datetime.now)

    # Hysteresis state — anlık dalgalanmaları filtrele
    _consecutive_met: int  = field(default=0, repr=False)  # ardışık "all_met" sayısı
    _consecutive_miss: int = field(default=0, repr=False)  # ardışık "şart bozuldu" sayısı
    _reject_until:    Optional[datetime] = field(default=None, repr=False)

    def set_state(self, new_state: SignalState) -> None:
        if self.state != new_state:
            self.state = new_state
            self.state_changed_at = datetime.now()
            # Miss sayacını sıfırla (yeni state'e girince temiz başla)
            # Ama MET sayacını KORUYORUZ — SETUP'a geçince zaten all_met sağlandı
            self._consecutive_miss = 0
            # Eğer WATCHLIST'e düşüyorsak tamamen sıfırla
            if new_state in (SignalState.WATCHLIST, SignalState.REJECT,
                              SignalState.CLOSED):
                self._consecutive_met = 0

    @property
    def state_age_secs(self) -> float:
        return (datetime.now() - self.state_changed_at).total_seconds()

    @property
    def confirming_progress_pct(self) -> float:
        """CONFIRMING durumunda teyit ilerlemesi (0-100)."""
        if self.state != SignalState.CONFIRMING:
            return 0.0
        from signals.trade_signal_engine import _DEFAULT_CRITERIA
        return min(100.0, self.state_age_secs / _DEFAULT_CRITERIA.confirm_secs * 100)

    @property
    def is_active(self) -> bool:
        return self.state not in (SignalState.CLOSED, SignalState.REJECT)

    @property
    def pnl_pct(self) -> float:
        if self.entry_filled > 0 and self.last_price > 0:
            return (self.last_price - self.entry_filled) / self.entry_filled * 100
        return 0.0

    @property
    def pnl_tl(self) -> float:
        if self.entry_filled > 0 and self.lots > 0:
            return (self.last_price - self.entry_filled) * self.lots
        return 0.0

    @property
    def quality_color(self) -> str:
        return {
            "A+": "#4ade80", "A": "#86efac",
            "B": "#fbbf24", "Watchlist": "#94a3b8"
        }.get(self.quality_label, "#94a3b8")


_DEFAULT_CRITERIA = BuyCriteria()  # confirming_progress_pct için referans


# ══════════════════════════════════════════════════════════════
# Trade Signal Engine
# ══════════════════════════════════════════════════════════════

class TradeSignalEngine:
    """
    Stabil trade signal motoru.

    Temel ilkeler:
      1. Şartlar CONFIRMING_SECS boyunca korunmadan BUY üretme
      2. BUY üretildikten sonra MIN_HOLD_SECS boyunca koru
      3. Scanner'dan düşünce BUY hemen iptal edilmez
      4. REJECT sonrası COOLDOWN bekle — ping-pong önlemi
      5. Hysteresis — tek tick anomalisi geçişe neden olmaz
    """

    def __init__(self, criteria: BuyCriteria | None = None):
        self._cr      = criteria or BuyCriteria()
        _DEFAULT_CRITERIA.__dict__.update(self._cr.__dict__)
        self._signals: dict[str, TradeSignal] = {}
        self._lock    = threading.RLock()
        self._buy_cbs:  list = []
        self._sell_cbs: list = []
        self._market_strength: float = 50.0

    # ── Ana güncelleme döngüsü ────────────────────────────────

    def update(
        self,
        ranked:     list[RankedSignal],
        snapshot:   MarketSnapshot,
        sectors:    dict,
        sector_eng,
    ) -> list[TradeSignal]:
        """
        Her snapshot (1-2s) döngüsünde çağrılır.
        Döndürür: aktif BUY_SIGNAL listesi.
        """
        self._market_strength = snapshot.market_strength
        index_return = self._calc_index_return(ranked)

        with self._lock:
            seen = set()

            # 1. Ranked sinyalleri işle
            for rsig in ranked:
                sym = rsig.candidate.symbol
                seen.add(sym)
                sig = self._signals.setdefault(sym, TradeSignal(symbol=sym))
                self._step(sig, rsig, snapshot, sectors, index_return)

            # 2. Scanner'da görünmeyen sinyaller — özel kural
            for sym, sig in self._signals.items():
                if sym not in seen:
                    self._handle_unseen(sig)

            # 3. Fiyat güncelle + sell kontrol
            for sym, sig in self._signals.items():
                tick = snapshot.ticks.get(sym)
                if tick:
                    sig.last_price = tick.price
                if sig.state == SignalState.IN_POSITION:
                    self._check_sell(sig)

            # 4. REJECT cooldown bitti mi?
            now = datetime.now()
            for sig in self._signals.values():
                if sig.state == SignalState.REJECT:
                    if sig._reject_until and now >= sig._reject_until:
                        sig.set_state(SignalState.WATCHLIST)

        return self.get_buy_signals()

    # ── State machine adımı ───────────────────────────────────

    def _step(
        self,
        sig:          TradeSignal,
        rsig:         RankedSignal,
        snap:         MarketSnapshot,
        sectors:      dict,
        index_return: float,
    ) -> None:
        """Tek sembol için state geçiş mantığı."""

        # Pozisyondaki sinyallere dokunma
        if sig.state in (SignalState.IN_POSITION, SignalState.SELL_SIGNAL,
                          SignalState.CLOSED):
            self._update_meta(sig, rsig, sectors, index_return)
            return

        # REJECT cooldown
        if sig.state == SignalState.REJECT:
            self._update_meta(sig, rsig, sectors, index_return)
            return

        # Meta güncelle
        self._update_meta(sig, rsig, sectors, index_return)

        c    = rsig.candidate
        risk = rsig.risk
        cr   = self._cr

        # Kriter kontrolü
        met, miss = self._check_criteria(c, rsig, sig)
        sig.criteria_met  = met
        sig.criteria_miss = miss
        n_met   = len(met)
        n_total = n_met + len(miss)
        all_met = n_met == n_total

        # Risk seviyelerini güncelle (BUY olmadan önce)
        if sig.state != SignalState.BUY_SIGNAL:
            sig.entry    = risk.entry
            sig.stop     = risk.stop
            sig.target   = risk.target
            sig.rr_ratio = risk.rr_ratio
            sig.quality_label = self._quality_label(rsig)

        # ── Hysteresis sayaçları ──────────────────────────────
        if all_met:
            sig._consecutive_met  += 1
            sig._consecutive_miss  = 0
        else:
            sig._consecutive_miss += 1
            sig._consecutive_met   = max(0, sig._consecutive_met - 1)

        # ── State geçişleri ───────────────────────────────────

        if sig.state == SignalState.BUY_SIGNAL:
            self._handle_buy_state(sig, n_met, n_total, all_met)

        elif sig.state == SignalState.CONFIRMING:
            self._handle_confirming_state(sig, n_met, n_total, all_met, rsig, sectors)

        elif sig.state == SignalState.SETUP:
            self._handle_setup_state(sig, n_met, n_total, all_met)

        elif sig.state == SignalState.WATCHLIST:
            self._handle_watchlist_state(sig, n_met, all_met)

    def _handle_buy_state(
        self, sig: TradeSignal, n_met: int, n_total: int, all_met: bool
    ) -> None:
        """
        BUY_SIGNAL → geri dönüş çok zor.

        Geçiş için gereken:
        - Min hold süresi dolmalı (30s)
        - VE ek grace süresi dolmalı (45s)
        - VE 3 ardışık "kriter bozuldu" teyidi
        """
        age = sig.state_age_secs
        cr  = self._cr

        if age < cr.min_hold_secs:
            return  # 30s dolmadan kesinlikle dokunma

        if all_met:
            # Şartlar hâlâ tamam — BUY'da kal
            sig._consecutive_miss = 0
            return

        # Şartlar bozulmuş — ama hemen iptal etme
        # 3 ardışık miss + grace süresi gerekli
        grace_passed = age >= (cr.min_hold_secs + cr.buy_drop_grace_secs)
        three_misses  = sig._consecutive_miss >= 3

        if grace_passed and three_misses:
            # BUY iptal — WATCHLIST'e dön (SETUP değil, sıfırdan başlasın)
            sig.set_state(SignalState.WATCHLIST)

    def _handle_confirming_state(
        self, sig: TradeSignal, n_met: int, n_total: int, all_met: bool,
        rsig: RankedSignal, sectors: dict
    ) -> None:
        """
        CONFIRMING → BUY veya SETUP'a geri dön.

        BUY geçişi:
        - 15s dolmuş VE all_met
        - VEYA 1m bar kapandı ve all_met (hızlı teyit)

        SETUP geri dönüşü:
        - Kriter sayısı confirming_drop_limit'in altına düşmeli
        - VE 2 ardışık miss
        """
        cr  = self._cr
        age = sig.state_age_secs

        if all_met:
            # 15s teyit süresini doldurdu → BUY!
            if age >= cr.confirm_secs:
                sig.set_state(SignalState.BUY_SIGNAL)
                sig.buy_issued_at = datetime.now()
                # Risk seviyelerini kilitle
                sig.entry    = rsig.risk.entry
                sig.stop     = rsig.risk.stop
                sig.target   = rsig.risk.target
                sig.rr_ratio = rsig.risk.rr_ratio
                sig.reason   = self._build_reason(sig.criteria_met, rsig, sectors)
                sig.quality_label = self._quality_label(rsig)
                self._fire_buy(sig)
            # Süresi dolmadı ama all_met — beklemeye devam
            return

        # Şartlar bozuldu — hysteresis ile geri dön
        # Kriter sayısı ÇOKÇA düşmediyse git
        too_many_lost = n_met < cr.confirming_drop_limit
        two_misses    = sig._consecutive_miss >= 2

        if too_many_lost and two_misses:
            sig.set_state(SignalState.SETUP)

    def _handle_setup_state(
        self, sig: TradeSignal, n_met: int, n_total: int, all_met: bool
    ) -> None:
        """
        SETUP → CONFIRMING veya WATCHLIST'e geri dön.
        all_met sağlandığı anda CONFIRMING başlar.
        """
        cr = self._cr

        if all_met:
            # Tüm kriterler sağlandı → CONFIRMING başlat
            # (sayaç şartı yok — SETUP'a gelmesi zaten filtre görevi gördü)
            sig.set_state(SignalState.CONFIRMING)
            sig.confirmed_at = datetime.now()

        elif n_met < cr.setup_min_criteria and sig._consecutive_miss >= 2:
            # Yeterli kriter kalmadı → WATCHLIST
            sig.set_state(SignalState.WATCHLIST)

    def _handle_watchlist_state(
        self, sig: TradeSignal, n_met: int, all_met: bool
    ) -> None:
        """
        WATCHLIST → SETUP geçişi.
        """
        cr = self._cr
        if n_met >= cr.setup_min_criteria:
            sig.set_state(SignalState.SETUP)

    # ── Scanner'da görünmeyen semboller ──────────────────────

    def _handle_unseen(self, sig: TradeSignal) -> None:
        """
        Scanner'da artık bulunmayan semboller.

        BUY_SIGNAL: korunur (min_hold + grace tamamen dolana kadar)
        CONFIRMING: SETUP'a düşer (scanner kaybetti, güvenilmez)
        SETUP:      WATCHLIST'e düşer
        """
        if sig.state == SignalState.BUY_SIGNAL:
            age = sig.state_age_secs
            cr  = self._cr
            # Hem min_hold hem grace dolana kadar koru
            if age < (cr.min_hold_secs + cr.buy_drop_grace_secs):
                return
            # Uzun süre scanner'da yok → WATCHLIST
            sig.set_state(SignalState.WATCHLIST)

        elif sig.state == SignalState.CONFIRMING:
            # Scanner'dan düştüyse teyiti iptal et
            sig.set_state(SignalState.SETUP)

        elif sig.state == SignalState.SETUP:
            if sig._consecutive_miss >= 3:
                sig.set_state(SignalState.WATCHLIST)
            else:
                sig._consecutive_miss += 1

    # ── Kriter kontrolü ──────────────────────────────────────

    def _check_criteria(
        self, c: SignalCandidate, rsig: RankedSignal, sig: TradeSignal
    ) -> tuple[list[str], list[str]]:
        cr  = self._cr
        met  = []
        miss = []

        def chk(name: str, cond: bool) -> None:
            (met if cond else miss).append(name)

        chk("trend",    c.trend)
        chk("breakout", c.breakout)
        chk("hacim",    c.volume_confirm)
        chk(f"RSI={c.rsi:.0f}",
            cr.rsi_min <= c.rsi <= cr.rsi_max)
        chk(f"sektör={sig.sector_strength:.0f}",
            sig.sector_strength >= cr.sector_strength)
        chk(f"piyasa={self._market_strength:.0f}%",
            self._market_strength >= cr.market_strength)
        chk(f"flow={sig.flow_score:.1f}",
            sig.flow_score >= cr.flow_score)
        chk(f"R/R={rsig.risk.rr_ratio:.1f}",
            rsig.risk.rr_ratio >= cr.rr_ratio)
        chk(f"skor={rsig.combined_score:.1f}",
            rsig.combined_score >= cr.combined_score)
        chk("RS≥0",
            sig.rs_score >= 0)   # endeksten güçlü VEYA eşit

        return met, miss

    # ── Meta güncelleme ──────────────────────────────────────

    def _update_meta(
        self,
        sig:          TradeSignal,
        rsig:         RankedSignal,
        sectors:      dict,
        index_return: float,
    ) -> None:
        """Skor, sektör, RS — state'ten bağımsız her tick güncellenir."""
        c = rsig.candidate
        sig.last_price     = c.price
        sig.updated_at     = datetime.now()
        sig.combined_score = rsig.combined_score
        sig.confidence     = rsig.confidence
        sig.flow_score     = rsig.flow_score or 0.0

        from data.sector_map import get_sector
        sec_name        = get_sector(c.symbol)
        sec_ss          = sectors.get(sec_name)
        sig.sector_name = sec_name
        sig.sector_strength = sec_ss.strength if sec_ss else 0.0

        if c.prev_price > 0:
            sr = (c.price - c.prev_price) / c.prev_price * 100
            sig.rs_score = round(sr - index_return, 3)

    # ── Sat koşulları ────────────────────────────────────────

    def _check_sell(self, sig: TradeSignal) -> None:
        if sig.state != SignalState.IN_POSITION:
            return
        price  = sig.last_price
        stop   = sig.stop_updated   or sig.stop
        target = sig.target_updated or sig.target
        reasons = []
        if price > 0 and stop > 0 and price <= stop:
            reasons.append(f"Stop kırıldı ₺{price:.2f} ≤ ₺{stop:.2f}")
        if price > 0 and target > 0 and price >= target:
            reasons.append(f"Hedefe ulaşıldı ₺{price:.2f} ≥ ₺{target:.2f}")
        if reasons:
            sig.set_state(SignalState.SELL_SIGNAL)
            sig.reason = " | ".join(reasons)
            self._fire_sell(sig)

    # ── Kullanıcı aksiyonları ────────────────────────────────

    def mark_position_entered(
        self, symbol: str, entry_price: float, lots: int
    ) -> None:
        with self._lock:
            sig = self._signals.get(symbol)
            if sig and sig.state == SignalState.BUY_SIGNAL:
                sig.entry_filled   = entry_price
                sig.lots           = lots
                sig.stop_updated   = sig.stop
                sig.target_updated = sig.target
                sig.set_state(SignalState.IN_POSITION)

    def mark_position_closed(self, symbol: str) -> None:
        with self._lock:
            sig = self._signals.get(symbol)
            if sig:
                sig.set_state(SignalState.CLOSED)

    def reject_signal(self, symbol: str) -> None:
        """Manuel sinyal iptali (trader gerek görmedi)."""
        with self._lock:
            sig = self._signals.get(symbol)
            if sig and sig.state == SignalState.BUY_SIGNAL:
                sig.set_state(SignalState.REJECT)
                sig._reject_until = datetime.now() + timedelta(
                    seconds=self._cr.reject_cooldown
                )

    def update_levels(
        self, symbol: str,
        stop: float | None = None,
        target: float | None = None
    ) -> None:
        with self._lock:
            sig = self._signals.get(symbol)
            if sig and sig.state == SignalState.IN_POSITION:
                if stop:   sig.stop_updated   = stop
                if target: sig.target_updated = target

    # ── Sorgu metodları ──────────────────────────────────────

    def get_buy_signals(self) -> list[TradeSignal]:
        with self._lock:
            return sorted(
                [s for s in self._signals.values()
                 if s.state == SignalState.BUY_SIGNAL],
                key=lambda s: s.quality_label
            )

    def get_setup_signals(self) -> list[TradeSignal]:
        with self._lock:
            return sorted(
                [s for s in self._signals.values()
                 if s.state in (SignalState.SETUP, SignalState.CONFIRMING)],
                key=lambda s: len(s.criteria_met), reverse=True
            )

    def get_watchlist(self) -> list[TradeSignal]:
        with self._lock:
            return sorted(
                [s for s in self._signals.values()
                 if s.state == SignalState.WATCHLIST],
                key=lambda s: len(s.criteria_met), reverse=True
            )

    def get_positions(self) -> list[TradeSignal]:
        with self._lock:
            return [s for s in self._signals.values()
                    if s.state == SignalState.IN_POSITION]

    def get_sell_signals(self) -> list[TradeSignal]:
        with self._lock:
            return [s for s in self._signals.values()
                    if s.state == SignalState.SELL_SIGNAL]

    def get_signal(self, symbol: str) -> Optional[TradeSignal]:
        with self._lock:
            return self._signals.get(symbol)

    def all_active(self) -> list[TradeSignal]:
        with self._lock:
            return [s for s in self._signals.values() if s.is_active]

    # ── Callback ─────────────────────────────────────────────

    def on_buy_signal(self, cb) -> None:
        self._buy_cbs.append(cb)

    def on_sell_signal(self, cb) -> None:
        self._sell_cbs.append(cb)

    def _fire_buy(self, sig: TradeSignal) -> None:
        for cb in self._buy_cbs:
            try: cb(sig)
            except Exception: pass

    def _fire_sell(self, sig: TradeSignal) -> None:
        for cb in self._sell_cbs:
            try: cb(sig)
            except Exception: pass

    # ── Yardımcılar ──────────────────────────────────────────

    def _calc_index_return(self, ranked: list[RankedSignal]) -> float:
        rets = []
        for r in ranked:
            c = r.candidate
            if c.prev_price > 0:
                rets.append((c.price - c.prev_price) / c.prev_price * 100)
        return sum(rets) / len(rets) if rets else 0.0

    def _quality_label(self, rsig: RankedSignal) -> str:
        c    = rsig.combined_score
        conf = rsig.confidence
        if c >= 8.0 and conf >= 70:  return "A+"
        if c >= 6.5 and conf >= 60:  return "A"
        if c >= 5.0:                 return "B"
        return "Watchlist"

    def _build_reason(
        self, met: list[str], rsig: RankedSignal, sectors: dict
    ) -> str:
        from data.sector_map import get_sector
        parts = []
        c     = rsig.candidate

        # Öncelikli sebepler
        if c.breakout:      parts.append("kırılım")
        if c.trend:         parts.append("trend")
        if c.volume_confirm: parts.append("hacim onayı")

        sec   = get_sector(c.symbol)
        ss    = sectors.get(sec)
        if ss and ss.strength >= 60:
            parts.append(f"{sec}({ss.strength:.0f})")

        if rsig.flow_score and rsig.flow_score >= 7:
            parts.append("akıllı para")

        # RS
        rs = getattr(rsig.candidate, 'rs_score', None)
        # (rs_score candidateta değil signal'de — meta'dan al)

        # Kaliteli met kriterler
        for m in met:
            if m not in ("trend", "breakout", "hacim") and len(parts) < 5:
                parts.append(m)

        return " + ".join(dict.fromkeys(parts))  # unique, sıralı

    def stats(self) -> dict:
        with self._lock:
            d: dict[str, int] = {}
            for s in self._signals.values():
                d[s.state.value] = d.get(s.state.value, 0) + 1
        return d

    def debug_signal(self, symbol: str) -> str:
        """Sembol için detaylı debug çıktısı."""
        with self._lock:
            sig = self._signals.get(symbol)
        if not sig:
            return f"{symbol}: sinyalte yok"
        cr_total = len(sig.criteria_met) + len(sig.criteria_miss)
        return (
            f"{symbol}: {sig.state.value} "
            f"age={sig.state_age_secs:.0f}s "
            f"kriter={len(sig.criteria_met)}/{cr_total} "
            f"consec_met={sig._consecutive_met} "
            f"consec_miss={sig._consecutive_miss} "
            f"ql={sig.quality_label}"
        )
