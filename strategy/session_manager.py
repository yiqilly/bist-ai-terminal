# ============================================================
# strategy/session_manager.py
# Canlı seans yönetimi
#
# Görevler:
#   1. Trade pencerelerini takip et (10:10-10:30)
#   2. Günlük reset zamanlama (09:59'da reset)
#   3. Pending entry zamanlaması
#   4. EOD uyarısı (17:20'de pozisyon kapat uyarısı)
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, date, timedelta
from enum import Enum
from typing import Callable, Optional
import threading


class SessionPhase(str, Enum):
    PRE_MARKET    = "PRE_MARKET"     # 09:00 öncesi
    OPENING       = "OPENING"        # 09:59-10:10 (açılış, veri toplama)
    SIGNAL_WINDOW = "SIGNAL_WINDOW"  # 10:10-10:30 (sinyal penceresi)
    INTRADAY      = "INTRADAY"       # 10:30-17:20 (pozisyon yönetimi)
    EOD_WARNING   = "EOD_WARNING"    # 17:20-17:25 (EOD uyarısı)
    CLOSED        = "CLOSED"         # 17:25 sonrası


# Seans saatleri
T_RESET         = time(9, 59)    # günlük reset
T_OPENING_END   = time(10, 10)   # açılış verisi toplama bitiş
T_SIGNAL_START  = time(10, 10)   # sinyal penceresi başlangıç
T_SIGNAL_END    = time(10, 30)   # sinyal penceresi bitiş
T_EOD_WARN      = time(17, 20)   # EOD uyarı başlangıç
T_EOD_CLOSE     = time(17, 25)   # EOD zorunlu kapatma
T_MARKET_CLOSE  = time(18, 0)    # piyasa kapanış


@dataclass
class SessionState:
    phase:           SessionPhase = SessionPhase.PRE_MARKET
    day:             Optional[date] = None
    signal_window:   bool = False    # şu an sinyal penceresinde mi?
    eod_warning:     bool = False    # EOD uyarısı aktif mi?
    day_reset_done:  bool = False    # bugün reset yapıldı mı?
    last_phase:      SessionPhase = SessionPhase.PRE_MARKET


class SessionManager:
    """
    Canlı seans yönetimi.

    app.py _update() içinde her tick'te çağrılır:
        sm = SessionManager()
        sm.on_callbacks(on_reset=..., on_signal_open=..., on_eod=...)

        # Her tick:
        phase = sm.tick()
        if not sm.state.signal_window:
            return  # pencere dışı, sinyal arama
    """

    def __init__(self):
        self.state    = SessionState()
        self._lock    = threading.Lock()

        # Callback'ler
        self._on_reset:        Optional[Callable] = None
        self._on_signal_open:  Optional[Callable] = None
        self._on_signal_close: Optional[Callable] = None
        self._on_eod:          Optional[Callable] = None

    def on_callbacks(
        self,
        on_reset:        Optional[Callable] = None,
        on_signal_open:  Optional[Callable] = None,
        on_signal_close: Optional[Callable] = None,
        on_eod:          Optional[Callable] = None,
    ):
        self._on_reset        = on_reset
        self._on_signal_open  = on_signal_open
        self._on_signal_close = on_signal_close
        self._on_eod          = on_eod

    def tick(self, now: Optional[datetime] = None) -> SessionPhase:
        """
        Her UI tick'inde çağrılır.
        Geçiş varsa callback'leri tetikler.
        Mevcut SessionPhase döner.
        """
        if now is None:
            now = datetime.now()

        t   = now.time()
        d   = now.date()

        with self._lock:
            # ── Gün değişimi reset ─────────────────────────────
            if d != self.state.day:
                self.state.day           = d
                self.state.day_reset_done= False
                self.state.eod_warning   = False

            # ── Reset (09:59) ──────────────────────────────────
            if t >= T_RESET and not self.state.day_reset_done:
                self.state.day_reset_done = True
                if self._on_reset:
                    try: self._on_reset()
                    except: pass

            # ── Faz hesapla ────────────────────────────────────
            new_phase = self._calc_phase(t)
            prev      = self.state.phase

            # ── Sinyal penceresi açıldı ────────────────────────
            if (new_phase == SessionPhase.SIGNAL_WINDOW and
                    prev != SessionPhase.SIGNAL_WINDOW):
                self.state.signal_window = True
                if self._on_signal_open:
                    try: self._on_signal_open()
                    except: pass

            # ── Sinyal penceresi kapandı ───────────────────────
            elif (new_phase != SessionPhase.SIGNAL_WINDOW and
                    prev == SessionPhase.SIGNAL_WINDOW):
                self.state.signal_window = False
                if self._on_signal_close:
                    try: self._on_signal_close()
                    except: pass

            # ── EOD uyarısı ────────────────────────────────────
            if (t >= T_EOD_WARN and t < T_EOD_CLOSE and
                    not self.state.eod_warning):
                self.state.eod_warning = True
                if self._on_eod:
                    try: self._on_eod()
                    except: pass

            self.state.last_phase = self.state.phase
            self.state.phase      = new_phase
            return new_phase

    def _calc_phase(self, t: time) -> SessionPhase:
        if t < T_RESET:
            return SessionPhase.PRE_MARKET
        if t < T_OPENING_END:
            return SessionPhase.OPENING
        if t < T_SIGNAL_END:
            return SessionPhase.SIGNAL_WINDOW
        if t < T_EOD_WARN:
            return SessionPhase.INTRADAY
        if t < T_EOD_CLOSE:
            return SessionPhase.EOD_WARNING
        if t < T_MARKET_CLOSE:
            return SessionPhase.CLOSED
        return SessionPhase.PRE_MARKET

    # ── Yardımcılar ───────────────────────────────────────────
    @property
    def in_signal_window(self) -> bool:
        return self.state.phase == SessionPhase.SIGNAL_WINDOW

    @property
    def in_trading_hours(self) -> bool:
        return self.state.phase in (
            SessionPhase.SIGNAL_WINDOW,
            SessionPhase.INTRADAY,
        )

    @property
    def eod_approaching(self) -> bool:
        return self.state.phase in (
            SessionPhase.EOD_WARNING,
            SessionPhase.CLOSED,
        )

    def phase_label(self) -> str:
        labels = {
            SessionPhase.PRE_MARKET:    "⏳ Piyasa Açılış Öncesi",
            SessionPhase.OPENING:       "📊 Açılış (Veri Toplama)",
            SessionPhase.SIGNAL_WINDOW: "🎯 SİNYAL PENCERESİ",
            SessionPhase.INTRADAY:      "📈 Seans İçi",
            SessionPhase.EOD_WARNING:   "⚠ Gün Sonu Yaklaşıyor",
            SessionPhase.CLOSED:        "🔴 Piyasa Kapandı",
        }
        return labels.get(self.state.phase, "—")

    def minutes_to_next_signal(self) -> Optional[int]:
        """Sinyal penceresine kaç dakika kaldı? (penceredeyse 0)"""
        now = datetime.now()
        t   = now.time()
        if self.in_signal_window:
            return 0
        if t < T_SIGNAL_START:
            delta = datetime.combine(now.date(), T_SIGNAL_START) - now
            return int(delta.total_seconds() / 60)
        return None   # pencere geçti, yarın
