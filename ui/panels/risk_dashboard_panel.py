# ============================================================
# ui/panels/risk_dashboard_panel.py
# Risk Dashboard Panel — FAZ 9 UI
# ============================================================
import tkinter as tk
from tkinter import ttk
from ui.theme import *


class RiskDashboardPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4); hdr.pack(fill="x")
        tk.Label(hdr, text="◈  RİSK DASHBOARD",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)
        self._alert_lbl = tk.Label(hdr, text="", font=FONT_SMALL,
                                    bg=PANEL_TITLE_BG, fg=COLOR_NEGATIVE)
        self._alert_lbl.pack(side="right", padx=10)

        body = tk.Frame(self, bg=BG_PANEL, padx=10, pady=8)
        body.pack(fill="both", expand=True)

        # Üst metrik grid
        grid = tk.Frame(body, bg=BG_PANEL); grid.pack(fill="x", pady=(0, 8))

        def metric(parent, r, c, label, var):
            f = tk.Frame(parent, bg=BG_CARD, padx=8, pady=6)
            f.grid(row=r, column=c, padx=3, pady=3, sticky="ew")
            parent.columnconfigure(c, weight=1)
            tk.Label(f, text=label, font=("Consolas", 7),
                     bg=BG_CARD, fg=TEXT_DIM).pack()
            lbl = tk.Label(f, text="—", font=("Consolas", 11, "bold"),
                           bg=BG_CARD, fg=TEXT_PRIMARY)
            lbl.pack()
            setattr(self, var, lbl)

        metric(grid, 0, 0, "Açık Pozisyon",    "_pos_cnt")
        metric(grid, 0, 1, "Toplam Exposure",  "_exposure")
        metric(grid, 0, 2, "Exposure %",       "_exp_pct")
        metric(grid, 1, 0, "Günlük PnL",       "_daily_pnl")
        metric(grid, 1, 1, "Ort. Risk/Trade",  "_avg_risk")
        metric(grid, 1, 2, "Max DD Tahmini",   "_mdd")

        # Sektör exposure tablosu
        sep = tk.Frame(body, bg=BORDER, height=1); sep.pack(fill="x", pady=4)
        tk.Label(body, text="Sektör Dağılımı",
                 font=FONT_SMALL, bg=BG_PANEL, fg=TEXT_DIM).pack(anchor="w")

        style = ttk.Style()
        style.configure("Risk.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=18,
            font=FONT_SMALL, borderwidth=0)
        style.configure("Risk.Treeview.Heading",
            background=BG_HEADER, foreground=TEXT_DIM,
            font=("Consolas", 7), relief="flat")

        self._sec_tree = ttk.Treeview(
            body, columns=["Sektör", "TL", "%"],
            show="headings", style="Risk.Treeview", height=5
        )
        for col, w in [("Sektör", 120), ("TL", 90), ("%", 60)]:
            self._sec_tree.heading(col, text=col)
            self._sec_tree.column(col, width=w, anchor="center")
        self._sec_tree.pack(fill="x")

        # Uyarı mesajları
        sep2 = tk.Frame(body, bg=BORDER, height=1); sep2.pack(fill="x", pady=4)
        self._msg_lbl = tk.Label(body, text="",
                                  font=("Consolas", 8), bg=BG_PANEL, fg=TEXT_DIM,
                                  wraplength=280, justify="left")
        self._msg_lbl.pack(fill="x")

    def update(self, metrics) -> None:
        if metrics is None:
            return

        # Renk fonksiyonları
        def pnl_col(v): return COLOR_POSITIVE if v >= 0 else COLOR_NEGATIVE
        def exp_col(v):
            if v >= 70: return COLOR_NEGATIVE
            if v >= 50: return COLOR_WARNING
            return COLOR_POSITIVE

        self._pos_cnt.config(
            text=f"{metrics.open_count}/{metrics.max_open}",
            fg=COLOR_NEGATIVE if metrics.is_max_positions else TEXT_PRIMARY
        )
        self._exposure.config(text=f"₺{metrics.total_exposure:,.0f}")
        self._exp_pct.config(
            text=f"%{metrics.exposure_pct:.1f}",
            fg=exp_col(metrics.exposure_pct)
        )
        self._daily_pnl.config(
            text=f"₺{metrics.total_pnl_tl:+,.0f}",
            fg=pnl_col(metrics.total_pnl_tl)
        )
        self._avg_risk.config(text=f"%{metrics.avg_risk_per_trade:.2f}")
        self._mdd.config(
            text=f"%{metrics.max_drawdown_est:.2f}",
            fg=COLOR_NEGATIVE if metrics.max_drawdown_est > 5 else TEXT_PRIMARY
        )

        # Sektör tablosu
        for row in self._sec_tree.get_children():
            self._sec_tree.delete(row)
        total_exp = metrics.total_exposure or 1
        for i, (sec, tl) in enumerate(
            sorted(metrics.sector_exposure.items(), key=lambda x: -x[1])
        ):
            pct = tl / total_exp * 100
            tag = f"sec_{i}"
            self._sec_tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                sec[:15], f"₺{tl:,.0f}", f"%{pct:.1f}"
            ))
            bg = TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN
            self._sec_tree.tag_configure(tag, background=bg)

        # Alert
        alert_colors = {"normal": TEXT_DIM, "caution": COLOR_WARNING, "danger": COLOR_NEGATIVE}
        alert_col = alert_colors.get(metrics.alert_level, TEXT_DIM)
        self._alert_lbl.config(
            text="⚠" if metrics.alert_level != "normal" else "",
            fg=alert_col
        )
        self._msg_lbl.config(
            text="\n".join(metrics.messages) if metrics.messages else "Portföy riski normal",
            fg=alert_col
        )
