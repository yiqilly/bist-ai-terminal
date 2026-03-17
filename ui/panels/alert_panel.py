# ============================================================
# ui/panels/alert_panel.py — Alert / Bildirim Paneli
# ============================================================
import tkinter as tk
from ui.theme import *
from data.models import AlertEvent

_SEV_COLORS = {
    "critical": COLOR_POSITIVE,
    "warning":  COLOR_WARNING,
    "info":     COLOR_ACCENT,
}


class AlertPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        tk.Label(h, text="◈  UYARILAR & ALERTLER",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)

        self._frame = tk.Frame(self, bg=BG_PANEL)
        self._frame.pack(fill="both", expand=True, padx=4, pady=4)

    def update(self, alerts: list[AlertEvent]):
        for w in self._frame.winfo_children():
            w.destroy()

        if not alerts:
            tk.Label(self._frame, text="Henüz uyarı yok",
                     font=FONT_SMALL, bg=BG_PANEL, fg=TEXT_DIM).pack(pady=8)
            return

        for evt in alerts[:12]:
            col = _SEV_COLORS.get(evt.severity, TEXT_SECONDARY)
            card = tk.Frame(self._frame, bg=BG_CARD,
                             highlightbackground=col, highlightthickness=1)
            card.pack(fill="x", pady=1)
            row = tk.Frame(card, bg=BG_CARD)
            row.pack(fill="x", padx=6, pady=3)
            tk.Label(row, text=evt.message, font=FONT_SMALL,
                     bg=BG_CARD, fg=col, anchor="w", justify="left",
                     wraplength=280).pack(side="left", fill="x", expand=True)
            tk.Label(row, text=evt.timestamp.strftime("%H:%M"),
                     font=FONT_SMALL, bg=BG_CARD, fg=TEXT_DIM).pack(side="right")
