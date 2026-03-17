# ============================================================
# ui/panels/news_panel.py — KAP Haber Paneli v2
# Gerçek KAP RSS veya mock fallback
# ============================================================
import tkinter as tk
from tkinter import ttk
from ui.theme import *
from data.models import NewsItem


_SENT_COLORS = {
    "POZİTİF": COLOR_POSITIVE,
    "NEGATİF": COLOR_NEGATIVE,
    "NÖTR":    TEXT_DIM,
}


class NewsPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._build()

    def _build(self):
        # Başlık
        hdr = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        hdr.pack(fill="x")
        tk.Label(hdr, text="◈  KAP HABERLER",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)
        self._src_lbl = tk.Label(hdr, text="",
                                  font=("Consolas", 7, "bold"),
                                  bg=PANEL_TITLE_BG, fg=COLOR_WARNING)
        self._src_lbl.pack(side="right", padx=10)
        self._cnt_lbl = tk.Label(hdr, text="",
                                  font=FONT_SMALL, bg=PANEL_TITLE_BG, fg=TEXT_DIM)
        self._cnt_lbl.pack(side="right", padx=6)

        # Scrollable alan
        container = tk.Frame(self, bg=BG_PANEL)
        container.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(container, bg=BG_PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(container, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(self._canvas, bg=BG_PANEL)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(self._win_id, width=e.width))
        # Mouse wheel
        self._canvas.bind("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

    def update(self, news_items: list[NewsItem], signal_symbols: set[str],
               source_label: str = "") -> None:
        for w in self._inner.winfo_children():
            w.destroy()

        # Kaynak etiketi
        is_real = source_label and source_label.upper() != "MOCK"
        self._src_lbl.config(
            text="● KAP RSS" if is_real else "MOCK",
            fg=COLOR_POSITIVE if is_real else COLOR_WARNING
        )
        self._cnt_lbl.config(text=f"{len(news_items)} haber")

        if not news_items:
            tk.Label(self._inner, text="Haber bekleniyor...",
                     font=FONT_SMALL, bg=BG_PANEL, fg=TEXT_DIM).pack(pady=20)
            return

        for i, item in enumerate(news_items[:40]):
            is_signal = item.symbol in signal_symbols
            is_pos    = item.sentiment > 0.4
            is_neg    = item.sentiment < -0.3

            bg = "#0a1f14" if (is_signal and is_pos) else BG_PANEL if i % 2 else BG_DARK

            card = tk.Frame(self._inner, bg=bg,
                            highlightbackground=BORDER, highlightthickness=1)
            card.pack(fill="x", padx=4, pady=1)

            top = tk.Frame(card, bg=bg)
            top.pack(fill="x", padx=6, pady=(3, 0))

            # Sembol
            sym_col = (COLOR_POSITIVE if is_pos else
                       COLOR_NEGATIVE if is_neg else TEXT_SECONDARY)
            sym_txt = item.symbol if item.symbol else "GENEL"
            tk.Label(top, text=sym_txt, font=("Consolas", 9, "bold"),
                     bg=bg, fg=sym_col, width=6, anchor="w").pack(side="left")

            # Kaynak + zaman
            age = f"{item.age_minutes:.0f}dk" if item.age_minutes < 60 else f"{item.age_minutes/60:.1f}sa"
            tk.Label(top, text=f"{item.source}  {age}",
                     font=("Consolas", 7), bg=bg, fg=TEXT_DIM).pack(side="right")

            # Sentiment ok
            sent_icon = "▲" if is_pos else ("▼" if is_neg else "—")
            tk.Label(top, text=sent_icon, font=FONT_SMALL,
                     bg=bg, fg=sym_col).pack(side="right", padx=4)

            # Başlık
            tk.Label(card, text=item.headline[:80],
                     font=FONT_SMALL, bg=bg, fg=TEXT_SECONDARY,
                     wraplength=300, anchor="w", justify="left"
                     ).pack(padx=6, pady=(1, 4), anchor="w")

            # Sinyal çakışması
            if is_signal and is_pos:
                tk.Label(card, text="★ Teknik + Haber çakışması",
                         font=("Consolas", 7), bg=bg, fg=COLOR_POSITIVE
                         ).pack(padx=6, pady=(0, 3))
