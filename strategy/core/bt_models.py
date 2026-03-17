# ============================================================
# strategy/core/bt_models.py
# Backtest Veri Modelleri
#
# Hiyerarşi:
#   TradeLog       — tek bir kapalı işlem
#   OpenPosition   — aktif açık pozisyon
#   PortfolioState — anlık portföy durumu
#   DayResult      — tek günün özeti
# ============================================================
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


# ── Enum'lar ─────────────────────────────────────────────────────────────────

class ExitReason(str, Enum):
    STOP_LOSS      = "stop_loss"
    TRAILING_STOP  = "trailing_stop"
    TARGET         = "target"
    END_OF_DAY     = "end_of_day"
    FORCED_CLOSE   = "forced_close"    # max pozisyon limiti veya özel durum


class SetupType(str, Enum):
    PULLBACK_REBREAK          = "PullbackRebreak"
    MORNING_MOMENTUM_BREAKOUT = "MorningMomentumBreakout"
    BREAKOUT_ONLY             = "BreakoutOnly"
    NONE                      = "None"


# ── Komisyon & Slippage Konfigürasyonu ───────────────────────────────────────

@dataclass
class ExecutionConfig:
    """
    Gerçekçi execution maliyetleri.
    Tüm değerler oran (0.0015 = %0.15).
    """
    commission_entry:   float = 0.0015   # %0.15 giriş komisyonu
    commission_exit:    float = 0.0015   # %0.15 çıkış komisyonu
    slippage_entry:     float = 0.0005   # %0.05 giriş slippage (market order)
    slippage_exit:      float = 0.0005   # %0.05 çıkış slippage
    min_lot:            int   = 1        # minimum işlem miktarı

    @property
    def total_rt_cost(self) -> float:
        """Round-trip toplam maliyet oranı."""
        return (self.commission_entry + self.slippage_entry +
                self.commission_exit  + self.slippage_exit)

    def apply_entry(self, price: float) -> float:
        """Giriş fiyatına komisyon + slippage uygula (long pozisyon — daha pahalı)."""
        return price * (1 + self.commission_entry + self.slippage_entry)

    def apply_exit(self, price: float) -> float:
        """Çıkış fiyatına komisyon + slippage uygula (long pozisyon — daha ucuz)."""
        return price * (1 - self.commission_exit - self.slippage_exit)


# ── Position Sizing Konfigürasyonu ───────────────────────────────────────────

@dataclass
class SizingConfig:
    """
    Portföy bazlı pozisyon boyutu.
    """
    total_capital:          float = 100_000.0
    risk_per_trade_pct:     float = 1.0      # Sermayenin %1'i riske edilir
    max_open_positions:     int   = 5
    max_portfolio_risk_pct: float = 8.0      # Aynı anda max %8 portföy riski
    min_position_value:     float = 1_000.0  # Minimum pozisyon değeri (TL)
    min_lot:                int   = 1        # minimum işlem adedi

    def position_size(
        self,
        capital: float,
        entry_price: float,
        stop_price: float,
    ) -> int:
        """
        Sabit Risk (Fixed Fractional) pozisyon boyutu.
        Kaç lot alınacağını hesaplar.

        risk_tl = capital * risk_per_trade_pct / 100
        lot     = risk_tl / (entry - stop)
        """
        risk_per_share = entry_price - stop_price
        if risk_per_share <= 0:
            return 0

        risk_tl = capital * (self.risk_per_trade_pct / 100)
        lots    = math.floor(risk_tl / risk_per_share)
        lots    = max(lots, self.min_lot)

        # Pozisyon değeri kontrolü
        if lots * entry_price < self.min_position_value:
            return 0

        return lots


# ── Stop/Target Konfigürasyonu ────────────────────────────────────────────────

@dataclass
class StopConfig:
    """
    Stop ve hedef hesaplama parametreleri.
    """
    initial_stop_pct:   float = 0.006   # Giriş fiyatından %0.6 aşağı
    target_rr:          float = 2.5     # Risk/Reward oranı (stop mesafesinin 2.5 katı)
    trailing_activation:float = 0.004   # Fiyat giriş fiyatının %0.4 üzerine çıkınca trailing başlar
    trailing_pct:       float = 0.006   # Trailing stop mesafesi (en yüksekten %0.6 aşağı)
    eod_exit_time_str:  str   = "17:30" # Gün sonu çıkış saati

    def initial_stop(self, entry: float) -> float:
        return round(entry * (1 - self.initial_stop_pct), 2)

    def initial_target(self, entry: float) -> float:
        stop   = self.initial_stop(entry)
        risk   = entry - stop
        return round(entry + risk * self.target_rr, 2)

    def trailing_stop(self, highest: float) -> float:
        return round(highest * (1 - self.trailing_pct), 2)


# ── Açık Pozisyon ────────────────────────────────────────────────────────────

@dataclass
class OpenPosition:
    """
    Trade açıldıktan sonra bar-by-bar takip edilen pozisyon.
    """
    symbol:        str
    entry_ts:      datetime
    entry_price:   float       # Fill fiyatı (komisyon + slippage sonrası)
    raw_entry:     float       # Gerçek bar kapanışı (komisyonsuz)
    lots:          int
    stop:          float
    target:        float
    setup_type:    str
    regime_mode:   str
    setup_quality: float       # CoreSetupFeatures.setup_quality

    # Dinamik takip
    highest_price: float = 0.0
    trailing_stop_active: bool = False
    current_stop:  float = 0.0

    def __post_init__(self):
        self.highest_price = self.raw_entry
        self.current_stop  = self.stop

    def update_trailing(self, current_high: float, cfg: StopConfig) -> None:
        """Her barda çağrılır — trailing stop günceller."""
        if current_high > self.highest_price:
            self.highest_price = current_high

        # Trailing aktivasyon kontrolü
        gain = (self.highest_price - self.raw_entry) / self.raw_entry
        if gain >= cfg.trailing_activation:
            self.trailing_stop_active = True

        if self.trailing_stop_active:
            ts = cfg.trailing_stop(self.highest_price)
            if ts > self.current_stop:
                self.current_stop = ts

    @property
    def unrealized_pnl_pct(self) -> float:
        return (self.highest_price - self.raw_entry) / self.raw_entry * 100

    @property
    def cost_basis(self) -> float:
        return self.entry_price * self.lots


# ── Kapalı İşlem Kaydı ───────────────────────────────────────────────────────

@dataclass
class TradeLog:
    """
    Kapandıktan sonra kalıcı kayıt. Gerçekçi: komisyon dahil.
    """
    # Kimlik
    trade_id:      int
    symbol:        str
    date:          date
    setup_type:    str
    regime_mode:   str
    setup_quality: float

    # Fiyatlar (ham — komisyonsuz)
    raw_entry:     float
    raw_exit:      float

    # Fiyatlar (fill — komisyon + slippage dahil)
    fill_entry:    float
    fill_exit:     float

    # Zaman
    entry_ts:      datetime
    exit_ts:       datetime

    # Boyut
    lots:          int
    stop_at_entry: float
    target:        float
    initial_risk:  float    # lots * (fill_entry - stop) per TL

    # Sonuç
    exit_reason:   ExitReason
    gross_pnl_tl:  float    # lots * (raw_exit - raw_entry)
    commission_tl: float    # toplam komisyon
    slippage_tl:   float    # toplam slippage
    net_pnl_tl:    float    # gross - commission - slippage
    pnl_pct:       float    # net_pnl_tl / (fill_entry * lots) * 100

    # Ek bilgi
    highest_price: float    # pozisyon boyunca görülen en yüksek
    trailing_triggered: bool

    @property
    def is_winner(self) -> bool:
        return self.net_pnl_tl > 0

    @property
    def hold_minutes(self) -> float:
        return (self.exit_ts - self.entry_ts).total_seconds() / 60

    def to_dict(self) -> dict:
        return {
            "trade_id":    self.trade_id,
            "symbol":      self.symbol,
            "date":        str(self.date),
            "setup_type":  self.setup_type,
            "regime_mode": self.regime_mode,
            "setup_quality": round(self.setup_quality, 2),
            "entry_ts":    self.entry_ts.strftime("%H:%M"),
            "exit_ts":     self.exit_ts.strftime("%H:%M"),
            "hold_min":    round(self.hold_minutes, 1),
            "lots":        self.lots,
            "raw_entry":   round(self.raw_entry,  2),
            "raw_exit":    round(self.raw_exit,   2),
            "fill_entry":  round(self.fill_entry, 2),
            "fill_exit":   round(self.fill_exit,  2),
            "stop":        round(self.stop_at_entry, 2),
            "target":      round(self.target,     2),
            "exit_reason": self.exit_reason.value,
            "gross_pnl":   round(self.gross_pnl_tl, 2),
            "commission":  round(self.commission_tl, 2),
            "slippage":    round(self.slippage_tl,   2),
            "net_pnl":     round(self.net_pnl_tl,    2),
            "pnl_pct":     round(self.pnl_pct,       4),
            "winner":      self.is_winner,
            "highest":     round(self.highest_price,  2),
            "trailing":    self.trailing_triggered,
        }


# ── Portföy Durumu ───────────────────────────────────────────────────────────

@dataclass
class PortfolioState:
    """
    Backtest boyunca güncellenen anlık portföy.
    """
    initial_capital: float
    cash:            float = 0.0
    open_positions:  dict[str, OpenPosition] = field(default_factory=dict)
    closed_trades:   list[TradeLog]          = field(default_factory=list)
    _trade_counter:  int                     = 0

    def __post_init__(self):
        self.cash = self.initial_capital

    @property
    def equity(self) -> float:
        """Anlık toplam değer: nakit + açık pozisyon piyasa değeri."""
        pos_value = sum(
            p.highest_price * p.lots
            for p in self.open_positions.values()
        )
        return self.cash + pos_value

    @property
    def open_count(self) -> int:
        return len(self.open_positions)

    @property
    def total_committed(self) -> float:
        return sum(p.cost_basis for p in self.open_positions.values())

    @property
    def available_capital(self) -> float:
        return self.cash

    def next_trade_id(self) -> int:
        self._trade_counter += 1
        return self._trade_counter
