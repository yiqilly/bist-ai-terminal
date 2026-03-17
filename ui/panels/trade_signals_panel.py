# ============================================================
# ui/panels/trade_signals_panel.py — v2
# 5 ayrı panel tek dosyada:
#   BuySignalsPanel   → sadece BUY_SIGNAL (gerçek işlem tablosu)
#   SetupPanel        → SETUP + CONFIRMING (yaklaşan)
#   WatchlistSignalPanel → WATCHLIST (takip listesi)
#   PositionsTabPanel → açık pozisyonlar (tab içi)
#   NotifTabPanel     → bildirim özeti (tab içi)
# ============================================================
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from ui.theme import *


# ══════════════════════════════════════════════════════════════
# 1. BUY SIGNALS PANEL — sadece gerçek işlem açılabilir sinyaller
# ══════════════════════════════════════════════════════════════

_QL_COLORS = {
    "A+": "#4ade80", "A": "#86efac", "B": "#fbbf24", "Watchlist": TEXT_SECONDARY,
}
_QL_BG = {
    "A+": "#0a2010", "A": "#0a1f14", "B": "#1a1400", "Watchlist": TABLE_ROW_EVEN,
}

BUY_COLS = [
    ("Hisse",   58), ("Rejim",  72), ("Strateji", 115), ("Setup",  90),
    ("Entry",   72), ("Stop",   72), ("Hedef",    72),  ("R/R",   48),
    ("Güven",   55), ("Sektör", 95), ("Sebep",   200),  ("Lot",   45),
    ("Kalite",  48),
]


class BuySignalsPanel(tk.Frame):
    """
    Ana karar tablosu.
    Sadece BUY_SIGNAL durumundaki sinyaller gösterilir.
    Scanner değil — gerçek işlem kararı için.
    """

    def __init__(self, parent,
                 on_buy: Optional[Callable] = None,
                 on_select: Optional[Callable] = None,
                 **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._on_buy    = on_buy
        self._on_select = on_select
        self._signals   = []
        self._sort_col  = "Kalite"
        self._sort_rev  = True
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._apply_filter())
        self._build()

    def _build(self):
        # ── Başlık ────────────────────────────────────────────
        hdr = tk.Frame(self, bg=PANEL_TITLE_BG, pady=5)
        hdr.pack(fill="x")

        left_hdr = tk.Frame(hdr, bg=PANEL_TITLE_BG)
        left_hdr.pack(side="left", padx=10)
        tk.Label(left_hdr, text="🚀  AL SİNYALLERİ",
                 font=("Consolas", 11, "bold"),
                 bg=PANEL_TITLE_BG, fg="#4ade80").pack(side="left")
        self._count_lbl = tk.Label(left_hdr, text="",
                                    font=("Consolas", 9),
                                    bg=PANEL_TITLE_BG, fg=TEXT_DIM)
        self._count_lbl.pack(side="left", padx=8)

        # ── Arama Kutusu ──────────────────────────────────────
        search_f = tk.Frame(hdr, bg=PANEL_TITLE_BG)
        search_f.pack(side="left", padx=20)
        tk.Label(search_f, text="🔍", font=("Consolas", 9),
                 bg=PANEL_TITLE_BG, fg=COLOR_ACCENT).pack(side="left")
        e = tk.Entry(search_f, textvariable=self._search_var, width=12,
                     font=("Consolas", 9), bg=BG_DARK, fg=TEXT_PRIMARY,
                     insertbackground=TEXT_PRIMARY, relief="flat")
        e.pack(side="left", padx=5)

        # Filtre butonları
        self._filter_var = tk.StringVar(value="TÜMÜ")
        filt_f = tk.Frame(hdr, bg=PANEL_TITLE_BG)
        filt_f.pack(side="right", padx=10)
        tk.Label(filt_f, text="Filtre:", font=FONT_SMALL,
                 bg=PANEL_TITLE_BG, fg=TEXT_DIM).pack(side="left")
        for ql in ["TÜMÜ", "A+", "A", "B"]:
            col = _QL_COLORS.get(ql, TEXT_DIM)
            b = tk.Radiobutton(
                filt_f, text=ql, variable=self._filter_var, value=ql,
                font=("Consolas", 8), bg=PANEL_TITLE_BG, fg=col,
                selectcolor=BG_DARK, activebackground=PANEL_TITLE_BG,
                cursor="hand2", command=self._apply_filter,
            )
            b.pack(side="left", padx=4)

        # ── Hint bar ──────────────────────────────────────────
        self._hint = tk.Label(self,
            text="⏳  Kriterler sağlandı — 15s teyit bekleniyor...",
            font=("Consolas", 8), bg=BG_DARK, fg=TEXT_DIM, pady=3)
        self._hint.pack(fill="x")

        # ── Treeview ──────────────────────────────────────────
        style = ttk.Style()
        style.configure("Buy.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=24,
            font=("Consolas", 9), borderwidth=0)
        style.configure("Buy.Treeview.Heading",
            background="#0a1f14", foreground="#4ade80",
            font=("Consolas", 8, "bold"), relief="flat")
        style.map("Buy.Treeview",
            background=[("selected", TABLE_SELECT)],
            foreground=[("selected", "#ffffff")])

        cols = [c[0] for c in BUY_COLS]
        tree_f = tk.Frame(self, bg=BG_PANEL)
        tree_f.pack(fill="both", expand=True)

        self._tree = ttk.Treeview(tree_f, columns=cols, show="headings",
                                   style="Buy.Treeview")
        for col, width in BUY_COLS:
            self._tree.heading(col, text=col,
                command=lambda c=col: self._sort_by(c))
            anchor = "w" if col in ("Sebep", "Setup") else "center"
            self._tree.column(col, width=width, anchor=anchor,
                                stretch=(col == "Sebep"))

        sb = ttk.Scrollbar(tree_f, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_sel)
        self._tree.bind("<Double-Button-1>",  self._on_dbl)

        # ── Alt bilgi ─────────────────────────────────────────
        self._footer = tk.Label(self,
            text="Çift tıkla → İşlem aç",
            font=("Consolas", 7), bg=BG_DARK, fg=TEXT_DIM, pady=2)
        self._footer.pack(fill="x")

        self._all_signals = []   # filtrelenmemiş tam liste

    def update(self, signals: list) -> None:
        self._all_signals = signals
        self._apply_filter()

    def _apply_filter(self):
        filt = self._filter_var.get()
        search = self._search_var.get().upper().strip()
        
        filtered = self._all_signals
        if filt != "TÜMÜ":
            filtered = [s for s in filtered if s.quality_label == filt]
        if search:
            filtered = [s for s in filtered if search in s.symbol.upper()]

        # Dinamik Sıralama
        filtered = self._sort_signals(filtered)
        
        self._signals = filtered
        self._render(filtered)

    def _sort_signals(self, signals: list):
        if not signals: return []
        col = self._sort_col
        rev = self._sort_rev
        
        # Kolon bazlı sort key
        if col == "Hisse": key = lambda s: s.symbol
        elif col == "Rejim": key = lambda s: getattr(s, 'regime', '')
        elif col == "Entry": key = lambda s: s.entry
        elif col == "Stop": key = lambda s: s.stop
        elif col == "Hedef": key = lambda s: s.target
        elif col == "R/R": key = lambda s: s.rr_ratio
        elif col == "Güven": key = lambda s: s.confidence
        elif col == "Kalite": key = lambda s: s.quality_label
        elif col == "Skor": key = lambda s: getattr(s, 'combined_score', 0)
        else: key = lambda s: s.symbol
        
        return sorted(signals, key=key, reverse=rev)

    def _render(self, signals: list):
        for row in self._tree.get_children():
            self._tree.delete(row)

        for i, sig in enumerate(signals):
            ql  = sig.quality_label
            col = _QL_COLORS.get(ql, TEXT_SECONDARY)
            bg  = _QL_BG.get(ql, TABLE_ROW_EVEN)
            tag = f"buy_{i}_{ql}"

            # Setup tipi
            setup_type = getattr(sig, 'setup_type', '')
            if not setup_type and hasattr(sig, 'reason'):
                r = sig.reason or ""
                if "PULLBACK" in r.upper() or "Rebreak" in r:
                    setup_type = "Pullback"
                elif "BREAKOUT" in r.upper() or "Kırılım" in r:
                    setup_type = "Breakout"
                elif "MOMENTUM" in r.upper():
                    setup_type = "Momentum"
                else:
                    setup_type = "—"

            # Rejim ve Strateji Tipi
            regime_str = getattr(sig, 'regime', '') or ''
            strategy_str = getattr(sig, 'strategy_type', '') or ''
            
            regime_short = {
                'BULL': '🟢 BULL', 'WEAK_BULL': '🟡 W.BULL',
                'RANGE': '🔵 RANGE', 'VOLATILE': '🟠 VOLATILE',
                'BEAR': '🔴 BEAR', 'WEAK_BEAR': '🟠 W.BEAR',
                'EDGE': '🟣 EDGE',
            }.get(regime_str, regime_str[:10] if regime_str else '—')
            
            strategy_short = {
                'BULL_BREAKOUT':    '📈 Breakout',
                'RANGE_REVERSION':  '↩ MeanRev',
                'VOLATILE_BREAKOUT':'⚡ VolBreak',
                'EDGE_MULTI':       '🦈 CoreSwing',
            }.get(strategy_str, strategy_str[:14] if strategy_str else '—')

            lot = str(sig.lots) if hasattr(sig, 'lots') and sig.lots else "—"

            self._tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                sig.symbol,
                regime_short,
                strategy_short,
                setup_type,
                f"₺{sig.entry:.2f}",
                f"₺{sig.stop:.2f}",
                f"₺{sig.target:.2f}",
                f"{sig.rr_ratio:.1f}x",
                f"%{sig.confidence:.0f}",
                f"{sig.sector_name[:12]}",
                sig.reason[:50] if sig.reason else "—",
                lot,
                ql,
            ))
            self._tree.tag_configure(tag, foreground=col, background=bg)

        n = len(signals)
        self._count_lbl.config(
            text=f"  {n} aktif AL sinyali" if n else "  Sinyal bekleniyor...",
            fg=COLOR_POSITIVE if n > 0 else TEXT_DIM
        )
        all_n = len(self._all_signals)
        self._hint.config(
            text=f"⏳ {all_n} sinyal aktif — Çift tıkla işlem aç  |  Kalite: A+={sum(1 for s in signals if s.quality_label=='A+')}  A={sum(1 for s in signals if s.quality_label=='A')}  B={sum(1 for s in signals if s.quality_label=='B')}",
            fg=TEXT_DIM
        )

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = True
        self._apply_filter()

    def _on_sel(self, event):
        sel = self._tree.selection()
        if sel and self._on_select:
            idx = int(sel[0])
            if idx < len(self._signals):
                self._on_select(self._signals[idx].symbol)

    def _on_dbl(self, event):
        sel = self._tree.selection()
        if sel and self._on_buy:
            idx = int(sel[0])
            if idx < len(self._signals):
                self._on_buy(self._signals[idx])


# ══════════════════════════════════════════════════════════════
# 2. SETUP PANEL — SETUP + CONFIRMING (yaklaşan sinyaller)
# ══════════════════════════════════════════════════════════════

SETUP_COLS = [
    ("Hisse",   58), ("Setup Türü", 110), ("Kriter",  65),
    ("Eksik",  160), ("Teyit",     80),   ("Durum",   90),
]

class SetupPanel(tk.Frame):
    def __init__(self, parent, on_select: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._on_select = on_select
        self._items     = []
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=PANEL_TITLE_BG, pady=5); hdr.pack(fill="x")
        tk.Label(hdr, text="⏳  SETUP  —  Teyit Bekleyen Sinyaller",
                 font=("Consolas", 10, "bold"),
                 bg=PANEL_TITLE_BG, fg=COLOR_WARNING).pack(side="left", padx=10)
        self._cnt = tk.Label(hdr, text="", font=FONT_SMALL, bg=PANEL_TITLE_BG, fg=TEXT_DIM)
        self._cnt.pack(side="right", padx=10)

        tk.Label(self, text="Bu hisseler kriterleri karşılıyor — 15s korunursa AL sinyaline geçer",
            font=("Consolas", 8), bg=BG_DARK, fg=TEXT_DIM, pady=3).pack(fill="x")

        style = ttk.Style()
        style.configure("Setup2.Treeview", background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=22, font=("Consolas", 9), borderwidth=0)
        style.configure("Setup2.Treeview.Heading", background="#1a1000", foreground=COLOR_WARNING,
            font=("Consolas", 8, "bold"), relief="flat")
        style.map("Setup2.Treeview", background=[("selected", TABLE_SELECT)])

        tree_f = tk.Frame(self, bg=BG_PANEL); tree_f.pack(fill="both", expand=True)
        cols = [c[0] for c in SETUP_COLS]
        self._tree = ttk.Treeview(tree_f, columns=cols, show="headings", style="Setup2.Treeview")
        for col, w in SETUP_COLS:
            self._tree.heading(col, text=col)
            anchor = "w" if col in ("Eksik", "Setup Türü") else "center"
            self._tree.column(col, width=w, anchor=anchor, stretch=(col == "Eksik"))
        sb = ttk.Scrollbar(tree_f, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._sel)

    def update(self, setups: list) -> None:
        self._items = setups
        for row in self._tree.get_children():
            self._tree.delete(row)
        for i, sig in enumerate(setups):
            n_met = len(sig.criteria_met)
            n_total = n_met + len(sig.criteria_miss)
            pct = n_met / n_total * 100 if n_total else 0
            is_conf = sig.state.value == "CONFIRMING"
            if is_conf:
                rem = max(0, 15 - sig.state_age_secs)
                teyit, state, col = f"⏱ {rem:.0f}s", "TEYIT EDİLİYOR", "#fbbf24"
            else:
                teyit, state, col = f"%{pct:.0f}", f"SETUP ({n_met}/{n_total})", TEXT_SECONDARY
            
            met = sig.criteria_met
            setup_type = "Trend+Breakout" if ("trend" in met and "breakout" in met) else ("Breakout" if "breakout" in met else ("Trend" if "trend" in met else "Gelişiyor"))
            eksik = ", ".join(sig.criteria_miss[:3]) if sig.criteria_miss else "—"
            bg = "#100800" if is_conf else (TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN)
            tag = f"s_{i}"
            self._tree.insert("", "end", iid=str(i), tags=(tag,), values=(sig.symbol, setup_type, f"{n_met}/{n_total}", eksik, teyit, state))
            self._tree.tag_configure(tag, foreground=col, background=bg)
        n = len(setups); conf_n = sum(1 for s in setups if s.state.value == "CONFIRMING")
        self._cnt.config(text=f"{n} setup  |  {conf_n} teyitte", fg=COLOR_WARNING if n > 0 else TEXT_DIM)

    def _sel(self, event):
        sel = self._tree.selection()
        if sel and self._on_select:
            idx = int(sel[0])
            if idx < len(self._items): self._on_select(self._items[idx].symbol)


# ══════════════════════════════════════════════════════════════
# 3. WATCHLIST PANEL — izleme listesi
# ══════════════════════════════════════════════════════════════

WL_COLS = [
    ("Hisse",   58), ("Sektör",  100), ("Trend",  60),
    ("RS",      55), ("Score",   50),  ("Sebep",  200),
]

class WatchlistSignalPanel(tk.Frame):
    def __init__(self, parent, on_select: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._on_select = on_select
        self._items     = []
        self._raw       = []
        self._rs        = {}
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._resort())
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=PANEL_TITLE_BG, pady=5); hdr.pack(fill="x")
        tk.Label(hdr, text="👁  WATCHLIST  —  İzleme Listesi", font=("Consolas", 10, "bold"),
                 bg=PANEL_TITLE_BG, fg=COLOR_ACCENT).pack(side="left", padx=10)
        self._cnt = tk.Label(hdr, text="", font=FONT_SMALL, bg=PANEL_TITLE_BG, fg=TEXT_DIM)
        self._cnt.pack(side="right", padx=10)

        search_f = tk.Frame(hdr, bg=PANEL_TITLE_BG); search_f.pack(side="right", padx=10)
        tk.Label(search_f, text="🔍", font=("Consolas", 8), bg=PANEL_TITLE_BG, fg=COLOR_ACCENT).pack(side="left")
        tk.Entry(search_f, textvariable=self._search_var, width=10, font=("Consolas", 8), 
                 bg=BG_DARK, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat").pack(side="left", padx=5)

        sort_f = tk.Frame(hdr, bg=PANEL_TITLE_BG); sort_f.pack(side="right", padx=8)
        self._sort_var = tk.StringVar(value="RS")
        tk.Label(sort_f, text="Sırala:", font=("Consolas", 7), bg=PANEL_TITLE_BG, fg=TEXT_DIM).pack(side="left")
        for s in ["RS", "Score", "Sektör"]:
            tk.Radiobutton(sort_f, text=s, variable=self._sort_var, value=s, font=("Consolas", 7), 
                           bg=PANEL_TITLE_BG, fg=TEXT_DIM, selectcolor=BG_DARK, activebackground=PANEL_TITLE_BG,
                           cursor="hand2", command=self._resort).pack(side="left", padx=3)

        tk.Label(self, text="Bu hisseler henüz sinyal vermedi — kriterleri oluşmaya başlıyor",
                 font=("Consolas", 8), bg=BG_DARK, fg=TEXT_DIM, pady=3).pack(fill="x")

        style = ttk.Style()
        style.configure("WLS.Treeview", background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY, fieldbackground=TABLE_ROW_EVEN,
                        rowheight=21, font=("Consolas", 9), borderwidth=0)
        style.configure("WLS.Treeview.Heading", background="#0a0e1a", foreground=COLOR_ACCENT, font=("Consolas", 8, "bold"), relief="flat")
        style.map("WLS.Treeview", background=[("selected", TABLE_SELECT)])

        tree_f = tk.Frame(self, bg=BG_PANEL); tree_f.pack(fill="both", expand=True)
        cols = [c[0] for c in WL_COLS]
        self._tree = ttk.Treeview(tree_f, columns=cols, show="headings", style="WLS.Treeview")
        for col, w in WL_COLS:
            self._tree.heading(col, text=col, command=lambda c=col: self._sort_by_header(c))
            self._tree.column(col, width=w, anchor="w" if col == "Sebep" else "center", stretch=(col == "Sebep"))
        sb = ttk.Scrollbar(tree_f, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._sel)

    def update(self, watchlist_signals: list, rs_results: dict = None) -> None:
        self._raw, self._rs = watchlist_signals, rs_results or {}
        self._resort()

    def _sort_by_header(self, col):
        if col == "Hisse": self._sort_var.set("Score") # Toggle dummy
        self._resort()

    def _resort(self):
        srt, search = self._sort_var.get(), self._search_var.get().upper().strip()
        items = [s for s in self._raw if search in s.symbol.upper()] if search else list(self._raw)
        if srt == "RS": items.sort(key=lambda s: self._rs.get(s.symbol, _FakeRS()).rs_vs_index, reverse=True)
        elif srt == "Score": items.sort(key=lambda s: s.combined_score, reverse=True)
        elif srt == "Sektör": items.sort(key=lambda s: s.sector_name)
        self._items = items; self._render()

    def _render(self):
        for row in self._tree.get_children(): self._tree.delete(row)
        for i, sig in enumerate(self._items):
            rs_val = self._rs.get(sig.symbol).rs_vs_index if self._rs.get(sig.symbol) else 0.0
            rs_col = COLOR_POSITIVE if rs_val > 0 else (COLOR_NEGATIVE if rs_val < -0.3 else TEXT_DIM)
            trend_txt = "↑ TREND" if (sig.criteria_met and "trend" in sig.criteria_met) else "—"
            n_met = len(sig.criteria_met); n_total = n_met + len(sig.criteria_miss)
            met_str = ", ".join(sig.criteria_met[:3]) if sig.criteria_met else "Kriter bekleniyor"
            bg = TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN; tag = f"w_{i}"
            self._tree.insert("", "end", iid=str(i), tags=(tag,), values=(sig.symbol, sig.sector_name[:12], trend_txt, f"{rs_val:+.2f}", f"{n_met}/{n_total}", met_str[:50]))
            self._tree.tag_configure(tag, foreground=rs_col if rs_val != 0 else TEXT_DIM, background=bg)
        n = len(self._items); self._cnt.config(text=f"{n} hisse izleniyor", fg=COLOR_ACCENT if n > 0 else TEXT_DIM)

    def _sel(self, event):
        sel = self._tree.selection()
        if sel and self._on_select:
            idx = int(sel[0])
            if idx < len(self._items): self._on_select(self._items[idx].symbol)

class _FakeRS: rs_vs_index = 0.0

TradeSignalsPanel = BuySignalsPanel
