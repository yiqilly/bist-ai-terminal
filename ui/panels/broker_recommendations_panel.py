# ============================================================
# ui/panels/broker_recommendations_panel.py — Kurum (v3)
# ============================================================
import tkinter as tk
from tkinter import ttk
from ui.theme import *
from data.models import BrokerRecommendation, BrokerConsensus

_REC_COL = {
    "AL": COLOR_POSITIVE, "Endeks Üstü Getiri": "#4ade80",
    "TUT": COLOR_WARNING, "Endekse Paralel": TEXT_SECONDARY,
    "SAT": COLOR_NEGATIVE, "Endeks Altı Getiri": "#ff8080",
}


class BrokerRecommendationsPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        self._on_symbol_click = kwargs.pop("on_symbol_click", None)
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._build()

    def _build(self):
        h = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4)
        h.pack(fill="x")
        self._title = tk.Label(h, text="◈  KURUM ÖNERİLERİ",
                                font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG)
        self._title.pack(side="left", padx=10)
        self._cons_lbl = tk.Label(h, text="", font=FONT_HEADER, bg=PANEL_TITLE_BG, fg=TEXT_DIM)
        self._cons_lbl.pack(side="right", padx=10)

        # Konsensüs özeti kartı
        self._sum_frame = tk.Frame(self, bg=BG_CARD,
                                    highlightbackground=BORDER, highlightthickness=1)
        self._sum_frame.pack(fill="x", padx=4, pady=(4,2))

        sum_row = tk.Frame(self._sum_frame, bg=BG_CARD); sum_row.pack(fill="x", padx=8, pady=4)
        self._buy_lbl  = self._metric(sum_row, "AL")
        self._hold_lbl = self._metric(sum_row, "TUT")
        self._sell_lbl = self._metric(sum_row, "SAT")
        self._tgt_lbl  = self._metric(sum_row, "Ort.Hedef")
        self._pot_lbl  = self._metric(sum_row, "Potansiyel")
        self._tot_lbl  = self._metric(sum_row, "Kurum")

        # Bireysel öneriler
        self._rec_frame = tk.Frame(self, bg=BG_PANEL)
        self._rec_frame.pack(fill="both", expand=True, padx=4, pady=2)

    def _metric(self, parent, label):
        f = tk.Frame(parent, bg=BG_CARD); f.pack(side="left", padx=6)
        tk.Label(f, text=label, font=("Consolas",7), bg=BG_CARD, fg=TEXT_DIM).pack()
        v = tk.Label(f, text="—", font=FONT_SMALL, bg=BG_CARD, fg=TEXT_PRIMARY); v.pack(); return v

    def update(self, symbol, recs: list[BrokerRecommendation],
               consensus: BrokerConsensus | None, get_pot):
        self._title.config(text=f"◈  KURUM{' — '+symbol if symbol else ''}")
        if consensus:
            cons_col = _REC_COL.get(consensus.consensus, TEXT_SECONDARY)
            self._cons_lbl.config(text=f"KONSENSÜS: {consensus.consensus}", fg=cons_col)
            self._buy_lbl.config(text=str(consensus.buy_count),  fg=COLOR_POSITIVE)
            self._hold_lbl.config(text=str(consensus.hold_count), fg=COLOR_WARNING)
            self._sell_lbl.config(text=str(consensus.sell_count), fg=COLOR_NEGATIVE)
            self._tgt_lbl.config(text=f"₺{consensus.avg_target:.1f}")
            pot_col = COLOR_POSITIVE if consensus.potential_pct >= 0 else COLOR_NEGATIVE
            self._pot_lbl.config(text=f"{consensus.potential_pct:+.1f}%", fg=pot_col)
            self._tot_lbl.config(text=str(consensus.total_recs))

    def update_top_picks(self, picks: list[BrokerConsensus]):
        """Yeni Refaktör: Global Top Picks (Konsensüs) listesini günceller."""
        self._title.config(text="◈  KURUM TOP PICKS (GLOBAL)")
        self._sum_frame.pack_forget() # Global modda özeti gizle

        for w in self._rec_frame.winfo_children(): w.destroy()
        if not picks:
            tk.Label(self._rec_frame, text="Henüz öneri verisi yok",
                     font=FONT_SMALL, bg=BG_PANEL, fg=TEXT_DIM).pack(pady=8)
            return

        for cons in picks:
            self._build_top_picks_card(cons)

    def _build_top_picks_card(self, cons: BrokerConsensus):
        rc = _REC_COL.get(cons.consensus, TEXT_SECONDARY)
        card = tk.Frame(self._rec_frame, bg=BG_CARD,
                         highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=2)
        
        # Sol Taraf: Sembol ve Konsensüs
        left = tk.Frame(card, bg=BG_CARD); left.pack(side="left", padx=8, pady=4)
        tk.Label(left, text=cons.symbol, font=FONT_TITLE, bg=BG_CARD, fg=COLOR_ACCENT).pack(side="left")
        tk.Label(left, text=cons.consensus, font=FONT_HEADER, bg=BG_CARD, fg=rc).pack(side="left", padx=10)
        
        # Sağ Taraf: Potansiyel ve Hedef
        right = tk.Frame(card, bg=BG_CARD); right.pack(side="right", padx=8)
        pot_col = COLOR_POSITIVE if cons.potential_pct >= 0 else COLOR_NEGATIVE
        tk.Label(right, text=f"%{cons.potential_pct:+.1f}", font=FONT_HEADER, bg=BG_CARD, fg=pot_col).pack(side="right")
        tk.Label(right, text=f"₺{cons.avg_target:.1f}", font=FONT_SMALL, bg=BG_CARD, fg=TEXT_SECONDARY).pack(side="right", padx=8)

    def _build_card(self, rec, potential):
        rc = _REC_COL.get(rec.recommendation, TEXT_SECONDARY)
        card = tk.Frame(self._rec_frame, bg=BG_CARD,
                         highlightbackground=rc, highlightthickness=1)
        card.pack(fill="x", pady=2)
        r1 = tk.Frame(card, bg=BG_CARD); r1.pack(fill="x", padx=6, pady=(4,0))
        tk.Label(r1, text=rec.broker, font=FONT_HEADER, bg=BG_CARD, fg=TEXT_PRIMARY).pack(side="left")
        tk.Label(r1, text=rec.recommendation, font=FONT_HEADER, bg=BG_CARD, fg=rc).pack(side="right")
        r2 = tk.Frame(card, bg=BG_CARD); r2.pack(fill="x", padx=6)
        tk.Label(r2, text=f"₺{rec.target_price:.1f}", font=FONT_SMALL, bg=BG_CARD, fg=TEXT_SECONDARY).pack(side="left")
        pot_col = COLOR_POSITIVE if potential >= 0 else COLOR_NEGATIVE
        tk.Label(r2, text=f"{potential:+.1f}%", font=FONT_SMALL, bg=BG_CARD, fg=pot_col).pack(side="left", padx=8)
        tk.Label(r2, text=rec.report_date.strftime("%d.%m.%y"), font=FONT_SMALL, bg=BG_CARD, fg=TEXT_DIM).pack(side="right")
        if rec.note:
            tk.Label(card, text=rec.note, font=FONT_SMALL, bg=BG_CARD, fg=TEXT_DIM,
                     wraplength=285, anchor="w", justify="left").pack(padx=6, pady=(0,4), anchor="w")
        else:
            tk.Frame(card, height=4, bg=BG_CARD).pack()
