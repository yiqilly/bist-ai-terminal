# ============================================================
# signals/notification_store.py
# NotificationCenter — UI bağımsız veri katmanı
# Tkinter gerektirmez. ui/panels/notification_center.py sadece
# bu store'u kullanır ve görsel katmanı sağlar.
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from typing import Optional


@dataclass
class Notification:
    type:    str     # BUY | SELL | ALERT | NEWS | INFO
    symbol:  str
    message: str
    detail:  str     = ""
    ts:      datetime = field(default_factory=datetime.now)

    @property
    def age_str(self) -> str:
        secs = (datetime.now() - self.ts).total_seconds()
        if secs < 60:   return f"{secs:.0f}s"
        if secs < 3600: return f"{secs/60:.0f}m"
        return f"{secs/3600:.1f}h"


class NotificationCenter:
    """Merkezi bildirim deposu — singleton, thread-safe."""
    _instance: Optional["NotificationCenter"] = None
    _max = 50

    def __init__(self):
        self._queue:     deque[Notification] = deque(maxlen=self._max)
        self._listeners: list = []

    @classmethod
    def get(cls) -> "NotificationCenter":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add(self, ntype: str, symbol: str, message: str, detail: str = "") -> Notification:
        n = Notification(type=ntype, symbol=symbol, message=message, detail=detail)
        self._queue.appendleft(n)
        for cb in self._listeners:
            try: cb(n)
            except Exception: pass
        return n

    def on_new(self, cb) -> None:
        self._listeners.append(cb)

    def get_all(self) -> list[Notification]:
        return list(self._queue)

    def get_by_type(self, ntype: str) -> list[Notification]:
        return [n for n in self._queue if n.type == ntype]

    def unread_count(self) -> int:
        return len(self._queue)
