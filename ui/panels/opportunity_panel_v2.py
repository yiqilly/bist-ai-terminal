# ============================================================
# ui/panels/opportunity_panel_v2.py
# Opportunity Panel v2 — FAZ 5 UI
# Az sayıda, yüksek kaliteli fırsat gösterir.
# ============================================================
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from ui.theme import *

_QL_COLORS = {
    "A+": "#4ade80", "A": "#86efac", "B": "#fbbf24",
}
_SETUP_ICONS = {
    "BREAKOUT":        "⚡",
    "PULLBACK_REBREAK":"🔄",
    "SECTOR_LEADER":   "🏆",
    "MOMENTUM_SURGE":  "🚀",
}
COLS = [
    ("Hisse",   55), ("Setup",   100), ("Skor",   45),
    ("R/R",     45), ("Güven",   50),  ("Sektör", 90),
    ("Kal.",    40), ("Sebep",  180),
]


class OpportunityPanelV2(tk.Frame):
    def __init__(self, parent, on_select: Optional[Callable] = None,
                 on_buy: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._on_select = on_select
        self._on_buy    = on_buy
        self._items     = []
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4); hdr.pack(fill="x")
        tk.Label(hdr, text="◈  FIRSAT MOTORU",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)
        self._cnt = tk.Label(hdr, text="0 fırsat",
                              font=FONT_SMALL, bg=PANEL_TITLE_BG, fg=TEXT_DIM)
        self._cnt.pack(side="right", padx=10)

        style = ttk.Style()
        style.configure("OppV2.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=22,
            font=FONT_SMALL, borderwidth=0)
        style.configure("OppV2.Treeview.Heading",
            background=BG_HEADER, foreground=COLOR_ACCENT,
            font=FONT_HEADER, relief="flat")
        style.map("OppV2.Treeview",
            background=[("selected", TABLE_SELECT)])

        cols = [c[0] for c in COLS]
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   style="OppV2.Treeview", height=10)
        for col, w in COLS:
            self._tree.heading(col, text=col)
            anchor = "w" if col == "Sebep" else "center"
            self._tree.column(col, width=w, anchor=anchor,
                               stretch=(col == "Sebep"))

        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._sel)
        self._tree.bind("<Double-Button-1>", self._dbl)

    def update(self, items: list) -> None:
        self._items = items
        for row in self._tree.get_children():
            self._tree.delete(row)

        for i, opp in enumerate(items):
            ql_col = _QL_COLORS.get(opp.quality_label, TEXT_SECONDARY)
            icon   = _SETUP_ICONS.get(opp.setup_type, "•")
            setup_txt = f"{icon} {opp.setup_type[:10]}"
            bg = TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN
            tag = f"opp_{i}"
            self._tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                opp.symbol,
                setup_txt,
                f"{opp.opp_score:.1f}",
                f"{opp.rr_ratio:.1f}x",
                f"%{opp.confidence:.0f}",
                f"{opp.sector_name[:10]}({opp.sector_strength:.0f})",
                opp.quality_label,
                opp.reason[:45],
            ))
            self._tree.tag_configure(tag, foreground=ql_col, background=bg)

        n = len(items)
        self._cnt.config(
            text=f"{n} fırsat" if n else "Yüksek kaliteli fırsat yok",
            fg=COLOR_POSITIVE if n > 0 else TEXT_DIM
        )

    def _sel(self, event):
        sel = self._tree.selection()
        if sel and self._on_select:
            idx = int(sel[0])
            if idx < len(self._items):
                self._on_select(self._items[idx].symbol)

    def _dbl(self, event):
        sel = self._tree.selection()
        if sel and self._on_buy:
            idx = int(sel[0])
            if idx < len(self._items):
                self._on_buy(self._items[idx])
