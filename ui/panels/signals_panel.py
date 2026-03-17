# ============================================================
# ui/panels/signals_panel.py — En İyi Sinyaller (genişletilmiş)
# ============================================================
import tkinter as tk
from tkinter import ttk
from typing import Callable
from ui.theme import *
from data.models import RankedSignal

COLUMNS = [
    ("Rk",    30), ("Hisse", 55), ("Fiyat",  65), ("Score",  45),
    ("AI",    45), ("Birleşik", 60), ("RSI",  45), ("Giriş",  65),
    ("Stop",  65), ("Hedef",   65), ("Risk%", 50), ("R/R",    45),
    ("Kalite",65), ("Lot",     45),
]

_QL_COLORS = {
    "Elite": COLOR_POSITIVE, "Strong": "#4ade80",
    "Watchlist": COLOR_WARNING, "Weak": COLOR_NEGATIVE,
}


class SignalsPanel(tk.Frame):
    def __init__(self, parent, on_select: Callable | None = None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._on_select = on_select
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        tk.Label(h, text="◈  EN İYİ SİNYALLER",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)

        style = ttk.Style()
        style.configure("Signal.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=20,
            font=FONT_SMALL, borderwidth=0)
        style.configure("Signal.Treeview.Heading",
            background=BG_HEADER, foreground=COLOR_ACCENT,
            font=FONT_HEADER, relief="flat")
        style.map("Signal.Treeview",
            background=[("selected", TABLE_SELECT)],
            foreground=[("selected", TEXT_PRIMARY)])

        cols = [c[0] for c in COLUMNS]
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   style="Signal.Treeview", height=8)
        for col, width in COLUMNS:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=width, anchor="center", stretch=False)

        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_row_select)
        self._signals: list[RankedSignal] = []

    def update(self, signals: list[RankedSignal]):
        self._signals = signals
        for row in self._tree.get_children():
            self._tree.delete(row)

        for i, s in enumerate(signals):
            c = s.candidate
            r = s.risk
            ps = s.position_size
            ql_color = _QL_COLORS.get(s.quality_label, TEXT_SECONDARY)
            tag = f"ql_{s.quality_label}"
            self._tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                s.rank,
                c.symbol,
                f"{c.price:.2f}",
                c.score,
                f"{s.ai_score:.1f}",
                f"{s.combined_score:.1f}",
                f"{c.rsi:.1f}",
                f"{r.entry:.2f}",
                f"{r.stop:.2f}",
                f"{r.target:.2f}",
                f"{r.risk_pct:.1f}%",
                f"{r.rr_ratio:.2f}",
                s.quality_label,
                ps.suggested_lots if ps else "—",
            ))
            self._tree.tag_configure(tag,
                foreground=ql_color,
                background=TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN)

    def _on_row_select(self, event):
        sel = self._tree.selection()
        if sel and self._on_select:
            idx = int(sel[0])
            if idx < len(self._signals):
                self._on_select(self._signals[idx])
