# ============================================================
# ui/panels/portfolio_panel.py — Portföy Takip Paneli
# ============================================================
import tkinter as tk
from tkinter import ttk
from ui.theme import *
from portfolio.portfolio_engine import PortfolioEngine


class PortfolioPanel(tk.Frame):
    def __init__(self, parent, engine: PortfolioEngine, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._engine = engine
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        tk.Label(h, text="◈  PORTFÖY",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)

        # Özet
        summary = tk.Frame(self, bg=BG_CARD,
                            highlightbackground=BORDER, highlightthickness=1)
        summary.pack(fill="x", padx=6, pady=6)

        metrics = tk.Frame(summary, bg=BG_CARD)
        metrics.pack(fill="x", padx=8, pady=6)

        self._cash_lbl  = self._metric(metrics, "Nakit", "₺0", 0)
        self._value_lbl = self._metric(metrics, "Toplam", "₺0", 1)
        self._pnl_lbl   = self._metric(metrics, "PnL", "₺0", 2)
        self._pos_lbl   = self._metric(metrics, "Pozisyon", "0", 3)

        # Pozisyon tablosu
        cols = ["Hisse", "Adet", "Maliyet", "Güncel", "PnL", "PnL%"]
        widths = [60, 50, 75, 75, 75, 60]

        style = ttk.Style()
        style.configure("Port.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=20,
            font=FONT_SMALL, borderwidth=0)
        style.configure("Port.Treeview.Heading",
            background=BG_HEADER, foreground=COLOR_ACCENT,
            font=FONT_HEADER, relief="flat")

        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   style="Port.Treeview", height=6)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center", stretch=False)
        self._tree.pack(fill="both", expand=True, padx=2)

    def _metric(self, parent, label: str, value: str, col: int) -> tk.Label:
        f = tk.Frame(parent, bg=BG_CARD)
        f.grid(row=0, column=col, padx=12, pady=2)
        tk.Label(f, text=label, font=FONT_SMALL, bg=BG_CARD, fg=TEXT_DIM).pack()
        lbl = tk.Label(f, text=value, font=FONT_MEDIUM, bg=BG_CARD, fg=TEXT_PRIMARY)
        lbl.pack()
        return lbl

    def update(self):
        e = self._engine
        pnl_color = COLOR_POSITIVE if e.total_pnl >= 0 else COLOR_NEGATIVE
        self._cash_lbl.config(text=f"₺{e.cash:,.0f}")
        self._value_lbl.config(text=f"₺{e.total_value:,.0f}")
        self._pnl_lbl.config(text=f"₺{e.total_pnl:+,.0f}", fg=pnl_color)
        self._pos_lbl.config(text=str(len(e.positions)))

        for row in self._tree.get_children():
            self._tree.delete(row)
        for i, pos in enumerate(e.positions):
            pnl_col = COLOR_POSITIVE if pos.pnl >= 0 else COLOR_NEGATIVE
            tag = f"p{i}"
            self._tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                pos.symbol,
                f"{pos.quantity:.0f}",
                f"₺{pos.avg_cost:.2f}",
                f"₺{pos.current_price:.2f}",
                f"₺{pos.pnl:+.0f}",
                f"{pos.pnl_pct:+.1f}%",
            ))
            self._tree.tag_configure(tag,
                foreground=pnl_col,
                background=TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN)
