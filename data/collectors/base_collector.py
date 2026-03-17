# ============================================================
# data/collectors/base_collector.py
# Soyut Collector Arayüzü
#
# Tüm collector'lar bu sınıfı extend eder:
#   TradingViewCollector   (borsapy WebSocket)
#   MockCollector          (geliştirme / test)
#   MatriksCollector       (Matriks IQ DDE — gelecek)
#   ForeksCollector        (Foreks API — gelecek)
#   CSVCollector           (offline backfill — gelecek)
#
# Collector'ın tek görevi:
#   Ham veriyi normalize et → MarketBus'a yayınla
#   UI veya strateji engine'e doğrudan bağlanma!
# ============================================================
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from data.models import MarketTick, BarData


# ── Collector Durumu ─────────────────────────────────────────

class CollectorState:
    DISCONNECTED = "DISCONNECTED"
    CONNECTING   = "CONNECTING"
    CONNECTED    = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    STOPPING     = "STOPPING"


# ── Normalize Edilmiş Quote ──────────────────────────────────

@dataclass
class NormalizedQuote:
    """
    Her veri kaynağından gelen ham veri bu formata normalize edilir.
    market_bus.publish("quote", quote) ile yayınlanır.
    """
    symbol:    str
    last:      float
    bid:       float
    ask:       float
    volume:    float
    timestamp: datetime = field(default_factory=datetime.now)
    # Opsiyonel zenginleştirme alanları
    change_pct:    float = 0.0
    prev_close:    float = 0.0
    high_day:      float = 0.0
    low_day:       float = 0.0
    source:        str   = ""     # "borsapy" | "matriks" | "mock"

    def to_market_tick(self) -> MarketTick:
        """MarketBus'ın beklediği MarketTick'e dönüştür."""
        return MarketTick(
            symbol=self.symbol,
            price=self.last,
            bid=self.bid,
            ask=self.ask,
            volume=self.volume,
            timestamp=self.timestamp,
        )


# ── Normalize Edilmiş Bar ────────────────────────────────────

@dataclass
class NormalizedBar:
    """
    1m / 5m mum verisi.
    market_bus.publish("bar", bar) ile yayınlanır.
    """
    symbol:     str
    timeframe:  str        # "1m" | "5m" | "15m" | "1h" | "1d"
    open:       float
    high:       float
    low:        float
    close:      float
    volume:     float
    start_time: datetime
    is_closed:  bool = True    # False → mevcut henüz kapanmamış bar
    source:     str  = ""

    def to_bar_data(self) -> BarData:
        """MarketBus'ın beklediği BarData'ya dönüştür."""
        return BarData(
            symbol=self.symbol,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            timestamp=self.start_time,
        )

    def fmt_volume(self) -> str:
        """'1.2M', '850K' formatı."""
        v = self.volume
        if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
        if v >= 1_000:     return f"{v/1_000:.0f}K"
        return str(int(v))


# ── Collector İstatistikleri ─────────────────────────────────

@dataclass
class CollectorStats:
    quotes_received:   int = 0
    bars_received:     int = 0
    quotes_published:  int = 0
    bars_published:    int = 0
    throttle_drops:    int = 0
    reconnect_count:   int = 0
    error_count:       int = 0
    started_at:        Optional[datetime] = None
    last_quote_at:     Optional[datetime] = None
    last_error:        str = ""

    @property
    def uptime_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        return (datetime.now() - self.started_at).total_seconds()


# ── Soyut Collector ──────────────────────────────────────────

class BaseCollector(ABC):
    """
    Tüm data collector'ların uygulaması gereken temel arayüz.

    Implement edilmesi gereken metodlar:
        connect()
        disconnect()
        subscribe(symbol)
        _run_stream()    (arka plan thread'i)

    Otomatik sağlanan metodlar:
        subscribe_many(symbols)
        publish_quote(quote)
        publish_bar(bar)
        on_quote_callback / on_bar_callback kayıt
        stats, state takibi
    """

    def __init__(self, config: dict | None = None):
        self._config   = config or {}
        self._state    = CollectorState.DISCONNECTED
        self._symbols: list[str] = []
        self._stats    = CollectorStats()
        self._lock     = threading.Lock()

        # Callback'ler — MarketBus entegrasyonu için
        self._quote_callbacks: list[Callable[[NormalizedQuote], None]] = []
        self._bar_callbacks:   list[Callable[[NormalizedBar],   None]] = []

        # Logger — subclass adını kullanır
        self._log = logging.getLogger(self.__class__.__name__)

    # ── Yaşam Döngüsü ────────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """
        Veri kaynağına bağlan.
        Başarılı → True, başarısız → False.
        Bağlantı başarılı olsa da olmasa da exception fırlatma,
        sadece False döndür — reconnect logic bunu handle eder.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Bağlantıyı düzgünce kapat. Thread-safe olmalı."""
        ...

    @abstractmethod
    def subscribe(self, symbol: str) -> None:
        """
        Tek sembol için veri akışı başlat.
        connect() başarıyla tamamlandıktan sonra çağrılır.
        """
        ...

    def subscribe_many(self, symbols: list[str]) -> None:
        """Birden fazla sembol için toplu subscribe."""
        self._symbols = list(symbols)
        for sym in symbols:
            try:
                self.subscribe(sym)
            except Exception as e:
                self._log.error(f"subscribe({sym}) hatası: {e}")

    def start(self, symbols: list[str]) -> bool:
        """
        connect() + subscribe_many() — tek adım başlatma.
        Reconnect loop'u da başlatır.
        """
        self._stats.started_at = datetime.now()
        self._symbols = list(symbols)
        ok = self._do_connect_and_subscribe()
        if ok:
            self._log.info(
                f"Collector başlatıldı: {len(symbols)} sembol "
                f"({self.__class__.__name__})"
            )
        return ok

    def stop(self) -> None:
        """Collector'ı durdur."""
        with self._lock:
            self._state = CollectorState.STOPPING
        self.disconnect()
        self._log.info("Collector durduruldu.")

    # ── Callback Kayıt ──────────────────────────────────────

    def on_quote(self, cb: Callable[[NormalizedQuote], None]) -> None:
        """Her normalize edilmiş quote'da çağrılacak fonksiyon."""
        self._quote_callbacks.append(cb)

    def on_bar(self, cb: Callable[[NormalizedBar], None]) -> None:
        """Her yeni kapalı bar'da çağrılacak fonksiyon."""
        self._bar_callbacks.append(cb)

    # ── Yayın (publish) ─────────────────────────────────────

    def _publish_quote(self, quote: NormalizedQuote) -> None:
        """
        Normalize edilmiş quote'u tüm callback'lere ilet.
        Subclass'lar throttle sonrası bunu çağırır.
        """
        self._stats.quotes_published += 1
        self._stats.last_quote_at     = quote.timestamp
        for cb in self._quote_callbacks:
            try:
                cb(quote)
            except Exception as e:
                self._log.warning(f"quote callback hatası: {e}")

    def _publish_bar(self, bar: NormalizedBar) -> None:
        """Yeni bar'ı tüm callback'lere ilet."""
        self._stats.bars_published += 1
        for cb in self._bar_callbacks:
            try:
                cb(bar)
            except Exception as e:
                self._log.warning(f"bar callback hatası: {e}")

    # ── Durum ────────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == CollectorState.CONNECTED

    @property
    def stats(self) -> CollectorStats:
        return self._stats

    @property
    def subscribed_symbols(self) -> list[str]:
        return list(self._symbols)

    # ── İç Yardımcılar ──────────────────────────────────────

    def _do_connect_and_subscribe(self) -> bool:
        """connect() + subscribe_many() — hata yakalama ile."""
        try:
            self._state = CollectorState.CONNECTING
            ok = self.connect()
            if ok:
                self._state = CollectorState.CONNECTED
                self.subscribe_many(self._symbols)
                return True
            else:
                self._state = CollectorState.DISCONNECTED
                return False
        except Exception as e:
            self._stats.error_count += 1
            self._stats.last_error   = str(e)
            self._state = CollectorState.DISCONNECTED
            self._log.error(f"Bağlantı hatası: {e}")
            return False

    def _format_stats(self) -> str:
        s = self._stats
        return (
            f"quotes={s.quotes_published} bars={s.bars_published} "
            f"drops={s.throttle_drops} reconnects={s.reconnect_count} "
            f"errors={s.error_count} uptime={s.uptime_seconds:.0f}s"
        )
