# ============================================================
# ui/panels/market_context_panel.py
# Market Context Panel — Piyasa rejimi + breadth + volatilite
# ============================================================
import tkinter as tk
from ui.theme import *


class MarketContextPanel(tk.Frame):
    """
    Market Strength panelinin genişletilmiş versiyonu.
    Regime, Breadth, Momentum, Volatilite, Trade Guide gösterir.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        tk.Label(h, text="◈  PİYASA REJİMİ",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)

        body = tk.Frame(self, bg=BG_PANEL, padx=10, pady=6)
        body.pack(fill="both", expand=True)

        # Rejim etiketi (büyük)
        self._regime_lbl = tk.Label(body, text="— —",
            font=("Consolas", 11, "bold"), bg=BG_PANEL, fg=COLOR_WARNING)
        self._regime_lbl.pack(fill="x")

        # Güç bar
        self._bar_canvas = tk.Canvas(body, height=12, bg=BG_PANEL, highlightthickness=0)
        self._bar_canvas.pack(fill="x", pady=(4, 2))

        # Sayısal değer + etiketi
        row1 = tk.Frame(body, bg=BG_PANEL); row1.pack(fill="x")
        self._str_lbl = tk.Label(row1, text="50", font=FONT_LARGE,
                                  bg=BG_PANEL, fg=COLOR_POSITIVE, width=4, anchor="w")
        self._str_lbl.pack(side="left")
        tk.Label(row1, text="/100", font=FONT_SMALL,
                 bg=BG_PANEL, fg=TEXT_DIM).pack(side="left")
        self._sl_lbl = tk.Label(row1, text="", font=FONT_SMALL,
                                 bg=BG_PANEL, fg=TEXT_SECONDARY)
        self._sl_lbl.pack(side="right")

        # Breadth
        brow = tk.Frame(body, bg=BG_PANEL); brow.pack(fill="x", pady=(4,0))
        self._adv_lbl = tk.Label(brow, text="↑ 0", font=FONT_SMALL, bg=BG_PANEL, fg=COLOR_POSITIVE)
        self._adv_lbl.pack(side="left", padx=(0,6))
        self._dec_lbl = tk.Label(brow, text="↓ 0", font=FONT_SMALL, bg=BG_PANEL, fg=COLOR_NEGATIVE)
        self._dec_lbl.pack(side="left", padx=(0,6))
        self._unc_lbl = tk.Label(brow, text="→ 0", font=FONT_SMALL, bg=BG_PANEL, fg=TEXT_DIM)
        self._unc_lbl.pack(side="left")
        self._breadth_lbl = tk.Label(brow, text="", font=("Consolas", 7),
                                      bg=BG_PANEL, fg=TEXT_DIM)
        self._breadth_lbl.pack(side="right")

        # Metriken satır
        sep = tk.Frame(body, bg=BORDER, height=1); sep.pack(fill="x", pady=4)
        metrics = tk.Frame(body, bg=BG_PANEL); metrics.pack(fill="x")

        def metric_col(parent, label, var_name):
            f = tk.Frame(parent, bg=BG_PANEL); f.pack(side="left", expand=True)
            tk.Label(f, text=label, font=("Consolas", 7),
                     bg=BG_PANEL, fg=TEXT_DIM).pack()
            lbl = tk.Label(f, text="—", font=("Consolas", 9, "bold"),
                           bg=BG_PANEL, fg=TEXT_SECONDARY)
            lbl.pack()
            setattr(self, var_name, lbl)

        metric_col(metrics, "Momentum", "_mom_lbl")
        metric_col(metrics, "Volatilite", "_vol_lbl")
        metric_col(metrics, "Hacim Bias", "_vbias_lbl")
        metric_col(metrics, "AD Oran", "_ad_lbl")

        # Trade rehberi
        sep2 = tk.Frame(body, bg=BORDER, height=1); sep2.pack(fill="x", pady=4)
        self._guide_lbl = tk.Label(body, text="", font=("Consolas", 8),
                                    bg=BG_PANEL, fg=TEXT_DIM, wraplength=200, justify="left")
        self._guide_lbl.pack(fill="x")

    def update(self, ctx) -> None:
        """ctx: MarketContext dataclass"""
        if ctx is None:
            return

        col = ctx.color
        self._regime_lbl.config(text=ctx.label, fg=col)

        # Bar
        self._bar_canvas.update_idletasks()
        w = self._bar_canvas.winfo_width() or 200
        pct = ctx.market_strength / 100
        self._bar_canvas.delete("all")
        self._bar_canvas.create_rectangle(0, 0, w, 12, fill=BG_DARK, outline="")
        self._bar_canvas.create_rectangle(0, 0, int(w * pct), 12, fill=col, outline="")

        self._str_lbl.config(text=f"{ctx.market_strength:.0f}", fg=col)
        self._sl_lbl.config(text=ctx.strength_label, fg=col)
        self._adv_lbl.config(text=f"↑ {ctx.advancing}")
        self._dec_lbl.config(text=f"↓ {ctx.declining}")
        self._unc_lbl.config(text=f"→ {ctx.unchanged}")
        self._breadth_lbl.config(text=ctx.breadth_label)

        mom_col = COLOR_POSITIVE if ctx.avg_momentum > 0 else COLOR_NEGATIVE
        self._mom_lbl.config(text=f"{ctx.avg_momentum:+.1f}", fg=mom_col)

        vol_col = COLOR_WARNING if ctx.volatility > 2.5 else TEXT_SECONDARY
        self._vol_lbl.config(text=f"{ctx.volatility:.1f}%", fg=vol_col)

        vb_col = COLOR_POSITIVE if ctx.vol_bias >= 1 else COLOR_NEGATIVE
        self._vbias_lbl.config(text=f"{ctx.vol_bias:.1f}x", fg=vb_col)
        self._ad_lbl.config(text=f"{ctx.ad_ratio:.1f}x",
                             fg=COLOR_POSITIVE if ctx.ad_ratio >= 1 else COLOR_NEGATIVE)

        guide = ctx.description
        # Router durumunu göster
        regime = ctx.regime
        no_trade_regimes = {'RANGE', 'BEAR', 'WEAK_BEAR', 'RISK_OFF'}
        if regime in no_trade_regimes:
            trade_status = {
                'RANGE':     "⏸ RANGE — İşlem Yok, Bekleniyoruz",
                'BEAR':      "🔴 BEAR — İşlem Yok",
                'WEAK_BEAR': "🟠 WEAK BEAR — İşlem Yok",
                'RISK_OFF':  "⚠ RISK OFF — İşlem Yok",
            }.get(regime, "⏸ İşlem Yok")
            guide = f"{trade_status}\n" + guide
        elif regime == 'BULL':
            guide = "🟢 BULL — 📈 Breakout Stratejisi Aktif\n" + guide
        elif regime == 'WEAK_BULL':
            guide = "🟡 WEAK BULL — 📈 Breakout (Dikkatli)\n" + guide
        elif regime == 'VOLATILE':
            guide = "🟠 VOLATİL — ⚡ Volatility Breakout Aktif\n" + guide
        elif regime == 'EDGE':
            guide = "🟣 EDGE — 🦈 Core & Swing Dinamik Kasa Aktif\n" + guide

        if not ctx.trade_allowed:
            guide = "🚫 YENİ POZİSYON ÖNERİLMEZ\n" + guide
        elif ctx.position_size_adj < 0.7:
            guide = f"⚠ Boyut ×{ctx.position_size_adj:.1f}\n" + guide
        self._guide_lbl.config(text=guide[:150])
