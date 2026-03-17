# ============================================================
# watchlist/watchlist_engine.py — Watchlist Yöneticisi
# ============================================================
from data.models import WatchlistItem
from datetime import datetime


class WatchlistEngine:
    def __init__(self):
        self._items: dict[str, WatchlistItem] = {}

    def add(self, symbol: str, note: str = "") -> None:
        if symbol not in self._items:
            self._items[symbol] = WatchlistItem(symbol=symbol, note=note)

    def remove(self, symbol: str) -> None:
        self._items.pop(symbol, None)

    def toggle(self, symbol: str) -> bool:
        """Varsa kaldır, yoksa ekle. True = eklendi."""
        if symbol in self._items:
            self.remove(symbol); return False
        self.add(symbol); return True

    def is_watching(self, symbol: str) -> bool:
        return symbol in self._items

    def get_all(self) -> list[WatchlistItem]:
        return sorted(self._items.values(), key=lambda x: x.added_at, reverse=True)

    @property
    def symbols(self) -> set[str]:
        return set(self._items.keys())
