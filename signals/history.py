# ============================================================
# signals/history.py — Sinyal Geçmişi
# ============================================================
from collections import deque
from datetime import datetime
from config import SIGNAL_HISTORY_MAX
from data.models import RankedSignal


class SignalHistory:
    def __init__(self, max_size: int = SIGNAL_HISTORY_MAX):
        self._history: deque[dict] = deque(maxlen=max_size)
        self._seen: set[str] = set()

    def add(self, signal: RankedSignal) -> None:
        key = f"{signal.candidate.symbol}_{signal.candidate.score}"
        if key not in self._seen:
            self._seen.add(key)
            self._history.appendleft({
                "time": datetime.now().strftime("%H:%M:%S"),
                "symbol": signal.candidate.symbol,
                "score": signal.candidate.score,
                "rsi": round(signal.candidate.rsi, 1),
                "entry": signal.risk.entry,
                "target": signal.risk.target,
                "rr": signal.risk.rr_ratio,
            })

    def get_all(self) -> list[dict]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
        self._seen.clear()
