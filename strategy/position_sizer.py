# ============================================================
# strategy/position_sizer.py
# Gerçek sermaye bazlı lot hesabı
#
# Risk yönetimi kuralları (backtest bulgularıyla uyumlu):
#   - İşlem başı risk: sermayenin %1.2'si
#   - Max açık pozisyon: 3
#   - Max DD eşiği: %15 → yeni işlem durdur
#   - Pozisyon başına max sermaye: %25
#   - Aynı sektörde max 2 pozisyon
# ============================================================
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SizingResult:
    lots:          int
    entry:         float
    stop:          float
    target:        float
    risk_tl:       float    # bu işlemdeki TL risk
    risk_pct:      float    # sermayenin %'si
    reward_tl:     float
    rr_ratio:      float
    allowed:       bool
    reject_reason: str = ""


class PositionSizer:
    """
    Gerçek sermaye bazlı lot hesabı.

    Kullanım:
        sizer = PositionSizer(capital=500_000, config=cfg)
        result = sizer.calc(entry=15.50, stop=15.10, target=16.30)
        if result.allowed:
            # işlem aç: result.lots lot
    """

    def __init__(self, capital: float, config: dict):
        self._capital       = capital
        self._risk_pct      = config.get('risk_per_trade_pct',  1.2) / 100
        self._max_pos       = config.get('max_open_positions',  3)
        self._max_dd        = config.get('max_drawdown_pct',    15.0) / 100
        self._max_pos_pct   = config.get('max_position_pct',    25.0) / 100
        self._max_sector    = config.get('max_sector_positions', 2)
        self._min_rr        = config.get('min_rr',               1.8)
        self._comm_rate     = config.get('commission_rate',      0.0015)
        self._slip_rate     = config.get('slippage_rate',        0.0005)

        # Canlı state
        self._peak_capital  = capital
        self._open_positions: dict[str, dict] = {}   # sym → {entry, lots, sector}

    # ── Ana metod ────────────────────────────────────────────
    def calc(
        self,
        entry:    float,
        stop:     float,
        target:   float,
        sector:   str = "",
        symbol:   str = "",
    ) -> SizingResult:
        """Lot hesapla ve izin ver/reddet."""

        def reject(reason: str) -> SizingResult:
            return SizingResult(
                lots=0, entry=entry, stop=stop, target=target,
                risk_tl=0, risk_pct=0, reward_tl=0, rr_ratio=0,
                allowed=False, reject_reason=reason)

        # Temel kontroller
        if entry <= 0 or stop <= 0 or target <= 0:
            return reject("Geçersiz fiyat seviyeleri")
        if stop >= entry:
            return reject(f"Stop ({stop:.2f}) >= Entry ({entry:.2f})")
        if target <= entry:
            return reject(f"Target ({target:.2f}) <= Entry ({entry:.2f})")

        # R/R kontrolü
        risk_per_lot   = entry - stop
        reward_per_lot = target - entry
        rr             = reward_per_lot / risk_per_lot
        if rr < self._min_rr:
            return reject(f"R/R {rr:.2f} < min {self._min_rr}")

        # Max DD kontrolü
        current_dd = (self._peak_capital - self._capital) / self._peak_capital
        if current_dd >= self._max_dd:
            return reject(
                f"Max DD aşıldı: {current_dd*100:.1f}% >= {self._max_dd*100:.0f}%")

        # Max açık pozisyon
        if len(self._open_positions) >= self._max_pos:
            return reject(
                f"Max pozisyon ({self._max_pos}) dolu: "
                f"{', '.join(self._open_positions.keys())}")

        # Sektör kontrolü
        if sector:
            sec_count = sum(1 for p in self._open_positions.values()
                            if p.get('sector') == sector)
            if sec_count >= self._max_sector:
                return reject(
                    f"Sektör limiti: {sector} zaten {sec_count} pozisyon var")

        # Lot hesabı (risk bazlı)
        risk_budget = self._capital * self._risk_pct
        lots = int(risk_budget / risk_per_lot)

        # Pozisyon boyutu limiti (%25 max)
        pos_limit = int(self._capital * self._max_pos_pct / entry)
        lots = min(lots, pos_limit)
        lots = max(lots, 1)

        risk_tl   = lots * risk_per_lot
        reward_tl = lots * reward_per_lot

        return SizingResult(
            lots=lots, entry=entry, stop=stop, target=target,
            risk_tl=round(risk_tl, 2),
            risk_pct=round(risk_tl / self._capital * 100, 3),
            reward_tl=round(reward_tl, 2),
            rr_ratio=round(rr, 2),
            allowed=True,
        )

    # ── State yönetimi ────────────────────────────────────────
    def on_position_opened(self, sym: str, entry: float, lots: int,
                            stop: float, target: float, sector: str = "") -> None:
        self._open_positions[sym] = dict(
            entry=entry, lots=lots, stop=stop, target=target, sector=sector)

    def on_position_closed(self, sym: str, exit_price: float) -> float:
        """PnL döner, state günceller."""
        pos = self._open_positions.pop(sym, None)
        if not pos: return 0.0
        pnl = (exit_price - pos['entry']) * pos['lots']
        comm = (pos['entry'] * pos['lots'] + exit_price * pos['lots']) * self._comm_rate
        net_pnl = pnl - comm
        self._capital += net_pnl
        if self._capital > self._peak_capital:
            self._peak_capital = self._capital
        return net_pnl

    def on_stop_updated(self, sym: str, new_stop: float) -> None:
        if sym in self._open_positions:
            self._open_positions[sym]['stop'] = new_stop

    # ── Özellikler ────────────────────────────────────────────
    @property
    def capital(self) -> float:
        return self._capital

    @property
    def open_count(self) -> int:
        return len(self._open_positions)

    @property
    def drawdown_pct(self) -> float:
        return (self._peak_capital - self._capital) / self._peak_capital * 100

    @property
    def available_slots(self) -> int:
        return max(0, self._max_pos - len(self._open_positions))

    def summary(self) -> str:
        dd = self.drawdown_pct
        return (f"Sermaye: ₺{self._capital:,.0f}  "
                f"DD: {dd:.1f}%  "
                f"Poz: {self.open_count}/{self._max_pos}  "
                f"Boş: {self.available_slots}")
