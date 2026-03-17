# ============================================================
# utils/collector_logger.py
# Collector Loglama Altyapısı
#
# Özellikler:
#   - Rotating file handler (5MB × 3 backup)
#   - Renkli console output (terminal)
#   - Collector / BarBuilder / Bridge için hazır logger'lar
# ============================================================
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path


# ── ANSI Renk Kodları ────────────────────────────────────────

class _ColorFormatter(logging.Formatter):
    """Console için renkli log çıktısı."""

    COLORS = {
        logging.DEBUG:    "\033[37m",    # Gri
        logging.INFO:     "\033[32m",    # Yeşil
        logging.WARNING:  "\033[33m",    # Sarı
        logging.ERROR:    "\033[31m",    # Kırmızı
        logging.CRITICAL: "\033[35m",    # Mor
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color  = self.COLORS.get(record.levelno, "")
        msg    = super().format(record)
        return f"{color}{msg}{self.RESET}"


# ── Logger Fabrikası ─────────────────────────────────────────

def setup_collector_logging(
    log_file:     str  = "logs/collector.log",
    level_str:    str  = "INFO",
    max_bytes:    int  = 5 * 1024 * 1024,   # 5 MB
    backup_count: int  = 3,
    console:      bool = True,
) -> None:
    """
    Tüm collector bileşenlerinin kullandığı logging konfigürasyonu.
    main.py veya run_collector.py'de bir kez çağrılır.
    """
    level = getattr(logging, level_str.upper(), logging.INFO)

    # Log klasörü oluştur
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    # Root logger değil — sadece collector bileşenlerini konfigure et
    loggers = [
        "TradingViewCollector",
        "MockCollector",
        "CollectorBridge",
        "BarBuilder",
        "MarketBus",
    ]

    fmt_file    = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt_console = _ColorFormatter(
        "%(asctime)s [%(levelname)-7s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    # Rotating file handler
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt_file)
        file_handler.setLevel(level)
    except Exception as e:
        print(f"[Logging] Dosya handler oluşturulamadı: {e}", file=sys.stderr)
        file_handler = None

    # Console handler
    if console:
        con_handler = logging.StreamHandler(sys.stdout)
        con_handler.setFormatter(fmt_console)
        con_handler.setLevel(level)
    else:
        con_handler = None

    for name in loggers:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers.clear()
        logger.propagate = False

        if file_handler:
            logger.addHandler(file_handler)
        if con_handler:
            logger.addHandler(con_handler)


def get_logger(name: str) -> logging.Logger:
    """Hazır konfigüre edilmiş logger döndür."""
    return logging.getLogger(name)

# ── borsapy / WebSocket gürültü loglarını sustur ─────────────
# "Failed to parse packet", "Quote error for BIST:xxx",
# "WebSocket error" gibi borsapy'nin kendi iç logları
# terminale çıkmasın.

def silence_borsapy_noise() -> None:
    """
    borsapy, websocket-client ve ilgili kütüphanelerin
    gürültülü loglarını ERROR seviyesine çek.
    """
    noisy_loggers = [
        "borsapy",
        "borsapy.stream",
        "borsapy.tv",
        "websocket",
        "websocket._core",
        "websockets",
        "urllib3",
        "urllib3.connectionpool",
    ]
    for name in noisy_loggers:
        lg = logging.getLogger(name)
        lg.setLevel(logging.ERROR)
        lg.propagate = False
