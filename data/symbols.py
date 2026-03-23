# ============================================================
# data/symbols.py — BIST Sembol Evrenler
# Gerçek liste borsapy Index('XU100').component_symbols'dan alındı
# ============================================================
from config import UNIVERSE

# Gerçek BIST100 bileşenleri (borsapy'den)
BIST100: list[str] = [
    "AEFES", "AGHOL", "AKBNK", "AKSA",  "AKSEN",
    "ALARK", "ALTNY", "ANSGR", "ARCLK", "ASELS",
    "ASTOR", "BALSU", "BIMAS", "BRSAN", "BRYAT",
    "BSOKE", "BTCIM", "CANTE", "CCOLA", "CIMSA",
    "CWENE", "DAPGM", "DOAS",  "DOHOL", "DSTKF",
    "ECILC", "EFOR",  "EGEEN", "EKGYO", "ENERY",
    "ENJSA", "ENKAI", "EREGL", "EUPWR", "FENER",
    "FROTO", "GARAN", "GENIL", "GESAN", "GLRMK",
    "GRSEL", "GRTHO", "GSRAY", "GUBRF", "HALKB",
    "HEKTS", "ISCTR", "ISMEN", "IZENR", "KCAER",
    "KCHOL", "KLRHO", "KONTR", "KRDMD", "KTLEV",
    "KUYAS", "MAGEN", "MAVI",  "MGROS", "MIATK",
    "MPARK", "OBAMS", "ODAS",  "OTKAR", "OYAKC",
    "PASEU", "PATEK", "PETKM", "PGSUS", "QUAGR",
    "RALYH", "REEDR", "SAHOL", "SASA",  "SISE",
    "SKBNK", "SOKM",  "TABGD", "TAVHL", "TCELL",
    "THYAO", "TKFEN", "TOASO", "TRALT", "TRENJ",
    "TRMET", "TSKB",  "TSPOR", "TTKOM", "TTRAK",
    "TUKAS", "TUPRS", "TUREX", "TURSG", "ULKER",
    "VAKBN", "VESTL", "YEOTK", "YKBNK", "ZOREN",
]

# BIST30 ve BIST50 — geriye dönük uyumluluk
BIST30: list[str] = [
    "AKBNK", "ARCLK", "ASELS", "BIMAS", "DOHOL",
    "EKGYO", "EREGL", "FROTO", "GARAN", "GUBRF",
    "HALKB", "ISCTR", "KCHOL", "KRDMD", "MGROS",
    "ODAS",  "PETKM", "PGSUS", "SAHOL", "SASA",
    "SISE",  "SOKM",  "TAVHL", "TCELL", "THYAO",
    "TKFEN", "TOASO", "TUPRS", "VAKBN", "YKBNK",
]

BIST50: list[str] = BIST30 + [
    "AEFES", "AKSEN", "ALARK", "CCOLA", "CIMSA",
    "DOAS",  "ENKAI", "MAVI",  "OTKAR", "OYAKC",
    "SKBNK", "TSKB",  "TTKOM", "ULKER", "VESTL",
    "BRYAT", "HEKTS", "ISMEN", "TUPRS", "ZOREN",
]

_UNIVERSES = {"BIST30": BIST30, "BIST50": BIST50, "BIST100": BIST100}
ACTIVE_UNIVERSE: list[str] = _UNIVERSES.get(UNIVERSE, BIST100)

def get_universe(name: str | None = None) -> list[str]:
    return _UNIVERSES.get(name or UNIVERSE, BIST100)


# Sektör mapping
SECTOR_MAP: dict[str, str] = {
    # Bankacılık
    "AKBNK": "Bankacılık", "GARAN": "Bankacılık", "HALKB": "Bankacılık",
    "ISCTR": "Bankacılık", "VAKBN": "Bankacılık", "YKBNK": "Bankacılık",
    "TSKB":  "Bankacılık", "SKBNK": "Bankacılık",
    # Otomotiv
    "FROTO": "Otomotiv", "TOASO": "Otomotiv", "OTKAR": "Otomotiv",
    "DOAS":  "Otomotiv", "TTRAK": "Otomotiv",
    # Beyaz Eşya / Elektronik
    "ARCLK": "Elektronik", "VESTL": "Elektronik",
    # Perakende
    "BIMAS": "Perakende", "MGROS": "Perakende", "SOKM": "Perakende",
    "MAVI":  "Perakende",
    # Gıda
    "ULKER": "Gıda", "CCOLA": "Gıda", "AEFES": "Gıda",
    "BALSU": "Gıda", "TUKAS": "Gıda", "TABGD": "Gıda",
    # Havacılık / Ulaşım
    "THYAO": "Havacılık", "PGSUS": "Havacılık", "TAVHL": "Havacılık",
    "FENER": "Spor", "GSRAY": "Spor", "TSPOR": "Spor",
    # Telekom
    "TCELL": "Telekom", "TTKOM": "Telekom",
    # Enerji
    "AKSEN": "Enerji", "ODAS": "Enerji", "ENERY": "Enerji",
    "ENJSA": "Enerji", "ZOREN": "Enerji", "CWENE": "Enerji",
    "EUPWR": "Enerji", "IZENR": "Enerji", "KCAER": "Enerji",
    # Petrokimya / Kimya
    "TUPRS": "Petrokimya", "PETKM": "Petrokimya", "SASA": "Kimya",
    "AKSA":  "Kimya",
    # Demir-Çelik / Metal
    "EREGL": "Demir-Çelik", "KRDMD": "Demir-Çelik", "OYAKC": "Demir-Çelik",
    "BRSAN": "Metal", "TRMET": "Metal", "TRALT": "Metal", "ALTNY": "Metal",
    # Savunma / Teknoloji
    "ASELS": "Savunma", "ASTOR": "Savunma",
    # Holding
    "KCHOL": "Holding", "SAHOL": "Holding", "DOHOL": "Holding",
    "ENKAI": "Holding", "AGHOL": "Holding", "GRTHO": "Holding",
    "KLRHO": "Holding", "RALYH": "Holding",
    # Cam / İnşaat
    "SISE":  "Cam", "BSOKE": "İnşaat", "BTCIM": "İnşaat",
    "CIMSA": "İnşaat", "CANTE": "İnşaat",
    # GYO
    "EKGYO": "GYO", "MPARK": "GYO", "OBAMS": "GYO",
    # Madencilik
    "GLRMK": "Madencilik",
    # Tarım / Gübre
    "GUBRF": "Gübre", "EGEEN": "Tarım", "QUAGR": "Tarım",
    # Finans / Sigorta
    "ANSGR": "Sigorta", "TURSG": "Sigorta", "ISMEN": "Finans",
    "REEDR": "Finans", "KTLEV": "Finans", "MAGEN": "Finans",
    "PASEU": "Finans", "PATEK": "Finans",
    # Diğer
    "BRYAT": "Turizm", "GENIL": "Diğer", "GESAN": "Diğer",
    "GRSEL": "Diğer", "DSTKF": "Diğer", "DAPGM": "Diğer",
    "ECILC": "Diğer", "EFOR":  "Diğer", "HEKTS": "Tarım",
    "KONTR": "Diğer", "KUYAS": "Diğer", "MIATK": "Diğer",
    "MPARK": "GYO",   "TABGD": "Gıda",  "TRENJ": "Enerji",
    "TUREX": "Diğer", "YEOTK": "Diğer",
}
