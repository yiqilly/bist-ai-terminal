# ============================================================
# ui/panels/notification_center.py
# Notification Center UI Panel
# Veri: signals/notification_store.py
# ============================================================
import tkinter as tk
from tkinter import ttk
from signals.notification_store import NotificationCenter, Notification
from ui.theme import *

_TYPE_COLOR = {
    "BUY":   "#4ade80", "SELL":  "#f87171",
    "ALERT": "#fbbf24", "NEWS":  "#60a5fa", "INFO": "#94a3b8",
}
_TYPE_ICON = {
    "BUY": "🚀", "SELL": "⚠", "ALERT": "⚡", "NEWS": "📰", "INFO": "ℹ",
}


class NotificationPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._nc     = NotificationCenter.get()
        self._filter = tk.StringVar(value="TÜMÜ")
        self._build()
        self._nc.on_new(lambda n: self.after(0, self.refresh))

    def _build(self):
        hdr = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4); hdr.pack(fill="x")
        tk.Label(hdr, text="◈  BİLDİRİM MERKEZİ",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)
        filt_f = tk.Frame(hdr, bg=PANEL_TITLE_BG); filt_f.pack(side="right", padx=8)
        for typ in ["TÜMÜ", "BUY", "SELL", "ALERT", "NEWS"]:
            col = _TYPE_COLOR.get(typ, TEXT_DIM)
            tk.Radiobutton(
                filt_f, text=typ, variable=self._filter, value=typ,
                font=("Consolas", 7), bg=PANEL_TITLE_BG, fg=col,
                selectcolor=BG_DARK, activebackground=PANEL_TITLE_BG,
                cursor="hand2", command=self.refresh,
            ).pack(side="left", padx=3)

        list_f = tk.Frame(self, bg=BG_PANEL); list_f.pack(fill="both", expand=True)
        self._canvas  = tk.Canvas(list_f, bg=BG_PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(list_f, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._rows_f = tk.Frame(self._canvas, bg=BG_PANEL)
        win = self._canvas.create_window((0, 0), window=self._rows_f, anchor="nw")
        self._rows_f.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(win, width=e.width))

    def refresh(self) -> None:
        for w in self._rows_f.winfo_children():
            w.destroy()
        filt  = self._filter.get()
        items = (self._nc.get_all() if filt == "TÜMÜ"
                 else self._nc.get_by_type(filt))
        if not items:
            tk.Label(self._rows_f, text="Bildirim yok",
                     font=FONT_SMALL, bg=BG_PANEL, fg=TEXT_DIM).pack(pady=20)
            return
        for i, n in enumerate(items[:50]):
            bg  = BG_PANEL if i % 2 == 0 else BG_DARK
            row = tk.Frame(self._rows_f, bg=bg, pady=3)
            row.pack(fill="x", padx=4, pady=1)
            col  = _TYPE_COLOR.get(n.type, TEXT_DIM)
            icon = _TYPE_ICON.get(n.type, "•")
            tk.Label(row, text=icon, font=("Consolas", 10),
                     bg=bg, fg=col, width=2).pack(side="left", padx=4)
            tk.Label(row, text=n.symbol or "—",
                     font=("Consolas", 9, "bold"),
                     bg=bg, fg=col, width=7).pack(side="left")
            tk.Label(row, text=n.message[:55], font=FONT_SMALL,
                     bg=bg, fg=TEXT_SECONDARY, anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(row, text=n.age_str, font=("Consolas", 7),
                     bg=bg, fg=TEXT_DIM, width=5).pack(side="right", padx=4)
