# ============================================================
# data/adapters/base_adapter.py — Abstract Base Adapter
# ============================================================
from abc import ABC, abstractmethod
from typing import Callable, Optional
from data.models import MarketSnapshot, MarketTick, BarData


class BaseMarketDataAdapter(ABC):
    """
    Tüm veri adaptörlerinin uygulaması gereken temel arayüz.
    Yeni bir veri kaynağı eklemek için bu sınıfı extend et.
    """

    def __init__(self):
        self._tick_callbacks: list[Callable[[MarketTick], None]] = []
        self._bar_callbacks: list[Callable[[BarData], None]] = []
        self._connected: bool = False

    # ── Bağlantı ───────────────────────────────────────────
    @abstractmethod
    def connect(self) -> bool:
        """Veri kaynağına bağlan. Başarılıysa True döndür."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Bağlantıyı kapat."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Bağlantı durumunu döndür."""
        ...

    def reconnect(self) -> bool:
        """Bağlantıyı kes ve yeniden bağlan."""
        self.disconnect()
        return self.connect()

    def health_check(self) -> bool:
        """Adaptörün sağlıklı çalışıp çalışmadığını kontrol et."""
        return self.is_connected()

    # ── Abonelik ───────────────────────────────────────────
    @abstractmethod
    def subscribe(self, symbols: list[str]) -> None:
        """Belirtilen sembollere abone ol."""
        ...

    @abstractmethod
    def unsubscribe(self, symbols: list[str]) -> None:
        """Aboneliği iptal et."""
        ...

    # ── Anlık Veri ─────────────────────────────────────────
    @abstractmethod
    def get_latest_snapshot(self) -> MarketSnapshot:
        """En güncel piyasa anlık görüntüsünü döndür."""
        ...

    # ── Event Callback'leri ────────────────────────────────
    def on_tick(self, callback: Callable[[MarketTick], None]) -> None:
        """Her fiyat tickinde çağrılacak fonksiyonu kaydet."""
        self._tick_callbacks.append(callback)

    def on_bar(self, callback: Callable[[BarData], None]) -> None:
        """Her mum kapanışında çağrılacak fonksiyonu kaydet."""
        self._bar_callbacks.append(callback)

    def _emit_tick(self, tick: MarketTick) -> None:
        for cb in self._tick_callbacks:
            try:
                cb(tick)
            except Exception as e:
                print(f"[Adapter] Tick callback hatası: {e}")

    def _emit_bar(self, bar: BarData) -> None:
        for cb in self._bar_callbacks:
            try:
                cb(bar)
            except Exception as e:
                print(f"[Adapter] Bar callback hatası: {e}")
