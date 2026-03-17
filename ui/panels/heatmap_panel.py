# ============================================================
# ui/panels/heatmap_panel.py — Heatmap v3 (gelişmiş renkler)
# ============================================================
import tkinter as tk
from typing import Callable
from ui.theme import *
from data.models import MarketSnapshot, SignalCandidate

# Skor → renk (daha belirgin skalası)
_SCORE_BG = {
    0: "#0a1020", 1: "#0d1a30", 2: "#0f2444",
    3: "#0e3a5a", 4: "#0e5068", 5: "#008575", 6: "#00aa88",
}
_SCORE_BORDER = {
    0: "#1a2540", 1: "#1e3060", 2: "#1e4070",
    3: "#1e6080", 4: "#1e8090", 5: "#00c4a0", 6: "#ffffff",
}


class HeatmapPanel(tk.Frame):
    COLS = 10  # BIST100 için kolon sayısını artırdık

    def __init__(self, parent, on_symbol_click: Callable[[str], None] | None = None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._on_click = on_symbol_click
        self._selected: str | None = None
        self._cells: dict[str, dict] = {} # Recycle cache
        self._last_update = 0.0
        self._cache = {} # symbol -> {price, score, change}
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=2)
        h.pack(fill="x")
        from config import UNIVERSE
        tk.Label(h, text=f"◈  {UNIVERSE} HEATMAP",
                 font=FONT_HEADER, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)
        tk.Label(h, text="↓ tıkla", font=("Consolas", 7),
                 bg=PANEL_TITLE_BG, fg=TEXT_DIM).pack(side="right", padx=10)
        self._grid = tk.Frame(self, bg=BG_PANEL)
        self._grid.pack(fill="both", expand=True, padx=2, pady=2)

        for c in range(self.COLS):
            self._grid.columnconfigure(c, weight=1)

    def set_selected(self, symbol: str | None):
        self._selected = symbol

    def update(self, snapshot: MarketSnapshot, candidates: list[SignalCandidate]):
        import time
        now = time.time()
        if now - self._last_update < 1.0: # Throttle 1s
            return
        self._last_update = now

        score_map = {c.symbol: c for c in candidates}
        active_symbols = list(snapshot.ticks.keys())

        # 1. Artık olmayan sembolleri temizle
        to_remove = [s for s in self._cells if s not in active_symbols]
        for s in to_remove:
            self._cells[s]["frame"].destroy()
            del self._cells[s]
            if s in self._cache: del self._cache[s]

        # 2. Güncelle veya Oluştur
        for i, symbol in enumerate(active_symbols):
            row, col = divmod(i, self.COLS)
            tick  = snapshot.ticks.get(symbol)
            cand  = score_map.get(symbol)
            score = min(cand.score if cand else 0, 6)

            price = tick.price if tick else 0.0
            change = round((cand.price - cand.prev_price) / cand.prev_price * 100, 1) if (cand and cand.prev_price > 0) else 0.0
            rsi = cand.rsi if cand else 0.0
            
            # Performans: Değişim yoksa güncelleme
            cache_key = (price, score, change, symbol == self._selected)
            if self._cache.get(symbol) == cache_key:
                continue
            self._cache[symbol] = cache_key

            bg     = _SCORE_BG.get(score, "#0a1020")
            border = "#ffffff" if symbol == self._selected else _SCORE_BORDER.get(score, BORDER)
            chg_col = COLOR_POSITIVE if change >= 0 else COLOR_NEGATIVE

            if symbol not in self._cells:
                # Yeni hücre oluştur (ayni...)
                frm = tk.Frame(self._grid, bg=bg, highlightthickness=1, cursor="hand2")
                frm.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
                
                l_sym = tk.Label(frm, text=symbol, font=("Consolas", 8, "bold"), bg=bg, fg=TEXT_PRIMARY, cursor="hand2")
                l_sym.pack(pady=(1,0))
                l_prc = tk.Label(frm, text="", font=("Consolas", 7), bg=bg, fg=TEXT_SECONDARY, cursor="hand2")
                l_prc.pack()
                l_chg = tk.Label(frm, text="", font=("Consolas", 7), bg=bg, fg=chg_col, cursor="hand2")
                l_chg.pack()
                l_inf = tk.Label(frm, text="", font=("Consolas", 6), bg=bg, fg=TEXT_DIM, cursor="hand2")
                l_inf.pack(pady=(0,1))

                for w in [frm, l_sym, l_prc, l_chg, l_inf]:
                    w.bind("<Button-1>", lambda e, s=symbol: self._click(s))

                self._cells[symbol] = {
                    "frame": frm, "l_sym": l_sym, "l_prc": l_prc, 
                    "l_chg": l_chg, "l_inf": l_inf
                }
            
            cell = self._cells[symbol]
            cell["frame"].config(bg=bg, highlightbackground=border)
            cell["l_sym"].config(bg=bg)
            cell["l_prc"].config(text=f"{price:.1f}", bg=bg)
            cell["l_chg"].config(text=f"{change:+.1f}%", bg=bg, fg=chg_col)
            cell["l_inf"].config(text=f"R{rsi:.0f} S{score}", bg=bg)

    def _click(self, symbol: str):
        self._selected = symbol
        if self._on_click: self._on_click(symbol)
