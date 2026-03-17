# ============================================================
# ui/panels/signal_detail_panel.py — Seçili Sinyal Detayı
# ============================================================
import tkinter as tk
from ui.theme import *
from data.models import RankedSignal


class SignalDetailPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._labels: dict[str, tk.Label] = {}
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        tk.Label(h, text="◈  SİNYAL DETAYI",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)

        self._symbol_label = tk.Label(self, text="— Seçim yok —",
                                       font=FONT_LARGE, bg=BG_PANEL, fg=TEXT_SECONDARY)
        self._symbol_label.pack(pady=(6, 2))

        grid = tk.Frame(self, bg=BG_PANEL)
        grid.pack(fill="both", expand=True, padx=10, pady=4)

        fields = [
            ("RSI", "rsi"), ("EMA9", "ema9"), ("EMA21", "ema21"), ("ATR", "atr"),
            ("Giriş", "entry"), ("Stop", "stop"), ("Hedef", "target"),
            ("Risk%", "risk"), ("R/R", "rr"), ("Kalite", "quality"),
        ]

        for i, (label, key) in enumerate(fields):
            row, col = divmod(i, 2)
            tk.Label(grid, text=label + ":", font=FONT_HEADER,
                     bg=BG_PANEL, fg=TEXT_DIM, anchor="e", width=8
                     ).grid(row=row, column=col * 2, sticky="e", padx=(4, 2), pady=2)
            lbl = tk.Label(grid, text="—", font=FONT_SMALL,
                           bg=BG_PANEL, fg=TEXT_PRIMARY, anchor="w", width=10)
            lbl.grid(row=row, column=col * 2 + 1, sticky="w", padx=(0, 8), pady=2)
            self._labels[key] = lbl

    def update(self, signal: RankedSignal | None):
        if signal is None:
            self._symbol_label.config(text="— Seçim yok —", fg=TEXT_SECONDARY)
            for lbl in self._labels.values():
                lbl.config(text="—")
            return

        c = signal.candidate
        r = signal.risk
        self._symbol_label.config(
            text=c.symbol,
            fg=QUALITY_COLORS.get(r.quality, TEXT_PRIMARY)
        )
        data = {
            "rsi": f"{c.rsi:.1f}",
            "ema9": f"{c.ema9:.2f}",
            "ema21": f"{c.ema21:.2f}",
            "atr": f"{c.atr:.2f}",
            "entry": f"{r.entry:.2f}",
            "stop": f"{r.stop:.2f}",
            "target": f"{r.target:.2f}",
            "risk": f"{r.risk_pct:.1f}%",
            "rr": f"{r.rr_ratio:.2f}",
            "quality": r.quality,
        }
        for key, val in data.items():
            color = QUALITY_COLORS.get(r.quality, TEXT_PRIMARY) if key == "quality" else TEXT_PRIMARY
            self._labels[key].config(text=val, fg=color)
