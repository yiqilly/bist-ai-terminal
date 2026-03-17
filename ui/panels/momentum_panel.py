# ============================================================
# ui/panels/momentum_panel.py — Momentum Liderleri
# ============================================================
import tkinter as tk
from tkinter import ttk
from ui.theme import *
from data.models import SignalCandidate


class MomentumPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        tk.Label(h, text="◈  MOMENTUM LİDERLERİ",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)

        cols = ["Hisse", "Fiyat", "Değ%", "Momentum", "Hacim"]
        widths = [60, 70, 60, 75, 75]

        style = ttk.Style()
        style.configure("Mom.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=20,
            font=FONT_SMALL, borderwidth=0)
        style.configure("Mom.Treeview.Heading",
            background=BG_HEADER, foreground=COLOR_ACCENT,
            font=FONT_HEADER, relief="flat")

        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   style="Mom.Treeview", height=10)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center", stretch=False)

        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def update(self, leaders: list[SignalCandidate]):
        for row in self._tree.get_children():
            self._tree.delete(row)
        for i, c in enumerate(leaders):
            chg_color = COLOR_POSITIVE if c.momentum >= 0 else COLOR_NEGATIVE
            tag = f"mom_{i}"
            self._tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                c.symbol,
                f"{c.price:.2f}",
                f"{c.momentum:+.2f}%",
                f"{c.momentum:.3f}",
                f"{c.volume/1e6:.1f}M",
            ))
            self._tree.tag_configure(tag,
                foreground=COLOR_POSITIVE if c.momentum >= 0 else COLOR_NEGATIVE,
                background=TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN)
