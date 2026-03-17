# ============================================================
# ui/panels/chart_panel.py — Mini Grafik Paneli (Canvas)
# ============================================================
import tkinter as tk
from ui.theme import *
from data.models import ChartPoint, RiskProfile


class ChartPanel(tk.Frame):
    PAD_X = 12; PAD_TOP = 8; PAD_BOT = 20
    EMA9_COLOR  = "#f59e0b"
    EMA21_COLOR = "#3b82f6"
    ENTRY_COLOR = "#00d4aa"
    STOP_COLOR  = "#ff4d6d"
    TARGET_COLOR = "#4ade80"
    CLOSE_COLOR = "#94a3b8"

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._points: list[ChartPoint] = []
        self._risk: RiskProfile | None = None
        self._symbol = "—"
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        self._title = tk.Label(h, text="◈  MİNİ GRAFİK",
                                font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG)
        self._title.pack(side="left", padx=10)

        # Legend
        leg = tk.Frame(h, bg=PANEL_TITLE_BG)
        leg.pack(side="right", padx=8)
        for txt, col in [("EMA9", self.EMA9_COLOR), ("EMA21", self.EMA21_COLOR),
                         ("Giriş", self.ENTRY_COLOR), ("Stop", self.STOP_COLOR),
                         ("Hedef", self.TARGET_COLOR)]:
            tk.Label(leg, text=f"━ {txt}", font=("Consolas", 7), bg=PANEL_TITLE_BG, fg=col).pack(side="left", padx=3)

        self._canvas = tk.Canvas(self, bg="#080c14", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=2, pady=2)
        self._canvas.bind("<Configure>", lambda e: self._redraw())

    def update(self, symbol: str, points: list[ChartPoint], risk: RiskProfile | None = None):
        self._symbol = symbol
        self._points = points
        self._risk   = risk
        self._title.config(text=f"◈  {symbol} — MİNİ GRAFİK")
        self._redraw()

    def _redraw(self):
        c = self._canvas
        c.delete("all")
        pts = self._points
        if not pts:
            c.create_text(c.winfo_width()//2, c.winfo_height()//2,
                          text="Grafik verisi bekleniyor...",
                          fill=TEXT_DIM, font=FONT_SMALL)
            return

        W = c.winfo_width()  or 400
        H = c.winfo_height() or 180
        px = self.PAD_X; pt = self.PAD_TOP; pb = self.PAD_BOT

        closes = [p.close for p in pts]
        ema9s  = [p.ema9  for p in pts]
        ema21s = [p.ema21 for p in pts]

        all_vals = closes + ema9s + ema21s
        if self._risk:
            all_vals += [self._risk.entry, self._risk.stop, self._risk.target]

        lo, hi = min(all_vals), max(all_vals)
        span = hi - lo or 1.0

        def sx(i):   return px + (i / max(len(pts)-1, 1)) * (W - 2*px)
        def sy(v):   return pt + (1 - (v - lo) / span) * (H - pt - pb)

        # Grid lignes légères
        for lvl in [0.25, 0.5, 0.75]:
            y = pt + (1-lvl) * (H - pt - pb)
            c.create_line(px, y, W-px, y, fill="#1a2540", width=1)

        # Close line
        for i in range(1, len(pts)):
            c.create_line(sx(i-1), sy(pts[i-1].close),
                          sx(i),   sy(pts[i].close),
                          fill=self.CLOSE_COLOR, width=1)

        # EMA9
        for i in range(1, len(pts)):
            c.create_line(sx(i-1), sy(pts[i-1].ema9),
                          sx(i),   sy(pts[i].ema9),
                          fill=self.EMA9_COLOR, width=1, dash=(4,2))

        # EMA21
        for i in range(1, len(pts)):
            c.create_line(sx(i-1), sy(pts[i-1].ema21),
                          sx(i),   sy(pts[i].ema21),
                          fill=self.EMA21_COLOR, width=1, dash=(4,2))

        # Entry / Stop / Target lines
        if self._risk:
            r = self._risk
            for price, col, lbl in [
                (r.entry,  self.ENTRY_COLOR,  f"G {r.entry:.2f}"),
                (r.stop,   self.STOP_COLOR,   f"S {r.stop:.2f}"),
                (r.target, self.TARGET_COLOR, f"H {r.target:.2f}"),
            ]:
                if lo <= price <= hi:
                    y = sy(price)
                    c.create_line(px, y, W-px, y, fill=col, width=1, dash=(6,3))
                    c.create_text(W-px+2, y, text=lbl, fill=col,
                                  font=("Consolas", 7), anchor="w")

        # Son kapanış fiyatı
        last = pts[-1].close
        c.create_text(px, pt-2, text=f"₺{last:.2f}", fill=TEXT_PRIMARY,
                      font=("Consolas", 8, "bold"), anchor="w")

        # X ekseni zaman
        step = max(1, len(pts)//5)
        for i in range(0, len(pts), step):
            ts = pts[i].timestamp.strftime("%H:%M")
            c.create_text(sx(i), H-4, text=ts, fill=TEXT_DIM, font=("Consolas", 7))
