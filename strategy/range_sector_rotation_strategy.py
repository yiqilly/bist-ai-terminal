# ============================================================
# strategy/range_sector_rotation_strategy.py
# RANGE Rejim → Sector Rotation Stratejisi
#
# Analiz bulguları:
#   - Range günlerde sektörler ortalama %5.6 spread ile ayrışıyor
#   - 45 günün 45'inde spread > %2 (kesinlikle rotasyon var)
#   - Güçlü sektör hisseleri gün boyunca momentum kazanıyor
#     10:xx +0.61% → 16:xx +1.73% (WR %77-86)
#   - GYO, Tekstil, Gübre, Banka en sık dönen sektörler
#
# Strateji mantığı:
#   1. Sabah 10:00-10:30 arası sektörlerin açılış momentumunu ölç
#   2. En güçlü sektörü tespit et (diğerlerinden açıkça ayrışmalı)
#   3. O sektörün en güçlü hissesini seç (RS lideri)
#   4. Trend + hacim onaylıyorsa 10:20-10:40 arasında giriş
#   5. Gün boyunca momentum sürer — EOD veya ATR hedef çıkış
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from enum import Enum
from typing import Optional

# ── Sabitler ────────────────────────────────────────────────
DETECTION_START  = time(10,  0)   # sektör momentum ölçümü başlar
DETECTION_END    = time(10, 30)   # sektör tespiti sona erer
ENTRY_START      = time(10, 20)   # giriş başlangıcı (biraz veri biriksin)
ENTRY_END        = time(10, 45)   # bu saate kadar giriş yap veya iptal

# Sektör ayrışma eşiği
MIN_SECTOR_SPREAD    = 1.5   # güçlü sektör zayıftan en az %1.5 daha iyi
MIN_SECTOR_MOMENTUM  = 0.4   # güçlü sektör en az +%0.4 yukarı
MIN_SECTOR_BREADTH   = 0.60  # güçlü sektörün en az %60'ı yükseliyor

# Hisse filtreleri
RS_VS_SECTOR_MIN   = 0.0    # sektör ortalamasından güçlü
VOL_CONFIRM_MULT   = 1.2    # hacim 20-bar ortalamasının 1.2x'i
RSI_MIN            = 45.0   # aşırı satımda değil
RSI_MAX            = 78.0   # aşırı alımda değil

# Stop/Target
ATR_STOP_MULT    = 0.80    # stop = entry - günlük_ATR × 0.80
ATR_TARGET_MULT  = 1.80    # target = entry + günlük_ATR × 1.80 (~2.25R)
ATR_TRAIL_MULT   = 0.60
RR_MIN           = 1.8
CONFIRM_BARS     = 2

STRATEGY_TYPE    = "RANGE_SECTOR_ROTATION"


class RotationSetupType(str, Enum):
    NONE              = "NONE"
    SECTOR_LEADER     = "SECTOR_LEADER"       # sektör lideri + momentum
    SECTOR_BREAKOUT   = "SECTOR_BREAKOUT"     # sektör + kırılım


class RotationState(str, Enum):
    IDLE    = "IDLE"
    WATCHING= "WATCHING"    # sektör tespiti yapılıyor
    SETUP   = "SETUP"       # teyit bekleniyor
    SIGNAL  = "SIGNAL"
    REJECT  = "REJECT"


@dataclass
class SectorSnapshot:
    """Bir sektörün sabah momentumu."""
    name:         str
    momentum:     float  = 0.0   # sektörün ort. açılış getirisi %
    breadth:      float  = 0.0   # yükselen hisse oranı 0-1
    leader_sym:   str    = ""    # en güçlü hisse
    leader_ret:   float  = 0.0   # liderin getirisi %
    strength_score: float= 0.0   # birleşik skor

    def is_strong(self) -> bool:
        return (self.momentum >= MIN_SECTOR_MOMENTUM and
                self.breadth  >= MIN_SECTOR_BREADTH)


@dataclass
class RotationSignal:
    symbol:        str
    state:         RotationState    = RotationState.IDLE
    setup_type:    RotationSetupType= RotationSetupType.NONE
    strategy_type: str              = STRATEGY_TYPE

    entry:         float = 0.0
    stop:          float = 0.0
    target:        float = 0.0
    daily_atr:     float = 0.0

    sector_str:    float = 0.0
    rs_score:      float = 0.0
    rsi:           float = 50.0
    sector_name:   str   = ""
    sector_spread: float = 0.0   # güçlü - zayıf sektör farkı

    confirm_count: int   = 0
    reject_count:  int   = 0
    persist_count: int   = 0
    detail:        str   = ""

    def is_buy_signal(self) -> bool:
        return self.state == RotationState.SIGNAL

    def reset(self):
        self.state         = RotationState.IDLE
        self.setup_type    = RotationSetupType.NONE
        self.confirm_count = 0
        self.persist_count = 0
        self.entry = self.stop = self.target = 0.0


class RangeSectorRotationStrategy:
    """
    RANGE rejim için Sector Rotation stratejisi.

    on_bar() her 5m bar'da çağrılır.

    ctx içeriği:
        sector_returns:  dict[str, float]  ← sektör → açılış getirisi %
        sector_breadth:  dict[str, float]  ← sektör → yükselen oran 0-1
        sym_sector:      str               ← bu hissenin sektörü
        rs_vs_sector:    float             ← sektör ortalamasına göre RS
        ema9_daily:      float
        ema21_daily:     float
        rsi_daily:       float
        daily_atr:       float
        vol_ma:          float
        intraday_vol:    float
        intraday_bars:   list[Bar]
        opening_ret:     float             ← bu hissenin açılış getirisi %
    """

    def __init__(self):
        self._signals:    dict[str, RotationSignal] = {}
        self._day_sector: Optional[str]   = None    # bugün güçlü sektör
        self._day_spread: float           = 0.0
        self._day_snapshots: dict[str, SectorSnapshot] = {}

    def on_bar(self, symbol: str, bar, ctx: dict) -> Optional[RotationSignal]:
        sig = self._get_or_create(symbol)

        # Gün değişimi
        today = bar.timestamp.date()
        if hasattr(sig, '_date') and sig._date != today:
            sig.reset()
            # Gün değişiminde sektör tespitini sıfırla
            if not hasattr(self, '_today') or self._today != today:
                self._day_sector   = None
                self._day_spread   = 0.0
                self._day_snapshots= {}
                self._today        = today
        sig._date = today

        bar_t = bar.timestamp.time()

        # REJECT cooldown
        if sig.state == RotationState.REJECT:
            sig.reject_count += 1
            if sig.reject_count >= 8:
                sig.reset()
            return sig

        # Sinyal yaşıyorsa persist
        if sig.state == RotationState.SIGNAL:
            sig.persist_count += 1
            if sig.persist_count > 48:
                sig.reset()
            return sig

        # ── Faz 1: Sektör tespiti (10:00-10:30) ──────────────
        if DETECTION_START <= bar_t <= DETECTION_END:
            self._update_sector_snapshot(bar_t, ctx)

        # Giriş penceresi öncesi → sadece izle
        if bar_t < ENTRY_START:
            sig.state = RotationState.WATCHING
            return sig

        # Giriş penceresi kapandı → geç kalan yok
        if bar_t > ENTRY_END:
            if sig.state not in (RotationState.SIGNAL,):
                sig.state = RotationState.IDLE
            return sig

        # ── Faz 2: Sektör seçimi doğrulandı mı? ──────────────
        if self._day_sector is None:
            self._finalize_sector_selection(ctx)

        if self._day_sector is None:
            sig.state = RotationState.IDLE
            return sig

        # Bu hisse güçlü sektörde mi?
        sym_sector = ctx.get('sym_sector', '')
        if sym_sector != self._day_sector:
            sig.state = RotationState.IDLE
            return sig

        sig.sector_name   = sym_sector
        sig.sector_spread = self._day_spread

        # ── Faz 3: Hisse filtreleri ───────────────────────────

        # 1. RS: sektör ortalamasından güçlü
        rs_sec = float(ctx.get('rs_vs_sector', 0))
        if rs_sec < RS_VS_SECTOR_MIN:
            sig.state = RotationState.IDLE; return sig
        sig.rs_score = rs_sec

        # 2. Trend: günlük EMA9 > EMA21
        e9  = float(ctx.get('ema9_daily',  0))
        e21 = float(ctx.get('ema21_daily', 0))
        if e9 <= 0 or e21 <= 0 or e9 <= e21:
            sig.state = RotationState.IDLE; return sig

        # 3. RSI bandı
        rsi = float(ctx.get('rsi_daily', 50))
        if not (RSI_MIN <= rsi <= RSI_MAX):
            sig.state = RotationState.IDLE; return sig
        sig.rsi = rsi

        # 4. Açılış momentumu pozitif
        opening_ret = float(ctx.get('opening_ret', 0))
        if opening_ret < 0:
            sig.state = RotationState.IDLE; return sig

        # 5. Hacim onayı
        vol_ma = float(ctx.get('vol_ma', 0))
        vol_ok = (vol_ma <= 0) or (bar.volume >= vol_ma * VOL_CONFIRM_MULT)
        if not vol_ok:
            sig.state = RotationState.IDLE; return sig

        # 6. Sektör güç skoru
        datr = float(ctx.get('daily_atr', bar.close * 0.03))
        sig.daily_atr = datr
        snap = self._day_snapshots.get(sym_sector)
        sig.sector_str = snap.momentum * 20 if snap else 50.0

        # Setup tipi
        if opening_ret >= 0.8:
            setup = RotationSetupType.SECTOR_BREAKOUT
            detail = (f"SectorBreakout: {sym_sector} spread={self._day_spread:.1f}% "
                      f"open_ret={opening_ret:.2f}%")
        else:
            setup = RotationSetupType.SECTOR_LEADER
            detail = (f"SectorLeader: {sym_sector} spread={self._day_spread:.1f}% "
                      f"rs={rs_sec:.2f}")
        sig.setup_type = setup
        sig.detail     = detail

        # ── State machine ─────────────────────────────────────
        if sig.state in (RotationState.IDLE, RotationState.WATCHING):
            sig.state         = RotationState.SETUP
            sig.confirm_count = 1
            return sig

        if sig.state == RotationState.SETUP:
            sig.confirm_count += 1
            if sig.confirm_count >= CONFIRM_BARS:
                entry  = bar.close
                stop   = entry - datr * ATR_STOP_MULT
                target = entry + datr * ATR_TARGET_MULT
                risk   = entry - stop
                if risk > 0 and (target-entry)/risk >= RR_MIN and risk/entry <= 0.12:
                    sig.state         = RotationState.SIGNAL
                    sig.entry         = entry
                    sig.stop          = stop
                    sig.target        = target
                    sig.persist_count = 0
                else:
                    sig.state        = RotationState.REJECT
                    sig.reject_count = 0
                    sig.detail      += " | R/R yetersiz"

        return sig

    # ── Sektör yardımcıları ───────────────────────────────────
    def _update_sector_snapshot(self, bar_t: time, ctx: dict):
        """Her barda sektör momentumunu güncelle."""
        sec_rets  = ctx.get('sector_returns',  {})
        sec_bread = ctx.get('sector_breadth',  {})

        for sec, ret in sec_rets.items():
            bread = sec_bread.get(sec, 0.5)
            score = ret * 0.6 + (bread - 0.5) * 100 * 0.4
            if sec not in self._day_snapshots:
                self._day_snapshots[sec] = SectorSnapshot(name=sec)
            snap = self._day_snapshots[sec]
            snap.momentum      = ret
            snap.breadth       = bread
            snap.strength_score= score

    def _finalize_sector_selection(self, ctx: dict):
        """10:30'da güçlü sektörü seç."""
        if not self._day_snapshots:
            return

        # Güçlü sektörler
        strong = [(s, snap) for s, snap in self._day_snapshots.items()
                  if snap.is_strong()]
        if not strong:
            return

        # En güçlü sektörü bul
        best_sec, best_snap = max(strong,
                                   key=lambda x: x[1].strength_score)

        # Spread hesapla (güçlü - zayıf)
        all_moms = [s.momentum for s in self._day_snapshots.values()]
        if len(all_moms) >= 2:
            spread = best_snap.momentum - min(all_moms)
        else:
            spread = 0.0

        # Minimum spread kontrolü
        if spread < MIN_SECTOR_SPREAD:
            return

        self._day_sector = best_sec
        self._day_spread = spread

    def get_buy_signals(self) -> list[RotationSignal]:
        return [s for s in self._signals.values()
                if s.state == RotationState.SIGNAL]

    def reset_day(self):
        for s in self._signals.values():
            s.reset()
        self._day_sector    = None
        self._day_spread    = 0.0
        self._day_snapshots = {}

    def _get_or_create(self, sym: str) -> RotationSignal:
        if sym not in self._signals:
            self._signals[sym] = RotationSignal(symbol=sym)
        return self._signals[sym]
