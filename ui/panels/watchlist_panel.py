# ============================================================
# ui/panels/watchlist_panel.py — Watchlist Paneli
# ============================================================
import tkinter as tk
from tkinter import ttk
from typing import Callable
from ui.theme import *
from data.models import WatchlistItem


class WatchlistPanel(tk.Frame):
    def __init__(self, parent, on_select: Callable[[str], None] | None = None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._on_select = on_select
        self._items: list[WatchlistItem] = []
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        tk.Label(h, text="◈  TAKİP LİSTESİ",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)
        self._count_lbl = tk.Label(h, text="0 hisse", font=FONT_SMALL,
                                    bg=PANEL_TITLE_BG, fg=TEXT_DIM)
        self._count_lbl.pack(side="right", padx=10)

        cols = ["Hisse", "Eklenme", "Not"]
        widths = [60, 70, 150]

        style = ttk.Style()
        style.configure("WL.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=20,
            font=FONT_SMALL, borderwidth=0)
        style.configure("WL.Treeview.Heading",
            background=BG_HEADER, foreground=COLOR_ACCENT,
            font=FONT_HEADER, relief="flat")

        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   style="WL.Treeview", height=8)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center" if col != "Not" else "w")

        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._sel)

        # Kaldır butonu
        btn = tk.Button(self, text="— Listeden Çıkar",
                        font=FONT_SMALL, bg=BG_CARD, fg=COLOR_NEGATIVE,
                        relief="flat", cursor="hand2",
                        command=self._remove_selected)
        btn.pack(pady=4)

    def update(self, items: list[WatchlistItem]):
        self._items = items
        self._count_lbl.config(text=f"{len(items)} hisse")
        for row in self._tree.get_children():
            self._tree.delete(row)
        for i, item in enumerate(items):
            self._tree.insert("", "end", iid=str(i), values=(
                item.symbol,
                item.added_at.strftime("%d.%m %H:%M"),
                item.note or "—",
            ))
            self._tree.tag_configure(str(i),
                background=TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN)

    def _sel(self, event):
        sel = self._tree.selection()
        if sel and self._on_select:
            idx = int(sel[0])
            if idx < len(self._items):
                self._on_select(self._items[idx].symbol)

    def _remove_selected(self):
        pass  # app.py'de override edilecek; watchlist_engine.remove() çağrılacak
