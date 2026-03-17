# ============================================================
# data/sector_map.py
# BIST Sektör Haritası
#
# Her sembol için statik sektör ataması.
# Sektör analizi ve görselleştirme için temel veri.
# ============================================================
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ── Sektör Tanımları ─────────────────────────────────────────

SECTORS = [
    "Bankacılık",
    "Holding",
    "Demir-Çelik",
    "Petrokimya & Enerji",
    "Otomotiv",
    "Telekom",
    "Savunma",
    "Perakende",
    "Cam & Kimya",
    "Havacılık",
    "Madencilik",
    "İnşaat & Çimento",
    "Diğer",
]

# Sembol → Sektör
SYMBOL_SECTOR: dict[str, str] = {
    # Bankacılık
    "AKBNK": "Bankacılık",
    "GARAN": "Bankacılık",
    "ISCTR": "Bankacılık",
    "HALKB": "Bankacılık",
    "YKBNK": "Bankacılık",
    "VAKBN": "Bankacılık",

    # Holding
    "KCHOL": "Holding",
    "SAHOL": "Holding",
    "DOHOL": "Holding",
    "ENKAI": "Holding",
    "BRYAT": "Holding",

    # Demir-Çelik
    "EREGL": "Demir-Çelik",
    "KRDMD": "Demir-Çelik",

    # Petrokimya & Enerji
    "TUPRS": "Petrokimya & Enerji",
    "PETKM": "Petrokimya & Enerji",
    "SASA":  "Petrokimya & Enerji",
    "GUBRF": "Petrokimya & Enerji",
    "ODAS":  "Petrokimya & Enerji",

    # Otomotiv
    "FROTO": "Otomotiv",
    "TOASO": "Otomotiv",
    "OTKAR": "Otomotiv",

    # Telekom
    "TCELL": "Telekom",
    "TTKOM": "Telekom",

    # Savunma & Teknoloji
    "ASELS": "Savunma",
    "ALARK": "Savunma",

    # Perakende
    "BIMAS": "Perakende",
    "MGROS": "Perakende",
    "SOKM":  "Perakende",
    "VESTL": "Perakende",

    # Cam & Kimya
    "SISE":  "Cam & Kimya",
    "CIMSA": "İnşaat & Çimento",
    "TKFEN": "İnşaat & Çimento",
    "EKGYO": "İnşaat & Çimento",

    # Havacılık
    "THYAO": "Havacılık",
    "PGSUS": "Havacılık",
    "TAVHL": "Havacılık",

    # Madencilik
    "KOZAL": "Madencilik",
    "KOZAA": "Madencilik",

    # Diğer
    "ARCLK": "Diğer",
}


def get_sector(symbol: str) -> str:
    """Sembolün sektörünü döndür. Bilinmiyorsa 'Diğer'."""
    return SYMBOL_SECTOR.get(symbol.upper(), "Diğer")


def get_sector_symbols(sector: str) -> list[str]:
    """Sektördeki tüm sembolleri döndür."""
    return [s for s, sec in SYMBOL_SECTOR.items() if sec == sector]


def group_by_sector(symbols: list[str]) -> dict[str, list[str]]:
    """Sembol listesini sektörlere göre grupla."""
    groups: dict[str, list[str]] = {}
    for sym in symbols:
        sec = get_sector(sym)
        groups.setdefault(sec, []).append(sym)
    return groups


# ── Sektör Performans Modeli ──────────────────────────────────

@dataclass
class SectorSnapshot:
    """Tek bir sektörün anlık performans özeti."""
    name:          str
    symbols:       list[str] = field(default_factory=list)

    # Fiyat değişimi
    avg_change_pct: float = 0.0
    advancing:      int   = 0
    declining:      int   = 0

    # Hacim
    total_volume:   float = 0.0
    avg_volume:     float = 0.0
    volume_activity: float = 0.0   # 0-100 normalize

    # Momentum & Skor
    avg_momentum:   float = 0.0
    avg_score:      float = 0.0    # combined score
    avg_rsi:        float = 50.0

    # Güç puanı (0-100)
    strength:       float = 0.0
    strength_label: str   = "—"

    # Öne çıkanlar
    top_symbol:     str = "—"
    top_change:     float = 0.0
    weak_symbol:    str = "—"
    weak_change:    float = 0.0

    # Trend etiketi
    trend_label:    str = "NÖTR"
    trend_color:    str = "#94a3b8"   # TEXT_SECONDARY benzeri

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)

    @property
    def adv_ratio(self) -> float:
        total = self.advancing + self.declining
        return self.advancing / total if total else 0.5
