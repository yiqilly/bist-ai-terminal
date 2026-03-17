# ============================================================
# ui/panels/news_detail_panel.py — Seçili Hisse Haber Detayı
# ============================================================
import tkinter as tk
from ui.theme import *
from data.models import NewsItem


class NewsDetailPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        self._title = tk.Label(h, text="◈  SON HABERLER",
                                font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG)
        self._title.pack(side="left", padx=10)

        self._news_frame = tk.Frame(self, bg=BG_PANEL)
        self._news_frame.pack(fill="both", expand=True, padx=4, pady=4)

    def update(self, symbol: str | None, news_items: list[NewsItem]):
        self._title.config(text=f"◈  HABERLER{' — ' + symbol if symbol else ''}")
        for w in self._news_frame.winfo_children():
            w.destroy()

        if not news_items:
            tk.Label(self._news_frame, text="Bu hisse için haber bulunamadı",
                     font=FONT_SMALL, bg=BG_PANEL, fg=TEXT_DIM).pack(pady=8)
            return

        for item in news_items[:5]:
            self._build_card(item)

    def _build_card(self, item: NewsItem):
        sent = item.sentiment
        if sent > 0.3:
            border = COLOR_POSITIVE
            sent_txt, sent_fg = "▲ POZİTİF", COLOR_POSITIVE
        elif sent < -0.3:
            border = COLOR_NEGATIVE
            sent_txt, sent_fg = "▼ NEGATİF", COLOR_NEGATIVE
        else:
            border = BORDER
            sent_txt, sent_fg = "→ NÖTR", TEXT_SECONDARY

        card = tk.Frame(self._news_frame, bg=BG_CARD,
                         highlightbackground=border, highlightthickness=1)
        card.pack(fill="x", pady=2)

        top = tk.Frame(card, bg=BG_CARD)
        top.pack(fill="x", padx=6, pady=(4, 0))
        tk.Label(top, text=item.source, font=FONT_SMALL, bg=BG_CARD, fg=TEXT_DIM).pack(side="left")
        tk.Label(top, text=sent_txt, font=FONT_SMALL, bg=BG_CARD, fg=sent_fg).pack(side="right")

        tk.Label(card, text=item.headline, font=FONT_SMALL,
                 bg=BG_CARD, fg=TEXT_PRIMARY,
                 wraplength=290, anchor="w", justify="left").pack(
            fill="x", padx=6, pady=(2, 0))

        age = item.age_minutes
        age_str = f"{int(age)} dk önce" if age < 60 else f"{age/60:.1f} sa önce"
        tk.Label(card, text=age_str, font=FONT_SMALL,
                 bg=BG_CARD, fg=TEXT_DIM).pack(anchor="e", padx=6, pady=(0, 4))
