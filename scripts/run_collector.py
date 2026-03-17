#!/usr/bin/env python3
# ============================================================
# scripts/run_collector.py
# Collector Test / Standalone Çalıştırıcı
#
# Kullanım:
#   cd bist_terminal
#   python scripts/run_collector.py
#   python scripts/run_collector.py --source borsapy --symbols THYAO,GARAN,AKBNK
#   python scripts/run_collector.py --source mock --verbose
#   python scripts/run_collector.py --source borsapy --session TOKEN --session-sign SIGN
#
# Seçenekler:
#   --source   : borsapy | mock  (varsayılan: config'den)
#   --symbols  : Virgülle ayrılmış semboller (varsayılan: ilk 5)
#   --verbose  : Her bar için ayrıntılı çıktı
#   --session  : TradingView session token (opsiyonel)
#   --session-sign : TradingView session_sign token
#   --config   : Alternatif config dosyası yolu
#   --duration : Kaç saniye çalışsın (0=sonsuz, varsayılan: 0)
# ============================================================
from __future__ import annotations

import argparse
import signal
import sys
import os
import time
import threading
from datetime import datetime

# Proje kökünü path'e ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.collector_bridge import load_config, make_collector
from data.collectors.base_collector import NormalizedQuote, NormalizedBar
from utils.collector_logger import setup_collector_logging


# ── Konsol Çıktısı ───────────────────────────────────────────

class ConsolePrinter:
    """Quote ve bar'ları formatlanmış şekilde konsola basar."""

    def __init__(self, verbose: bool = False):
        self._verbose = verbose
        self._lock    = threading.Lock()
        self._counts: dict[str, int] = {}

    def on_quote(self, quote: NormalizedQuote) -> None:
        # Her sembolden sadece belirli sıklıkta yazdır (flood önleme)
        count = self._counts.get(quote.symbol, 0) + 1
        self._counts[quote.symbol] = count

        if count % 5 != 0:   # Her 5 update'te bir yazdır
            return

        bid_str = f"bid={quote.bid:.2f}" if quote.bid else ""
        ask_str = f"ask={quote.ask:.2f}" if quote.ask else ""
        vol_str = _fmt_vol(quote.volume)
        chg_str = f"{quote.change_pct:+.2f}%" if quote.change_pct else ""

        with self._lock:
            print(
                f"\033[36m[QUOTE]\033[0m "
                f"\033[1m{quote.symbol:<8}\033[0m "
                f"\033[33m{quote.last:>10.2f}\033[0m  "
                f"{bid_str:<16} {ask_str:<16} "
                f"vol={vol_str:<8} {chg_str}"
            )

    def on_bar(self, bar: NormalizedBar) -> None:
        if not bar.is_closed:
            return

        col  = "\033[32m" if bar.close >= bar.open else "\033[31m"
        body = bar.close - bar.open
        sign = "▲" if body >= 0 else "▼"

        with self._lock:
            print(
                f"\033[35m[BAR {bar.timeframe:>2}]\033[0m "
                f"\033[1m{bar.symbol:<8}\033[0m "
                f"O:{bar.open:<8.2f} "
                f"H:{bar.high:<8.2f} "
                f"L:{bar.low:<8.2f} "
                f"{col}C:{bar.close:<8.2f}{sign}\033[0m "
                f"V:{bar.fmt_volume():<8} "
                f"@ {bar.start_time.strftime('%H:%M')}"
            )

    def print_stats(self, collector) -> None:
        s = collector.stats
        print(
            f"\n\033[90m--- Stats | "
            f"quotes={s.quotes_published} "
            f"bars={s.bars_published} "
            f"drops={s.throttle_drops} "
            f"reconnects={s.reconnect_count} "
            f"errors={s.error_count} "
            f"uptime={s.uptime_seconds:.0f}s ---\033[0m"
        )


def _fmt_vol(v: float) -> str:
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000:     return f"{v/1_000:.0f}K"
    return str(int(v))


# ── Argüman Ayrıştırma ───────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="BIST Trading Terminal — Data Collector"
    )
    p.add_argument("--source",      type=str, default="",
                   help="Veri kaynağı: borsapy | mock")
    p.add_argument("--symbols",     type=str, default="",
                   help="Virgülle ayrılmış semboller")
    p.add_argument("--verbose",     action="store_true",
                   help="Detaylı çıktı")
    p.add_argument("--session",     type=str, default="",
                   help="TradingView session token")
    p.add_argument("--session-sign",type=str, default="",
                   help="TradingView session_sign token")
    p.add_argument("--config",      type=str, default="",
                   help="Config dosyası yolu")
    p.add_argument("--duration",    type=int, default=0,
                   help="Çalışma süresi saniye (0=sonsuz)")
    p.add_argument("--log-level",   type=str, default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


# ── Ana Fonksiyon ────────────────────────────────────────────

def main():
    args = parse_args()

    # Config yükle
    cfg = load_config(args.config or None)

    # Loglama kur
    log_cfg = cfg.get("logging", {})
    setup_collector_logging(
        log_file     = log_cfg.get("file", "logs/collector.log"),
        level_str    = args.log_level or log_cfg.get("level", "INFO"),
        max_bytes    = log_cfg.get("max_bytes", 5 * 1024 * 1024),
        backup_count = log_cfg.get("backup_count", 3),
        console      = True,
    )

    # Semboller
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = cfg.get("symbols", [])[:5]   # Varsayılan: ilk 5

    # Session varsa config'e ekle
    if args.session:
        cfg.setdefault("borsapy", {})["session"]      = args.session
    if args.session_sign:
        cfg.setdefault("borsapy", {})["session_sign"] = args.session_sign

    source = args.source or cfg.get("active_source", "mock")

    # ── Başlık ──────────────────────────────────────────────
    print("\n" + "=" * 62)
    print("  BIST Data Collector — Gerçek Zamanlı Veri Akışı")
    print("=" * 62)
    print(f"  Kaynak   : {source.upper()}")
    print(f"  Semboller: {', '.join(symbols)}")
    print(f"  Süre     : {'Sonsuz' if args.duration == 0 else f'{args.duration}s'}")
    print(f"  Zaman    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 62 + "\n")

    # ── Collector Oluştur ────────────────────────────────────
    collector = make_collector(source=source, config=cfg)
    printer   = ConsolePrinter(verbose=args.verbose)

    collector.on_quote(printer.on_quote)
    collector.on_bar(printer.on_bar)

    # ── Ctrl+C handler ───────────────────────────────────────
    stop_flag = threading.Event()

    def _sig_handler(sig, frame):
        print("\n\n\033[33mDurduruluyor...\033[0m")
        stop_flag.set()

    signal.signal(signal.SIGINT,  _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    # ── Başlat ───────────────────────────────────────────────
    ok = collector.start(symbols=symbols)
    if not ok:
        print("\033[31m[HATA] Collector başlatılamadı!\033[0m")
        print("  borsapy için: pip install borsapy")
        print("  Veya --source mock ile mock mod kullan")
        sys.exit(1)

    print(f"\033[32m✓ Collector başlatıldı ({collector.__class__.__name__})\033[0m")
    print("  Veri akışı bekleniyor... (Durdurmak için Ctrl+C)\n")

    # ── Çalışma döngüsü ──────────────────────────────────────
    start_time = time.time()
    stats_interval = 15   # Her 15 saniyede stats bas

    try:
        while not stop_flag.is_set():
            elapsed = time.time() - start_time

            if args.duration > 0 and elapsed >= args.duration:
                break

            if int(elapsed) % stats_interval == 0 and int(elapsed) > 0:
                printer.print_stats(collector)

            time.sleep(0.5)

    finally:
        printer.print_stats(collector)
        collector.stop()
        print("\n\033[32m✓ Collector durduruldu.\033[0m\n")


if __name__ == "__main__":
    main()
