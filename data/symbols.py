# ============================================================
# data/symbols.py — BIST Sembol Evrenler
# BIST30 | BIST50 | BIST100 altyapısı
# Varsayılan: BIST30
# ============================================================
from config import UNIVERSE

BIST30: list[str] = [
    "AKBNK", "ARCLK", "ASELS", "BIMAS", "DOHOL",
    "EKGYO", "EREGL", "FROTO", "GARAN", "GUBRF",
    "HALKB", "ISCTR", "KCHOL", "KOZAA", "KOZAL",
    "KRDMD", "MGROS", "ODAS",  "PETKM", "PGSUS",
    "SAHOL", "SASA",  "SISE",  "SOKM",  "TAVHL",
    "TCELL", "THYAO", "TKFEN", "TOASO", "TUPRS",
]

# BIST50 = BIST30 + 20 ek sembol
BIST50_EXTRA: list[str] = [
    "AKSEN", "ALARK", "AEFES", "ALFAS", "BRISA",
    "CCOLA", "ENKAI", "IHLGM", "LOGO",  "MAVI",
    "OTKAR", "OYAKC", "PRKME", "SKBNK", "TSKB",
    "TTKOM", "ULKER", "VAKBN", "VESBE", "YKBNK",
]
BIST50: list[str] = BIST30 + BIST50_EXTRA

# BIST100 = BIST50 + 50 ek sembol (temsili, genişletilebilir)
BIST100_EXTRA: list[str] = [
    "ADEL", "ADNAC", "AGHOL", "AKMGY", "AKSA",
    "ANACM", "ANHYT", "ANSGR", "ARKAS", "AYGAZ",
    "BAGFS", "BANVT", "BERA", "BIOEN", "BIZIM",
    "BMEKS", "BORSK", "BRYAT", "BUCIM", "CANTE",
    "CEMTS", "CIMSA", "CLEBI", "DOAS", "DOCO",
    "ECZYT", "EGEEN", "EMKEL", "ESEN", "EUPWR",
    "FLAP", "FMIZP", "GLYHO", "GOLTS", "GOZDE",
    "HEKTS", "HLGYO", "HUNER", "INDES", "IPEKE",
    "ISCTR", "ISGYO", "ISMEN", "IZFAS", "JANTS",
    "KARSN", "KATMR", "KAYSE", "KERVT", "KORDS",
]
BIST100: list[str] = BIST50 + BIST100_EXTRA

# Aktif evren — config'e göre seçilir
_UNIVERSES = {"BIST30": BIST30, "BIST50": BIST50, "BIST100": BIST100}
ACTIVE_UNIVERSE: list[str] = _UNIVERSES.get(UNIVERSE, BIST30)

def get_universe(name: str | None = None) -> list[str]:
    """Config veya parametre ile evren seç."""
    return _UNIVERSES.get(name or UNIVERSE, BIST30)

# Sektör mapping (BIST30 + ek semboller)
SECTOR_MAP: dict[str, str] = {
    "AKBNK": "Bankacılık",  "GARAN": "Bankacılık",
    "HALKB": "Bankacılık",  "ISCTR": "Bankacılık",
    "VAKBN": "Bankacılık",  "YKBNK": "Bankacılık",
    "TSKB":  "Bankacılık",  "SKBNK": "Bankacılık",
    "FROTO": "Otomotiv",    "TOASO": "Otomotiv",
    "OTKAR": "Otomotiv",
    "ARCLK": "Beyaz Eşya",  "VESBE": "Beyaz Eşya",
    "BIMAS": "Perakende",   "MGROS": "Perakende",
    "SOKM":  "Perakende",   "MAVI":  "Perakende",
    "ULKER": "Gıda",        "CCOLA": "Gıda",
    "AEFES": "Gıda",        "BANVT": "Gıda",
    "THYAO": "Havacılık",   "PGSUS": "Havacılık",
    "TAVHL": "Havacılık",   "CLEBI": "Havacılık",
    "TCELL": "Telekom",     "TTKOM": "Telekom",
    "TUPRS": "Enerji",      "AKSEN": "Enerji",
    "ODAS":  "Enerji",      "AYGAZ": "Enerji",
    "PETKM": "Petrokimya",  "SASA":  "Kimya",
    "EREGL": "Demir-Çelik", "KRDMD": "Demir-Çelik",
    "OYAKC": "Demir-Çelik",
    "ASELS": "Savunma",
    "KCHOL": "Holding",     "SAHOL": "Holding",
    "DOHOL": "Holding",     "ENKAI": "Holding",
    "SISE":  "Cam",         "ANACM": "Cam",
    "EKGYO": "GYO",         "ISGYO": "GYO",
    "HLGYO": "GYO",         "AKMGY": "GYO",
    "KOZAL": "Madencilik",  "KOZAA": "Madencilik",
    "GUBRF": "Gübre",       "BAGFS": "Gübre",
    "TKFEN": "İnşaat",      "CIMSA": "İnşaat",
    "BUCIM": "İnşaat",      "CEMTS": "İnşaat",
    "BRISA": "Lastik",
    "LOGO":  "Yazılım",     "INDES": "Yazılım",
    "ALFAS": "Finans",
    "TSKB":  "Bankacılık",
    "ALARK": "Diğer",       "IHLGM": "Diğer",
    "PRKME": "Diğer",
}
