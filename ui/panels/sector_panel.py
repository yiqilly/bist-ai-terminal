# ============================================================
# ui/panels/sector_panel.py
# Sektör Analiz Paneli
#
# Gösterir:
#   - Sektör adı + güç puanı (renk kodlu)
#   - Hisse sayısı
#   - Ortalama değişim %
#   - Toplam hacim
#   - Yükselen / Düşen sayısı
#   - En güçlü / En zayıf hisse
#   - Sektör trend etiketi
# ============================================================
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ui.theme import *
from data.sector_map import SectorSnapshot


# Güç skoru → renk
def _strength_color(s: float) -> str:
    if s >= 75: return "#4ade80"
    if s >= 60: return "#86efac"
    if s >= 45: return "#94a3b8"
    if s >= 30: return "#fca5a5"
    return "#f87171"


# Güç skoru → bar karakteri
def _bar_chars(s: float, width: int = 10) -> str:
    filled = round(s / 100 * width)
    return "█" * filled + "░" * (width - filled)


class SectorPanel(tk.Frame):
    """
    Sektör analiz tablosu.
    Notebook tab'ı olarak yerleştirilebilir.
    """

    COLS = [
        ("Sektör",       140, "w"),
        ("Güç",           65, "center"),
        ("Bar",          110, "w"),
        ("Ort.Değ%",      70, "center"),
        ("Hacim",         80, "center"),
        ("↑/↓",           50, "center"),
        ("En Güçlü",      72, "center"),
        ("En Zayıf",      72, "center"),
        ("Trend",         90, "center"),
    ]

    def __init__(self, parent, on_sector_click: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._on_click = on_sector_click
        self._sectors: dict[str, SectorSnapshot] = {}
        self._build()

    def _build(self):
        # Başlık
        hdr = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        hdr.pack(fill="x")
        tk.Label(hdr, text="◈  SEKTÖR ANALİZİ",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)
        self._summary_lbl = tk.Label(hdr, text="",
                                      font=FONT_SMALL, bg=PANEL_TITLE_BG, fg=TEXT_SECONDARY)
        self._summary_lbl.pack(side="right", padx=10)

        # Tablo çerçevesi
        tbl_f = tk.Frame(self, bg=BG_PANEL)
        tbl_f.pack(fill="both", expand=True, padx=4, pady=4)

        # Başlık satırı
        hdr_row = tk.Frame(tbl_f, bg=BG_DARK)
        hdr_row.pack(fill="x", pady=(0, 2))
        for col, width, anchor in self.COLS:
            tk.Label(hdr_row, text=col, font=("Consolas", 8, "bold"),
                     bg=BG_DARK, fg=TEXT_DIM,
                     width=width // 8, anchor=anchor).pack(side="left", padx=1)

        # Scrollable tablo
        canvas_f = tk.Frame(tbl_f, bg=BG_PANEL)
        canvas_f.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(canvas_f, bg=BG_PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_f, orient="vertical",
                                   command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._rows_frame = tk.Frame(self._canvas, bg=BG_PANEL)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._rows_frame, anchor="nw"
        )
        self._rows_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_frame_configure(self, e):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._canvas_window, width=e.width)

    def update(self, sectors: dict[str, SectorSnapshot]) -> None:
        """Sektör snapshot'larıyla güncelle."""
        self._sectors = sectors
        # Temizle
        for w in self._rows_frame.winfo_children():
            w.destroy()

        if not sectors:
            tk.Label(self._rows_frame, text="Veri bekleniyor...",
                     font=FONT_SMALL, bg=BG_PANEL, fg=TEXT_DIM).pack(pady=20)
            return

        # Güçten zayıfa sırala
        sorted_sectors = sorted(sectors.values(),
                                  key=lambda s: s.strength, reverse=True)

        for i, ss in enumerate(sorted_sectors):
            self._build_row(ss, i)

        # Özet
        avg_strength = sum(s.strength for s in sectors.values()) / len(sectors)
        n_strong = sum(1 for s in sectors.values() if s.strength >= 60)
        self._summary_lbl.config(
            text=f"Ort. Güç: {avg_strength:.0f}  |  Güçlü: {n_strong}/{len(sectors)}"
        )

    def _build_row(self, ss: SectorSnapshot, idx: int) -> None:
        bg = BG_PANEL if idx % 2 == 0 else BG_DARK
        row = tk.Frame(self._rows_frame, bg=bg, pady=3,
                        highlightbackground=BORDER, highlightthickness=1)
        row.pack(fill="x", pady=1)

        str_col = _strength_color(ss.strength)
        chg_col = COLOR_POSITIVE if ss.avg_change_pct >= 0 else COLOR_NEGATIVE

        # Sektör adı
        tk.Label(row, text=ss.name[:18], font=FONT_SMALL,
                 bg=bg, fg=TEXT_PRIMARY, width=18, anchor="w").pack(side="left", padx=4)

        # Güç
        tk.Label(row, text=f"{ss.strength:.0f}",
                 font=("Consolas", 9, "bold"),
                 bg=bg, fg=str_col, width=5, anchor="center").pack(side="left", padx=2)

        # Bar
        bar_txt = _bar_chars(ss.strength, 10)
        tk.Label(row, text=bar_txt, font=("Consolas", 7),
                 bg=bg, fg=str_col, width=12, anchor="w").pack(side="left", padx=2)

        # Ortalama değişim
        chg_txt = f"{ss.avg_change_pct:+.2f}%"
        tk.Label(row, text=chg_txt, font=("Consolas", 8, "bold"),
                 bg=bg, fg=chg_col, width=8, anchor="center").pack(side="left", padx=2)

        # Hacim
        vol = _fmt_vol(ss.total_volume)
        tk.Label(row, text=vol, font=("Consolas", 8),
                 bg=bg, fg=TEXT_SECONDARY, width=8, anchor="center").pack(side="left", padx=2)

        # Yükselen/Düşen
        adv_txt = f"↑{ss.advancing} ↓{ss.declining}"
        adv_col = COLOR_POSITIVE if ss.advancing > ss.declining else COLOR_NEGATIVE
        tk.Label(row, text=adv_txt, font=("Consolas", 7),
                 bg=bg, fg=adv_col, width=7, anchor="center").pack(side="left", padx=2)

        # En güçlü
        top_col = COLOR_POSITIVE if ss.top_change >= 0 else COLOR_NEGATIVE
        top_txt = f"{ss.top_symbol}\n{ss.top_change:+.1f}%" if ss.top_symbol != "—" else "—"
        tk.Label(row, text=top_txt, font=("Consolas", 7),
                 bg=bg, fg=top_col, width=8, anchor="center", justify="center").pack(side="left", padx=2)

        # En zayıf
        w_col = COLOR_NEGATIVE if ss.weak_change < 0 else COLOR_POSITIVE
        w_txt = f"{ss.weak_symbol}\n{ss.weak_change:+.1f}%" if ss.weak_symbol != "—" else "—"
        tk.Label(row, text=w_txt, font=("Consolas", 7),
                 bg=bg, fg=w_col, width=8, anchor="center", justify="center").pack(side="left", padx=2)

        # Trend
        tk.Label(row, text=ss.trend_label, font=("Consolas", 7, "bold"),
                 bg=bg, fg=ss.trend_color, width=12, anchor="center").pack(side="left", padx=4)

        # Tıklama
        if self._on_click:
            row.bind("<Button-1>", lambda e, s=ss.name: self._on_click(s))


def _fmt_vol(v: float) -> str:
    if v >= 1_000_000_000: return f"{v/1_000_000_000:.1f}G"
    if v >= 1_000_000:     return f"{v/1_000_000:.0f}M"
    if v >= 1_000:         return f"{v/1_000:.0f}K"
    return str(int(v))
