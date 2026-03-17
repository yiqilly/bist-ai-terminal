# ============================================================
# ui/panels/opportunity_panel.py — Fırsat Tarayıcı v4
# Core uyum kolonu dahil.
# ============================================================
import tkinter as tk
from tkinter import ttk
from typing import Callable
from ui.theme import *
from data.models import OpportunityCandidate

_ACTION_COLORS = {
    "güçlü aday": COLOR_POSITIVE, "izle": COLOR_WARNING,
    "erken": COLOR_ACCENT, "dikkat": COLOR_NEGATIVE,
}


class OpportunityPanel(tk.Frame):
    def __init__(self, parent, on_select: Callable[[str], None] | None = None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._on_select = on_select; self._items: list[OpportunityCandidate] = []
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4); h.pack(fill="x")
        tk.Label(h, text="◈  FIRSAT TARAYICI",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)
        self._count = tk.Label(h, text="", font=FONT_SMALL, bg=PANEL_TITLE_BG, fg=TEXT_DIM)
        self._count.pack(side="right", padx=10)

        cols   = ["Hisse","Skor","Kalite","Aksiyon","Core","Edge","Güven","Sebep"]
        widths = [55, 45, 70, 80, 55, 45, 50, 200]

        style = ttk.Style()
        style.configure("Opp.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=20,
            font=FONT_SMALL, borderwidth=0)
        style.configure("Opp.Treeview.Heading",
            background=BG_HEADER, foreground=COLOR_ACCENT,
            font=FONT_HEADER, relief="flat")
        style.map("Opp.Treeview",
            background=[("selected", TABLE_SELECT)],
            foreground=[("selected", TEXT_PRIMARY)])

        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   style="Opp.Treeview", height=12)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center" if col != "Sebep" else "w",
                               stretch=(col=="Sebep"))
        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._sel)

    def update(self, items: list[OpportunityCandidate]):
        self._items = items
        self._count.config(text=f"{len(items)} aday")
        for row in self._tree.get_children(): self._tree.delete(row)

        for i, opp in enumerate(items):
            ac  = _ACTION_COLORS.get(opp.action, TEXT_SECONDARY)
            tag = f"opp_{i}"
            core_txt = f"✓{opp.core_setup_type[:8]}" if opp.core_compatible else "—"
            edge_txt = f"{opp.core_edge_score:.1f}" if opp.core_edge_score > 0 else "—"
            self._tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                opp.symbol,
                f"{opp.opp_score:.1f}",
                opp.quality_label,
                opp.action,
                core_txt,
                edge_txt,
                f"{opp.confidence:.0f}%" if opp.confidence else "—",
                opp.reason,
            ))
            self._tree.tag_configure(tag, foreground=ac,
                background=TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN)

    def _sel(self, event):
        sel = self._tree.selection()
        if sel and self._on_select:
            idx = int(sel[0])
            if idx < len(self._items):
                self._on_select(self._items[idx].symbol)
