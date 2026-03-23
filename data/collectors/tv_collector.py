# ============================================================
# data/collectors/tv_collector.py — v4
#
# DÜZELTMELER:
# 1. subscribe_chart() TAMAMEN KAPATILDI
#    → duplicate id / create_series hatalarının tek kaynağı bu
#    → Bar verisi BarBuilder'ın quote-tabanlı fallback'inden geliyor
#    → Kullanıcı isterseı config'den subscribe_chart'ı açabilir
#
# 2. BIST:KOZAA no_such_symbol
#    → borsapy bazı sembolleri için BIST: prefix ile gönderip
#      TradingView'dan hata alıyor
#    → Bizim tarafımızda normalize ediyoruz ama borsapy içinde
#      subscribe() çağrısına sadece sembol adı gönderiyoruz (KOZAA)
#    → Gelen callback'lerde prefix strip yapıyoruz
#
# 3. WebSocket error fin=1 opcode=8
#    → borsapy'nin bağlantısı koptu, normal
#    → reconnect watcher handle ediyor
#
# 4. Tüm dedup ve heartbeat filtreler korundu
# ============================================================
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional

from data.collectors.base_collector import (
    BaseCollector, CollectorState,
    NormalizedQuote, NormalizedBar,
)
from data.collectors.tv_symbol_map import (
    normalize_incoming, normalize_for_subscribe, is_valid_symbol,
)
from data.bar_builder import BarBuilder


# ── Heartbeat / Control Paket Filtresi ──────────────────────

_HEARTBEAT_PREFIXES = ("~h~", "~m~", "~j~")

def _is_control_packet(data) -> bool:
    if isinstance(data, str):
        s = data.strip()
        return s.startswith(_HEARTBEAT_PREFIXES) or s in ("", "null", "undefined")
    return isinstance(data, (int, float))


# ── Throttle ─────────────────────────────────────────────────

class _ThrottleGate:
    def __init__(self, max_per_sec: int = 10):
        self._max    = max_per_sec
        self._counts: dict[str, int]   = defaultdict(int)
        self._window: dict[str, float] = defaultdict(float)
        self._drops  = 0

    def allow(self, symbol: str) -> bool:
        now = time.monotonic()
        if now - self._window[symbol] >= 1.0:
            self._window[symbol] = now
            self._counts[symbol] = 1
            return True
        if self._counts[symbol] < self._max:
            self._counts[symbol] += 1
            return True
        self._drops += 1
        return False

    @property
    def total_drops(self) -> int:
        return self._drops


# ── Subscription Registry ────────────────────────────────────

class _SubscriptionRegistry:
    def __init__(self):
        self._lock    = threading.Lock()
        self._quotes: set[str]              = set()
        self._charts: set[tuple[str, str]]  = set()
        self._series_ids: dict[tuple[str, str], str] = {}

    def can_quote(self, sym: str) -> bool:
        with self._lock: return sym not in self._quotes

    def mark_quote(self, sym: str) -> None:
        with self._lock: self._quotes.add(sym)

    def can_chart(self, sym: str, tf: str) -> bool:
        with self._lock: return (sym, tf) not in self._charts

    def mark_chart(self, sym: str, tf: str) -> None:
        with self._lock: self._charts.add((sym, tf))

    def series_id(self, sym: str, tf: str) -> str:
        key = (sym, tf)
        with self._lock:
            if key not in self._series_ids:
                uid = hashlib.md5(f"bist_{sym}_{tf}".encode()).hexdigest()[:12]
                self._series_ids[key] = f"s_{uid}"
            return self._series_ids[key]

    def clear(self) -> None:
        with self._lock:
            self._quotes.clear()
            self._charts.clear()
            self._series_ids.clear()


# ── TradingView Collector ────────────────────────────────────

class TradingViewCollector(BaseCollector):
    SOURCE = "borsapy"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        cfg = config or {}

        self._stream      = None
        self._stream_lock = threading.Lock()
        self._registry    = _SubscriptionRegistry()

        max_tps = cfg.get("max_ticks_per_second", 10)
        self._throttle = _ThrottleGate(max_per_sec=max_tps)

        tf_list = cfg.get("timeframes", ["1m", "5m"])
        self._bar_builder = BarBuilder(timeframes=tf_list, max_bars=200)
        self._bar_builder.on_bar(self._on_built_bar)

        self._backoff_seq    = cfg.get("reconnect_backoff", [2, 5, 10, 30])
        self._max_reconnects = cfg.get("max_reconnect_attempts", 0)
        self._reconnect_thread: Optional[threading.Thread] = None
        self._stop_event   = threading.Event()

        # subscribe_chart varsayılan KAPALI
        # Duplicate id sorununu çözdü — bar verisi BarBuilder'dan geliyor
        self._enable_chart_subscribe = cfg.get("enable_chart_subscribe", False)

        self._session      = cfg.get("session", "")
        self._session_sign = cfg.get("session_sign", "")
        self._skipped:     list[str] = []
        self._log = logging.getLogger("TradingViewCollector")

    # ── Bağlantı ─────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            import borsapy as bp
        except ImportError:
            self._log.error(
                "borsapy kurulu değil!\n"
                "Kur: pip install git+https://github.com/saidsurucu/borsapy.git"
            )
            return False

        try:
            if self._session and self._session_sign:
                try:
                    bp.set_tradingview_auth(
                        session=self._session,
                        session_sign=self._session_sign,
                    )
                except Exception as e:
                    self._log.warning(f"Auth: {e}")

            stream = bp.TradingViewStream()
            stream.connect()

            # Global callback'ler — bağlantı başında bir kez
            stream.on_any_quote(self._safe_on_quote)

            # Chart callback'i sadece subscribe_chart açıksa kayıt et
            if self._enable_chart_subscribe:
                stream.on_any_candle(self._safe_on_candle)

            with self._stream_lock:
                self._stream = stream

            self._log.info(
                f"TradingView stream bağlandı "
                f"(chart_subscribe={'açık' if self._enable_chart_subscribe else 'kapalı'})"
            )
            return True

        except Exception as e:
            self._log.error(f"connect() başarısız: {e}")
            self._stats.error_count += 1
            self._stats.last_error   = str(e)
            return False

    def disconnect(self) -> None:
        self._stop_event.set()
        with self._stream_lock:
            s, self._stream = self._stream, None
        if s:
            try: s.disconnect()
            except Exception: pass
        self._state = CollectorState.DISCONNECTED

    # ── Subscribe ─────────────────────────────────────────────

    def subscribe(self, symbol: str) -> None:
        """
        Quote subscribe.
        Sembolü normalize et (BIST: prefix'i zaten borsapy ekliyor,
        biz sadece temiz sembol adı gönderiyoruz).
        """
        tv_sym = normalize_for_subscribe(symbol)
        if tv_sym is None:
            self._log.warning(f"Geçersiz sembol atlandı: {symbol!r}")
            if symbol not in self._skipped:
                self._skipped.append(symbol)
            return

        if not self._registry.can_quote(tv_sym):
            return

        with self._stream_lock:
            if not self._stream:
                return
            try:
                # Sadece temiz sembol adı — borsapy prefix'i kendiisi ekliyor
                self._stream.subscribe(tv_sym)
                self._registry.mark_quote(tv_sym)
                self._log.debug(f"Quote abone: {tv_sym}")
            except Exception as e:
                err = str(e).lower()
                if "no_such_symbol" in err or "no such" in err:
                    self._log.warning(
                        f"Sembol bulunamadı: {tv_sym} — "
                        "TradingView'da mevcut olmayabilir"
                    )
                    if tv_sym not in self._skipped:
                        self._skipped.append(tv_sym)
                else:
                    self._log.error(f"subscribe({tv_sym}): {e}")

    def _subscribe_charts_batch(self, symbols: list[str]) -> None:
        """
        Chart (candle) aboneliği.
        VARSAYILAN KAPALI — enable_chart_subscribe=True yapılmadan çalışmaz.

        Açmak istersen config/data_sources.yaml'a ekle:
            enable_chart_subscribe: true

        ⚠ UYARI: duplicate id hatalarına yol açabilir.
        300ms gecikmeyle kademeli açılıyor.
        """
        if not self._enable_chart_subscribe:
            return

        timeframes = self._config.get("timeframes", ["1m", "5m"])
        for symbol in symbols:
            if self._stop_event.is_set():
                break
            tv_sym = normalize_for_subscribe(symbol)
            if tv_sym is None:
                continue
            if tv_sym in self._skipped:
                continue   # bulunamayan semboller atla

            for tf in timeframes:
                if self._stop_event.is_set():
                    break
                if not self._registry.can_chart(tv_sym, tf):
                    continue

                with self._stream_lock:
                    if not self._stream:
                        return
                    try:
                        self._stream.subscribe_chart(tv_sym, tf)
                        self._registry.mark_chart(tv_sym, tf)
                        self._log.debug(f"Chart abone: {tv_sym} {tf}")
                    except Exception as e:
                        err = str(e).lower()
                        if "duplicate" in err or "create_series" in err:
                            self._log.debug(f"Chart {tv_sym}/{tf} duplicate — atlandı")
                            self._registry.mark_chart(tv_sym, tf)
                        elif "no_such_symbol" in err:
                            self._log.warning(f"Chart sembol bulunamadı: {tv_sym}")
                        else:
                            self._log.warning(f"subscribe_chart({tv_sym} {tf}): {e}")

                time.sleep(0.30)

    # ── Safe Callback Wrapper'ları ────────────────────────────

    def _safe_on_quote(self, symbol, raw) -> None:
        """Heartbeat ve geçersiz paketleri filtrele."""
        if _is_control_packet(raw) or _is_control_packet(symbol):
            return
        # borsapy bazen "BIST:THYAO" formatında gönderebilir → normalize et
        clean = normalize_incoming(str(symbol))
        if not clean or not is_valid_symbol(clean):
            return
        self._on_raw_quote(clean, raw if isinstance(raw, dict) else {})

    def _safe_on_candle(self, symbol, interval, raw) -> None:
        if _is_control_packet(raw) or _is_control_packet(symbol):
            return
        clean = normalize_incoming(str(symbol))
        if not clean or not is_valid_symbol(clean):
            return
        self._on_raw_candle(clean, str(interval), raw if isinstance(raw, dict) else {})

    # ── Quote İşleme ─────────────────────────────────────────

    def _on_raw_quote(self, symbol: str, raw: dict) -> None:
        self._stats.quotes_received += 1
        if not self._throttle.allow(symbol):
            self._stats.throttle_drops += 1
            return
        try:
            last = _sf(raw.get("last") or raw.get("lp") or raw.get("price"))
            if last <= 0:
                return

            quote = NormalizedQuote(
                symbol     = symbol,
                last       = last,
                bid        = _sf(raw.get("bid")  or raw.get("bp"),  last),
                ask        = _sf(raw.get("ask")  or raw.get("ap"),  last),
                volume     = _sf(raw.get("volume") or raw.get("vol") or raw.get("volume_d")),
                timestamp  = datetime.now(),
                change_pct = _sf(raw.get("change_percent") or raw.get("ch") or raw.get("chp")),
                prev_close = _sf(raw.get("prev_close") or raw.get("pc")),
                high_day   = _sf(raw.get("high") or raw.get("high_price")),
                low_day    = _sf(raw.get("low")  or raw.get("low_price")),
                source     = self.SOURCE,
            )
            # BarBuilder'a gönder — quote'lardan 1m/5m bar üretir
            self._bar_builder.on_tick(quote)
            self._publish_quote(quote)

        except Exception as e:
            self._stats.error_count += 1
            self._stats.last_error   = str(e)
            self._log.debug(f"quote hata ({symbol}): {e}")

    # ── Candle İşleme ─────────────────────────────────────────

    def _on_raw_candle(self, symbol: str, interval: str, raw: dict) -> None:
        """
        Sadece enable_chart_subscribe=True ise çalışır.
        """
        self._stats.bars_received += 1
        try:
            ts = raw.get("time") or raw.get("t") or 0
            try:
                bar_time = datetime.fromtimestamp(float(ts)) if ts else datetime.now()
            except (ValueError, OSError):
                bar_time = datetime.now()

            close = _sf(raw.get("close") or raw.get("c"))
            if close <= 0:
                return

            bar = NormalizedBar(
                symbol     = symbol,
                timeframe  = interval,
                open       = _sf(raw.get("open")   or raw.get("o"),  close),
                high       = _sf(raw.get("high")   or raw.get("h"),  close),
                low        = _sf(raw.get("low")    or raw.get("l"),  close),
                close      = close,
                volume     = _sf(raw.get("volume") or raw.get("v")),
                start_time = bar_time,
                is_closed  = bool(raw.get("is_closed", True)),
                source     = self.SOURCE,
            )
            self._publish_bar(bar)
        except Exception as e:
            self._stats.error_count += 1
            self._stats.last_error   = str(e)
            self._log.debug(f"candle hata ({symbol}/{interval}): {e}")

    def _on_built_bar(self, bar: NormalizedBar) -> None:
        """BarBuilder'dan gelen quote-tabanlı bar."""
        if bar.is_closed:
            self._publish_bar(bar)

    # ── Başlatma ─────────────────────────────────────────────

    def start(self, symbols: list[str]) -> bool:
        self._stop_event.clear()
        ok = super().start(symbols)
        if ok:
            if self._enable_chart_subscribe:
                threading.Thread(
                    target=self._subscribe_charts_batch,
                    args=(list(symbols),), daemon=True,
                    name="tv-chart-subscribe",
                ).start()

            self._reconnect_thread = threading.Thread(
                target=self._reconnect_watcher,
                daemon=True, name="tv-reconnect",
            )
            self._reconnect_thread.start()
            self._log.info(
                f"TradingViewCollector başladı: {len(symbols)} sembol"
            )
        return ok

    # ── Reconnect ─────────────────────────────────────────────

    def _reconnect_watcher(self) -> None:
        attempt = 0
        backoff  = list(self._backoff_seq)
        while not self._stop_event.is_set():
            time.sleep(3.0)
            if self._stop_event.is_set():
                break
            if self._state in (CollectorState.STOPPING, CollectorState.RECONNECTING):
                continue
            if self._state == CollectorState.CONNECTED and self._stream:
                attempt = 0
                continue

            self._state = CollectorState.RECONNECTING
            self._stats.reconnect_count += 1
            delay = backoff[min(attempt, len(backoff) - 1)]
            self._log.warning(f"Bağlantı koptu. {delay}s sonra yeniden... (#{attempt+1})")
            time.sleep(delay)
            if self._stop_event.is_set():
                break

            with self._stream_lock:
                self._stream = None
            self._registry.clear()

            ok = self._do_connect_and_subscribe()
            if ok:
                if self._enable_chart_subscribe:
                    threading.Thread(
                        target=self._subscribe_charts_batch,
                        args=(list(self._symbols),), daemon=True,
                    ).start()
                self._log.info(f"Yeniden bağlandı (#{attempt+1})")
                attempt = 0
            else:
                attempt += 1
                if self._max_reconnects > 0 and attempt >= self._max_reconnects:
                    self._log.error("Max reconnect aşıldı.")
                    break

    def status_line(self) -> str:
        s = self._stats
        chart_mode = "chart=ON" if self._enable_chart_subscribe else "chart=OFF"
        return (
            f"[TV] {self._state} {chart_mode} | "
            f"Q={s.quotes_published} B={s.bars_published} "
            f"drop={s.throttle_drops} recon={s.reconnect_count}"
            + (f" skip={self._skipped}" if self._skipped else "")
        )


# ── Yardımcı ─────────────────────────────────────────────────

def _sf(val, default: float = 0.0) -> float:
    if val is None: return default
    try:
        r = float(val)
        return r if r == r else default
    except (ValueError, TypeError):
        return default
