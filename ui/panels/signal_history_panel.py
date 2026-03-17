# ============================================================
# ui/panels/signal_history_panel.py — Sinyal Geçmişi
# ============================================================
import tkinter as tk
from tkinter import ttk
from ui.theme import *


class SignalHistoryPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        tk.Label(h, text="◈  SİNYAL GEÇMİŞİ",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)

        cols = ["Zaman", "Hisse", "Score", "RSI", "Giriş", "Hedef", "R/R"]
        widths = [65, 60, 50, 50, 70, 70, 50]

        style = ttk.Style()
        style.configure("Hist.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=20,
            font=FONT_SMALL, borderwidth=0)
        style.configure("Hist.Treeview.Heading",
            background=BG_HEADER, foreground=COLOR_ACCENT,
            font=FONT_HEADER, relief="flat")

        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   style="Hist.Treeview", height=8)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center", stretch=False)

        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def update(self, history: list[dict]):
        for row in self._tree.get_children():
            self._tree.delete(row)
        for i, h in enumerate(history[:50]):
            self._tree.insert("", "end", iid=str(i), values=(
                h["time"], h["symbol"], h["score"],
                h["rsi"], f"{h['entry']:.2f}",
                f"{h['target']:.2f}", f"{h['rr']:.2f}",
            ))
            self._tree.tag_configure(str(i),
                background=TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN)
