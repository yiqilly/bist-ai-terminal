# ============================================================
# portfolio/trade_journal.py
# Trade Journal — işlem günlüğü (kalıcı JSON)
# ============================================================
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

JOURNAL_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "trade_journal.json"
)


@dataclass
class TradeRecord:
    symbol:      str
    entry_price: float
    exit_price:  float
    lots:        int
    entry_time:  str
    exit_time:   str
    exit_reason: str   = "manual"
    setup_type:  str   = "UNKNOWN"
    notes:       str   = ""
    pnl_tl:      float = 0.0
    pnl_pct:     float = 0.0

    def __post_init__(self):
        if self.entry_price > 0:
            self.pnl_tl  = (self.exit_price - self.entry_price) * self.lots
            self.pnl_pct = (self.exit_price - self.entry_price) / self.entry_price * 100


class TradeJournal:
    def __init__(self, filepath: str = JOURNAL_FILE):
        self._filepath = filepath
        self._records: list[TradeRecord] = []
        self._load()

    def add(self, record: TradeRecord) -> None:
        self._records.append(record)
        self._save()

    def record_from_position(self, pos, setup_type: str = "UNKNOWN") -> TradeRecord:
        from portfolio.position_manager import Position
        rec = TradeRecord(
            symbol      = pos.symbol,
            entry_price = pos.entry_price,
            exit_price  = pos.exit_price,
            lots        = pos.lots,
            entry_time  = pos.entry_time,
            exit_time   = pos.exit_time,
            exit_reason = pos.exit_reason,
            setup_type  = setup_type,
            notes       = pos.notes,
        )
        self.add(rec)
        return rec

    def get_all(self) -> list[TradeRecord]:
        return list(reversed(self._records))

    @property
    def win_count(self) -> int:
        return sum(1 for r in self._records if r.pnl_tl > 0)

    @property
    def loss_count(self) -> int:
        return sum(1 for r in self._records if r.pnl_tl < 0)

    @property
    def win_rate(self) -> float:
        total = len(self._records)
        return self.win_count / total * 100 if total else 0.0

    @property
    def total_pnl(self) -> float:
        return sum(r.pnl_tl for r in self._records)

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump([asdict(r) for r in self._records], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load(self):
        try:
            if not os.path.exists(self._filepath):
                return
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._records = [TradeRecord(**d) for d in data]
        except Exception:
            pass
