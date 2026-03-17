# ============================================================
# utils/logger.py — Loglama Yapılandırması
# ============================================================
import logging
import sys
from config import LOG_LEVEL


def setup_logger(name: str = "bist_terminal") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%H:%M:%S"
        ))
        logger.addHandler(handler)
    return logger

# Alias — main.py ve diğer modüller için
setup_logging = setup_logger
