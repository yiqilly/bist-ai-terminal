# ============================================================
# portfolio/position_manager.py
# Position Manager — FAZ 8
#
# Kullanıcının açık pozisyonlarını yönetir.
# Kalıcı state (JSON dosyası) + in-memory.
# ============================================================
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


POSITIONS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "positions.json"
)


@dataclass
class Position:
    symbol:         str
    entry_price:    float
    lots:           int
    stop:           float
    target:         float
    entry_time:     str    = ""   # ISO format
    notes:          str    = ""
    status:         str    = "OPEN"   # OPEN | CLOSED | STOPPED

    # Anlık (in-memory, kaydedilmez)
    current_price:  float  = 0.0
    trailing_stop:  float  = 0.0

    # Kapatma
    exit_price:     float  = 0.0
    exit_time:      str    = ""
    exit_reason:    str    = ""

    def __post_init__(self):
        if not self.entry_time:
            self.entry_time = datetime.now().isoformat(timespec="seconds")

    @property
    def pnl_pct(self) -> float:
        p = self.current_price if self.current_price > 0 else self.entry_price
        return (p - self.entry_price) / self.entry_price * 100 if self.entry_price else 0.0

    @property
    def pnl_tl(self) -> float:
        p = self.current_price if self.current_price > 0 else self.entry_price
        return (p - self.entry_price) * self.lots

    @property
    def cost_tl(self) -> float:
        return self.entry_price * self.lots

    @property
    def is_open(self) -> bool:
        return self.status == "OPEN"

    @property
    def stop_distance_pct(self) -> float:
        return abs(self.entry_price - self.stop) / self.entry_price * 100 if self.entry_price else 0.0

    @property
    def target_distance_pct(self) -> float:
        return abs(self.target - self.entry_price) / self.entry_price * 100 if self.entry_price else 0.0


class PositionManager:
    """
    Açık pozisyonları yönetir.
    Thread-safe. JSON ile kalıcı state.
    """

    def __init__(self, filepath: str = POSITIONS_FILE):
        self._filepath  = filepath
        self._positions: dict[str, Position] = {}   # symbol → Position
        self._lock      = threading.RLock()
        self._load()

    # ── CRUD ─────────────────────────────────────────────────

    def open_position(
        self,
        symbol:      str,
        entry_price: float,
        lots:        int,
        stop:        float,
        target:      float,
        notes:       str = "",
    ) -> Position:
        with self._lock:
            pos = Position(
                symbol=symbol,
                entry_price=entry_price,
                lots=lots,
                stop=stop,
                target=target,
                notes=notes,
            )
            self._positions[symbol] = pos
            self._save()
            return pos

    def close_position(
        self,
        symbol:      str,
        exit_price:  float,
        reason:      str = "manual",
    ) -> Optional[Position]:
        with self._lock:
            pos = self._positions.get(symbol)
            if pos and pos.is_open:
                pos.status     = "CLOSED"
                pos.exit_price = exit_price
                pos.exit_time  = datetime.now().isoformat(timespec="seconds")
                pos.exit_reason = reason
                self._save()
                return pos
            return None

    def update_stop(self, symbol: str, new_stop: float) -> None:
        with self._lock:
            pos = self._positions.get(symbol)
            if pos and pos.is_open:
                pos.stop = new_stop
                self._save()

    def update_target(self, symbol: str, new_target: float) -> None:
        with self._lock:
            pos = self._positions.get(symbol)
            if pos and pos.is_open:
                pos.target = new_target
                self._save()

    def add_note(self, symbol: str, note: str) -> None:
        with self._lock:
            pos = self._positions.get(symbol)
            if pos:
                ts = datetime.now().strftime("%H:%M")
                pos.notes = f"[{ts}] {note}\n" + pos.notes
                self._save()

    # ── Fiyat güncelleme ─────────────────────────────────────

    def update_prices(self, prices: dict[str, float]) -> list[str]:
        """
        Anlık fiyatları güncelle.
        Stop veya target tetiklenirse sembol listesi döner.
        """
        triggered = []
        with self._lock:
            for sym, pos in self._positions.items():
                if not pos.is_open:
                    continue
                price = prices.get(sym, 0.0)
                if price > 0:
                    pos.current_price = price
                    # Stop kontrolü
                    if price <= pos.stop:
                        pos.status      = "STOPPED"
                        pos.exit_price  = price
                        pos.exit_time   = datetime.now().isoformat(timespec="seconds")
                        pos.exit_reason = "stop"
                        triggered.append(sym)
                    # Target kontrolü
                    elif price >= pos.target:
                        triggered.append(sym)
        if triggered:
            self._save()
        return triggered

    # ── Sorgu ────────────────────────────────────────────────

    def get_open(self) -> list[Position]:
        with self._lock:
            return [p for p in self._positions.values() if p.is_open]

    def get_all(self) -> list[Position]:
        with self._lock:
            return list(self._positions.values())

    def get(self, symbol: str) -> Optional[Position]:
        with self._lock:
            return self._positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        with self._lock:
            p = self._positions.get(symbol)
            return p is not None and p.is_open

    @property
    def open_count(self) -> int:
        with self._lock:
            return sum(1 for p in self._positions.values() if p.is_open)

    @property
    def total_exposure(self) -> float:
        with self._lock:
            return sum(p.cost_tl for p in self._positions.values() if p.is_open)

    @property
    def total_pnl_tl(self) -> float:
        with self._lock:
            return sum(p.pnl_tl for p in self._positions.values() if p.is_open)

    # ── Kalıcı state ─────────────────────────────────────────

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
            data = []
            for p in self._positions.values():
                d = asdict(p)
                # current_price / trailing_stop kaydetme (runtime only)
                d.pop("current_price", None)
                d.pop("trailing_stop", None)
                data.append(d)
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load(self) -> None:
        try:
            if not os.path.exists(self._filepath):
                return
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for d in data:
                d.pop("current_price", None)
                d.pop("trailing_stop", None)
                pos = Position(**d)
                self._positions[pos.symbol] = pos
        except Exception:
            pass
