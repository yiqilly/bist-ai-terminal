# ============================================================
# data/collectors/tv_symbol_map.py
# TradingView Symbol Normalization
#
# Sorun: borsapy bazen BIST:KOZAA, BIST:THYAO gibi prefix'li
# semboller gönderiyor veya bekliyor. TradingView'ın sembol
# formatı exchange:symbol şeklinde. Bazı BIST sembolleri
# TradingView'da farklı isimle listeleniyor.
#
# Bu modül:
#   - Gelen sembolden prefix'i temizler (BIST:KOZAA → KOZAA)
#   - subscribe() için doğru TV formatına çevirir
#   - Geçersiz / bilinmeyen sembolleri filtreler
# ============================================================
from __future__ import annotations

import re

# ── BIST → TradingView sembol eşleştirme ────────────────────
# Çoğu sembol doğrudan eşleşir.
# Farklı isimle listelenenler için override map.
_TV_OVERRIDE: dict[str, str] = {
    # BIST kodu → TradingView symbol (exchange prefix'siz)
    "KOZAA": "KOZAA",   # BIST:KOZAA — doğrudan çalışıyor
    "KOZAL": "KOZAL",   # BIST:KOZAL
    "ODAS":  "ODAS",
    "GUBRF": "GUBRF",
    "TKFEN": "TKFEN",
    "SOKM":  "SOKM",
    "SASA":  "SASA",
    # Genel kural: BIST sembolü → büyük harf, prefix yok
    # borsapy subscribe() prefix olmadan alıyor: stream.subscribe("THYAO")
}

# TradingView'da aktif olan BIST30 sembolleri
# (borsapy bu sembolleri doğrudan kabul ediyor)
_VALID_BIST30: frozenset[str] = frozenset([
    "AKBNK", "ARCLK", "ASELS", "BIMAS", "DOHOL",
    "EKGYO", "EREGL", "FROTO", "GARAN", "GUBRF",
    "HALKB", "ISCTR", "KCHOL", "KOZAA", "KOZAL",
    "KRDMD", "MGROS", "ODAS",  "PETKM", "PGSUS",
    "SAHOL", "SASA",  "SISE",  "SOKM",  "TAVHL",
    "TCELL", "THYAO", "TKFEN", "TOASO", "TUPRS",
])

# Callback'lerde gelen symbol → normalize edilmiş BIST kodu
# borsapy bazen "BIST:THYAO" veya "IST:THYAO" döndürüyor
_PREFIX_RE = re.compile(r'^(?:BIST|IST|BORSA|XIST)[:\./]', re.IGNORECASE)


def normalize_incoming(raw_symbol: str) -> str:
    """
    borsapy callback'inden gelen ham sembolü normalize et.
    Örnekler:
        "BIST:THYAO"  → "THYAO"
        "IST:KOZAA"   → "KOZAA"
        "THYAO"       → "THYAO"
        "thyao"       → "THYAO"
    """
    sym = _PREFIX_RE.sub("", raw_symbol).strip().upper()
    # Alt sembol varsa (THYAO/TRY → THYAO)
    sym = sym.split("/")[0].split(".")[0]
    return sym


def normalize_for_subscribe(symbol: str) -> str | None:
    """
    BIST sembolünü borsapy subscribe() için hazırla.
    Geçersizse None döndür.
    """
    clean = symbol.strip().upper()
    if not is_valid_symbol(clean):
        return None
    return _TV_OVERRIDE.get(clean, clean)


def is_valid_symbol(symbol: str) -> bool:
    """Sembolün aktif evrende olup olmadığını kontrol et."""
    from data.symbols import ACTIVE_UNIVERSE
    return symbol.strip().upper() in ACTIVE_UNIVERSE


def get_all_valid() -> list[str]:
    from data.symbols import ACTIVE_UNIVERSE
    return sorted(ACTIVE_UNIVERSE)
