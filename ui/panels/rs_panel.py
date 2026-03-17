# ============================================================
# ui/panels/rs_panel.py
# Relative Strength Panel — FAZ 4 UI
# ============================================================
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from ui.theme import *

_LABEL_COLORS = {
    "LEADER":  "#4ade80",
    "STRONG":  "#86efac",
    "NEUTRAL": "#94a3b8",
    "LAGGARD": "#fb923c",
    "WEAK":    "#ef4444",
}

COLS = [
    ("Hisse",   55), ("RS",     55), ("Hisse%", 65),
    ("Sektör",  90), ("Rank",   40), ("Etiket", 75),
]


class RSPanel(tk.Frame):
    def __init__(self, parent, on_select: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._on_select = on_select
        self._items = []
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4); hdr.pack(fill="x")
        tk.Label(hdr, text="◈  GÖRECELİ GÜÇ (RS)",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)
        self._cnt = tk.Label(hdr, text="", font=FONT_SMALL, bg=PANEL_TITLE_BG, fg=TEXT_DIM)
        self._cnt.pack(side="right", padx=10)

        style = ttk.Style()
        style.configure("RS.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=20,
            font=FONT_SMALL, borderwidth=0)
        style.configure("RS.Treeview.Heading",
            background=BG_HEADER, foreground=COLOR_ACCENT,
            font=FONT_HEADER, relief="flat")
        style.map("RS.Treeview",
            background=[("selected", TABLE_SELECT)])

        cols = [c[0] for c in COLS]
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   style="RS.Treeview", height=8)
        for col, w in COLS:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center", stretch=False)
        self._tree.column("Sektör", stretch=True)

        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._sel)

    def update(self, rs_results: dict, show_leaders: bool = True) -> None:
        self._items = list(rs_results.values())
        if show_leaders:
            self._items = sorted(self._items, key=lambda r: r.rs_vs_index, reverse=True)
        for row in self._tree.get_children():
            self._tree.delete(row)

        for i, r in enumerate(self._items[:20]):
            col  = _LABEL_COLORS.get(r.label, TEXT_SECONDARY)
            tag  = f"rs_{i}"
            bg   = TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN
            rs_s = f"{r.rs_vs_index:+.2f}"
            self._tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                r.symbol,
                rs_s,
                f"{r.stock_return:+.2f}%",
                f"#{r.sector_rank}",
                f"#{r.universe_rank}",
                r.label,
            ))
            self._tree.tag_configure(tag, foreground=col, background=bg)

        self._cnt.config(text=f"{len(self._items)} hisse")

    def _sel(self, event):
        sel = self._tree.selection()
        if sel and self._on_select:
            idx = int(sel[0])
            if idx < len(self._items):
                self._on_select(self._items[idx].symbol)
