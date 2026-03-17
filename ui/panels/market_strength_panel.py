# ============================================================
# ui/panels/market_strength_panel.py — Piyasa Gücü + Rejim
# ============================================================
import tkinter as tk
from ui.theme import *
from data.models import RegimeResult


class MarketStrengthPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        tk.Label(h, text="◈  PİYASA GÜCÜ",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)

        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)

        # Progress bar
        self._canvas = tk.Canvas(body, height=20, bg=BG_PANEL, highlightthickness=0)
        self._canvas.pack(fill="x", pady=(0, 4))

        row = tk.Frame(body, bg=BG_PANEL)
        row.pack(fill="x")
        self._val_label = tk.Label(row, text="0", font=FONT_LARGE,
                                    bg=BG_PANEL, fg=COLOR_POSITIVE)
        self._val_label.pack(side="left")
        tk.Label(row, text=" / 100", font=FONT_MEDIUM,
                 bg=BG_PANEL, fg=TEXT_SECONDARY).pack(side="left")
        self._status_label = tk.Label(row, text="",
                                       font=FONT_SMALL, bg=BG_PANEL, fg=TEXT_DIM)
        self._status_label.pack(side="right")

        stats = tk.Frame(body, bg=BG_PANEL)
        stats.pack(fill="x", pady=(2, 0))
        self._adv_label = tk.Label(stats, text="↑ 0", font=FONT_SMALL,
                                    bg=BG_PANEL, fg=COLOR_POSITIVE)
        self._adv_label.pack(side="left", padx=(0, 8))
        self._dec_label = tk.Label(stats, text="↓ 0", font=FONT_SMALL,
                                    bg=BG_PANEL, fg=COLOR_NEGATIVE)
        self._dec_label.pack(side="left", padx=(0, 8))
        self._unc_label = tk.Label(stats, text="→ 0", font=FONT_SMALL,
                                    bg=BG_PANEL, fg=COLOR_NEUTRAL)
        self._unc_label.pack(side="left")

        # Rejim göstergesi
        self._regime_lbl = tk.Label(body, text="", font=FONT_HEADER,
                                     bg=BG_PANEL, fg=COLOR_WARNING, pady=2)
        self._regime_lbl.pack(fill="x", pady=(4, 0))

        self._regime_desc = tk.Label(body, text="", font=FONT_SMALL,
                                      bg=BG_PANEL, fg=TEXT_DIM,
                                      wraplength=260, justify="left")
        self._regime_desc.pack(fill="x")

    def update(
        self,
        strength: float,
        advancing: int,
        declining: int,
        unchanged: int,
        regime: RegimeResult | None = None,
    ):
        color = COLOR_POSITIVE if strength >= 60 else (
            COLOR_NEGATIVE if strength <= 40 else COLOR_WARNING)

        self._val_label.config(text=f"{strength:.0f}", fg=color)
        if strength >= 70:   status = "GÜÇLÜ BOĞA"
        elif strength >= 55: status = "YÜKSELİŞ"
        elif strength >= 45: status = "NÖTR"
        elif strength >= 30: status = "DÜŞÜŞ"
        else:                status = "GÜÇLÜ AYI"
        self._status_label.config(text=status, fg=color)
        self._adv_label.config(text=f"↑ {advancing}")
        self._dec_label.config(text=f"↓ {declining}")
        self._unc_label.config(text=f"→ {unchanged}")

        # Bar çiz
        self._canvas.delete("all")
        w = self._canvas.winfo_width() or 260
        bar_w = int((strength / 100) * w)
        self._canvas.create_rectangle(0, 0, w, 20, fill=BG_CARD, outline="")
        self._canvas.create_rectangle(0, 0, bar_w, 20, fill=color, outline="")

        # Rejim
        if regime:
            regime_color = {
                "TREND": COLOR_POSITIVE, "RANGE": COLOR_WARNING,
                "RISK_OFF": COLOR_NEGATIVE, "VOLATILE": "#ff8c00",
            }.get(regime.regime, TEXT_SECONDARY)
            self._regime_lbl.config(text=regime.label, fg=regime_color)
            self._regime_desc.config(text=regime.description)
