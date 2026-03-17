# ============================================================
# ui/theme.py — Renk Teması & Stil Sabitleri
# ============================================================

# Ana renkler
BG_DARK       = "#0a0e1a"    # Ana arka plan
BG_PANEL      = "#0f1520"    # Panel arka planı
BG_CARD       = "#141b2d"    # Kart arka planı
BG_HEADER     = "#0c1118"    # Başlık bandı
BORDER        = "#1e2a40"    # Çerçeve rengi
BORDER_ACCENT = "#1e3a5f"    # Vurgulu çerçeve

# Metin renkleri
TEXT_PRIMARY   = "#e8edf5"
TEXT_SECONDARY = "#7a8ba0"
TEXT_DIM       = "#3d5068"

# Sinyal renkleri
COLOR_POSITIVE = "#00d4aa"   # Yeşil (yükselen)
COLOR_NEGATIVE = "#ff4d6d"   # Kırmızı (düşen)
COLOR_NEUTRAL  = "#4a6080"   # Gri (değişmeyen)
COLOR_WARNING  = "#f59e0b"   # Sarı (uyarı)
COLOR_ACCENT   = "#3b82f6"   # Mavi (vurgu)

# Kalite renkleri
QUALITY_COLORS = {
    "A+": "#00d4aa",
    "A":  "#4ade80",
    "B":  "#f59e0b",
    "C":  "#6b7280",
}

# Heatmap renk skalası (düşük → yüksek skor)
HEATMAP_COLORS = [
    "#1a1a2e",   # skor 0
    "#16213e",   # skor 1
    "#0f3460",   # skor 2
    "#1a4a7a",   # skor 3
    "#1e6b8a",   # skor 4
    "#00a896",   # skor 5
    "#00d4aa",   # skor 6 (A+)
]

# Font ailesi
FONT_MAIN   = ("Consolas", 9)
FONT_SMALL  = ("Consolas", 8)
FONT_MEDIUM = ("Consolas", 10)
FONT_LARGE  = ("Consolas", 12, "bold")
FONT_TITLE  = ("Consolas", 11, "bold")
FONT_HEADER = ("Consolas", 9, "bold")

# Panel başlık stili
PANEL_TITLE_BG = "#0c1a2e"
PANEL_TITLE_FG = "#3b82f6"

# Tablo satır renkleri
TABLE_ROW_ODD  = "#0f1520"
TABLE_ROW_EVEN = "#111827"
TABLE_SELECT   = "#1e3a5f"


# ── Merkezi TTK Stil Başlatıcı ───────────────────────────────
# Bu fonksiyon main window oluştuktan SONRA bir kez çağrılmalı.
# Her panel kendi style.configure() çağrısını yapabilir,
# ama theme_use sadece burada çağrılır.

def apply_global_ttk_theme() -> None:
    """
    Uygulama genelinde koyu ttk teması uygular.
    TradingCockpit.__init__ içinde, super().__init__() sonrası çağrılır.
    """
    from tkinter import ttk
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Notebook
    style.configure("TNotebook",          background=BG_DARK,    borderwidth=0)
    style.configure("TNotebook.Tab",
        background=BG_CARD,  foreground=TEXT_SECONDARY,
        font=FONT_HEADER,    padding=[7, 3])
    style.map("TNotebook.Tab",
        background=[("selected", PANEL_TITLE_BG)],
        foreground=[("selected", COLOR_ACCENT)])

    # Scrollbar
    style.configure("Vertical.TScrollbar",
        background=BG_HEADER, troughcolor=BG_DARK,
        borderwidth=0, arrowsize=12)
    style.map("Vertical.TScrollbar",
        background=[("active", BORDER_ACCENT)])

    # Treeview — global dark varsayılanlar
    style.configure("Treeview",
        background       = TABLE_ROW_EVEN,
        foreground       = TEXT_PRIMARY,
        fieldbackground  = TABLE_ROW_EVEN,
        rowheight        = 20,
        font             = FONT_SMALL,
        borderwidth      = 0,
        relief           = "flat")
    style.configure("Treeview.Heading",
        background       = BG_HEADER,
        foreground       = COLOR_ACCENT,
        font             = FONT_HEADER,
        relief           = "flat",
        borderwidth      = 0)
    style.map("Treeview",
        background       = [("selected", TABLE_SELECT)],
        foreground       = [("selected", TEXT_PRIMARY)])
