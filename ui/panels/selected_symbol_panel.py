# ============================================================
# ui/panels/selected_symbol_panel.py — Karar Destek Paneli v5
#
# Tek bakışta "ne yapmalıyım?" sorusuna cevap verir.
#
# 1. HİSSE ÖZETİ   → sembol, sektör, signal state, setup
# 2. KARAR BLOĞU   → BUY / WATCHLIST / SELL kararı + sebep
# 3. TRADE BOX     → entry, stop, target, R/R, confidence, lot
# 4. TEKNİK ÖZET   → trend, breakout, volume, RS, sektör güç, rejim
# 5. DETAY         → skor, uyarılar, analiz notu
# ============================================================
import tkinter as tk
from tkinter import ttk
from ui.theme import *
from data.models import SymbolDetailViewModel


# ── Renk yardımcıları ────────────────────────────────────────

def _ql_color(ql: str) -> str:
    return {"A+": "#4ade80", "A": "#86efac",
            "B": "#fbbf24", "Watchlist": "#94a3b8"}.get(ql, "#94a3b8")

def _yn_color(active: bool) -> str:
    return COLOR_POSITIVE if active else TEXT_DIM

def _pnl_color(v: float) -> str:
    return COLOR_POSITIVE if v >= 0 else COLOR_NEGATIVE


# ══════════════════════════════════════════════════════════════
# Karar Destek Paneli
# ══════════════════════════════════════════════════════════════

class SelectedSymbolPanel(tk.Frame):
    """
    Sağ panel — karar destek merkezi.
    Seçili hisse için tek bakışta tam karar desteği.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self._vm: SymbolDetailViewModel | None = None
        self._build()

    # ── Layout ───────────────────────────────────────────────

    def _build(self):
        # Scrollable container
        outer = tk.Frame(self, bg=BG_DARK)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=BG_DARK, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._sf = tk.Frame(canvas, bg=BG_DARK)
        win = canvas.create_window((0, 0), window=self._sf, anchor="nw")
        self._sf.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(win, width=e.width))
        canvas.bind("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        sf = self._sf

        # ── 0. YOK mesajı ─────────────────────────────────────
        self._empty_lbl = tk.Label(sf,
            text="◈  Heatmap'ten bir hisse seçin",
            font=("Consolas", 10), bg=BG_DARK, fg=TEXT_DIM, pady=30)
        self._empty_lbl.pack()

        # ── 1. HİSSE ÖZETİ ────────────────────────────────────
        hdr = self._section(sf, "")  # başlıksız — sembol kendisi başlık
        hdr.pack_configure(pady=(0, 0))

        # Sembol + Fiyat satırı
        sym_row = tk.Frame(hdr, bg=BG_CARD); sym_row.pack(fill="x", padx=10, pady=(8, 2))
        self._sym_lbl = tk.Label(sym_row, text="—",
            font=("Consolas", 20, "bold"), bg=BG_CARD, fg=TEXT_PRIMARY)
        self._sym_lbl.pack(side="left")

        price_col = tk.Frame(sym_row, bg=BG_CARD); price_col.pack(side="right")
        self._price_lbl = tk.Label(price_col, text="—",
            font=("Consolas", 16, "bold"), bg=BG_CARD, fg=COLOR_ACCENT)
        self._price_lbl.pack(anchor="e")
        self._chg_lbl = tk.Label(price_col, text="—",
            font=("Consolas", 10, "bold"), bg=BG_CARD, fg=TEXT_SECONDARY)
        self._chg_lbl.pack(anchor="e")

        # Sektör + Signal State + Setup satırı
        meta_row = tk.Frame(hdr, bg=BG_CARD); meta_row.pack(fill="x", padx=10, pady=(2, 8))

        self._sector_lbl = tk.Label(meta_row, text="—",
            font=("Consolas", 8), bg=BG_CARD, fg=TEXT_DIM)
        self._sector_lbl.pack(side="left")

        self._state_lbl = tk.Label(meta_row, text="",
            font=("Consolas", 8, "bold"), bg=BG_CARD, fg=TEXT_DIM)
        self._state_lbl.pack(side="right")

        self._setup_lbl = tk.Label(meta_row, text="",
            font=("Consolas", 8), bg=BG_CARD, fg=TEXT_DIM)
        self._setup_lbl.pack(side="right", padx=6)

        # ── 2. KARAR BLOĞU ─────────────────────────────────────
        dec = self._section(sf, "KARAR")
        self._decision_frame = tk.Frame(dec, bg=BG_CARD)
        self._decision_frame.pack(fill="x", padx=8, pady=(4, 8))

        # Büyük karar butonu (renk + metin değişir)
        self._decision_btn = tk.Label(
            self._decision_frame,
            text="—  SEÇİM YOK",
            font=("Consolas", 13, "bold"),
            bg=BG_DARK, fg=TEXT_DIM,
            pady=10, relief="flat",
        )
        self._decision_btn.pack(fill="x", pady=(0, 4))

        # Kısa sebep metni
        self._decision_reason = tk.Label(
            self._decision_frame,
            text="",
            font=("Consolas", 8),
            bg=BG_CARD, fg=TEXT_DIM,
            wraplength=310, justify="left",
        )
        self._decision_reason.pack(fill="x", padx=2)

        # Kriter göstergesi (küçük progress barlar)
        self._crit_frame = tk.Frame(self._decision_frame, bg=BG_CARD)
        self._crit_frame.pack(fill="x", pady=(6, 0))

        # ── 3. TRADE BOX ──────────────────────────────────────
        tb = self._section(sf, "TRADE BOX")

        # Ana rakamlar (2×3 grid)
        grid = tk.Frame(tb, bg=BG_CARD); grid.pack(fill="x", padx=8, pady=(4, 8))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(2, weight=1)

        def trade_cell(parent, r, c, label):
            f = tk.Frame(parent, bg="#0a1a2a",
                         highlightbackground=BORDER, highlightthickness=1)
            f.grid(row=r, column=c, padx=3, pady=3, sticky="ew")
            tk.Label(f, text=label, font=("Consolas", 7),
                     bg="#0a1a2a", fg=TEXT_DIM).pack(pady=(4, 0))
            v = tk.Label(f, text="—",
                font=("Consolas", 12, "bold"), bg="#0a1a2a", fg=TEXT_PRIMARY)
            v.pack(pady=(0, 4))
            return v

        self._tb_entry  = trade_cell(grid, 0, 0, "ENTRY")
        self._tb_stop   = trade_cell(grid, 0, 1, "STOP")
        self._tb_target = trade_cell(grid, 0, 2, "HEDEF")
        self._tb_rr     = trade_cell(grid, 1, 0, "R/R")
        self._tb_conf   = trade_cell(grid, 1, 1, "GÜVEN")
        self._tb_lot    = trade_cell(grid, 1, 2, "ÖNERİLEN LOT")

        # ── 4. TEKNİK ÖZET ────────────────────────────────────
        tech = self._section(sf, "TEKNİK ÖZET")
        tech_inner = tk.Frame(tech, bg=BG_CARD); tech_inner.pack(fill="x", padx=8, pady=(4, 8))

        # Sinyal göstergeleri (yatay, renkli kutucuklar)
        sig_row = tk.Frame(tech_inner, bg=BG_CARD); sig_row.pack(fill="x", pady=(0, 6))
        self._sig_labels: dict[str, tk.Label] = {}
        for key, txt in [("trend","TREND"),("breakout","BREAKOUT"),
                          ("volume","HACİM"),("rs","RS")]:
            lbl = tk.Label(sig_row, text=f"● {txt}",
                font=("Consolas", 8, "bold"),
                bg=BG_DARK, fg=TEXT_DIM,
                padx=6, pady=3, relief="flat")
            lbl.pack(side="left", padx=2)
            self._sig_labels[key] = lbl

        # Metrik satırları
        self._tech_rows: dict[str, tuple] = {}
        for label, key in [
            ("RSI",      "rsi"),
            ("EMA9/21",  "ema"),
            ("ATR",      "atr"),
            ("Hacim",    "vol"),
            ("RS Skoru", "rs_score"),
            ("Sektör Güç", "sec_str"),
            ("Rejim",    "regime"),
        ]:
            row = tk.Frame(tech_inner, bg=BG_CARD); row.pack(fill="x", pady=1)
            tk.Label(row, text=label, font=("Consolas", 8),
                     bg=BG_CARD, fg=TEXT_DIM, width=11, anchor="w").pack(side="left")
            tk.Label(row, text=":", font=("Consolas", 8),
                     bg=BG_CARD, fg=TEXT_DIM).pack(side="left")
            val = tk.Label(row, text="—", font=("Consolas", 8, "bold"),
                           bg=BG_CARD, fg=TEXT_PRIMARY, anchor="w")
            val.pack(side="left", padx=4)
            bar = tk.Canvas(row, height=6, width=80, bg=BG_DARK,
                            highlightthickness=0)
            bar.pack(side="right", padx=4)
            self._tech_rows[key] = (val, bar)

        # ── 5. DETAY (opsiyonel — küçük font) ─────────────────
        det = self._section(sf, "DETAY")
        det_inner = tk.Frame(det, bg=BG_CARD); det_inner.pack(fill="x", padx=8, pady=(4, 8))

        # Skor grid
        score_row = tk.Frame(det_inner, bg=BG_CARD); score_row.pack(fill="x", pady=(0, 4))
        self._score_cells: dict[str, tk.Label] = {}
        for key, lbl in [("comb","Birleşik"),("conf","Güven"),("flow","Flow"),("ai","AI")]:
            f = tk.Frame(score_row, bg=BG_CARD)
            f.pack(side="left", expand=True)
            tk.Label(f, text=lbl, font=("Consolas", 7),
                     bg=BG_CARD, fg=TEXT_DIM).pack()
            v = tk.Label(f, text="—", font=("Consolas", 9, "bold"),
                         bg=BG_CARD, fg=TEXT_PRIMARY)
            v.pack()
            self._score_cells[key] = v

        # Analiz notu
        self._note_lbl = tk.Label(det_inner, text="",
            font=("Consolas", 8), bg=BG_CARD, fg=TEXT_SECONDARY,
            wraplength=310, justify="left")
        self._note_lbl.pack(fill="x", pady=(4, 0))

        # Uyarılar
        self._alert_frame = tk.Frame(det_inner, bg=BG_CARD)
        self._alert_frame.pack(fill="x")

    # ── Yardımcılar ──────────────────────────────────────────

    def _section(self, parent, title: str) -> tk.Frame:
        """Başlıklı kart bölümü."""
        outer = tk.Frame(parent, bg=BG_CARD,
                         highlightbackground=BORDER, highlightthickness=1)
        outer.pack(fill="x", padx=6, pady=3)
        if title:
            tk.Label(outer, text=f"  {title}",
                font=("Consolas", 7, "bold"),
                bg="#0c1320", fg=TEXT_DIM,
                pady=3, anchor="w"
            ).pack(fill="x")
        return outer

    def _bar(self, canvas: tk.Canvas, pct: float, color: str) -> None:
        """Küçük yatay progress bar çiz."""
        canvas.delete("all")
        w = int(canvas.winfo_width()) or 80
        canvas.create_rectangle(0, 0, w, 6, fill=BG_DARK, outline="")
        canvas.create_rectangle(0, 0, int(w * max(0, min(1, pct))), 6,
                                 fill=color, outline="")

    def _pill(self, frame: tk.Frame, text: str, color: str) -> None:
        """Küçük renkli etiket."""
        tk.Label(frame, text=text, font=("Consolas", 7, "bold"),
                 bg=color, fg="#000000" if color in ("#4ade80","#fbbf24","#86efac") else "white",
                 padx=4, pady=1).pack(side="left", padx=2, pady=2)

    # ── Ana güncelleme ────────────────────────────────────────

    def update(self, vm: SymbolDetailViewModel | None) -> None:
        self._vm = vm

        if vm is None:
            self._empty_lbl.config(text="◈  Heatmap'ten bir hisse seçin", fg=TEXT_DIM)
            self._sym_lbl.config(text="—")
            self._price_lbl.config(text="—")
            self._decision_btn.config(text="—  SEÇİM YOK", bg=BG_DARK, fg=TEXT_DIM)
            self._decision_reason.config(text="")
            return

        self._empty_lbl.config(text="")

        # ── 1. HİSSE ÖZETİ ───────────────────────────────────
        chg_col = _pnl_color(vm.change_pct)
        self._sym_lbl.config(text=vm.symbol, fg=TEXT_PRIMARY)
        self._price_lbl.config(text=f"₺{vm.price:.2f}", fg=COLOR_ACCENT)
        self._chg_lbl.config(text=f"{vm.change_pct:+.2f}%", fg=chg_col)

        # Sektör
        self._sector_lbl.config(
            text=f"📊  {vm.sector_name or '—'}  •  Güç: {vm.sector_strength:.0f}/100"
        )

        # Signal state (TradeSignal'dan gelir — ViewModel'de yoksa quality_label kullan)
        ql = vm.quality_label
        state_txt = {
            "A+": "🚀 BUY A+", "A": "🚀 BUY A", "B": "🔔 BUY B",
            "Watchlist": "👁 WATCHLIST", "Elite": "⭐ ELITE"
        }.get(ql, f"• {ql}")
        state_col = _ql_color(ql)
        self._state_lbl.config(text=state_txt, fg=state_col)
        self._setup_lbl.config(text=vm.core_setup_type or "—", fg=TEXT_DIM)

        # ── 2. KARAR BLOĞU ───────────────────────────────────
        self._update_decision(vm)

        # ── 3. TRADE BOX ─────────────────────────────────────
        rr = vm.rr_ratio
        rr_col = COLOR_POSITIVE if rr >= 2.0 else (COLOR_WARNING if rr >= 1.5 else COLOR_NEGATIVE)
        conf_col = COLOR_POSITIVE if vm.confidence >= 65 else (
                   COLOR_WARNING if vm.confidence >= 50 else COLOR_NEGATIVE)

        self._tb_entry.config(text=f"₺{vm.entry:.2f}", fg=TEXT_PRIMARY)
        self._tb_stop.config(text=f"₺{vm.stop:.2f}", fg=COLOR_NEGATIVE)
        self._tb_target.config(text=f"₺{vm.target:.2f}", fg=COLOR_POSITIVE)
        self._tb_rr.config(text=f"{rr:.1f}x", fg=rr_col)
        self._tb_conf.config(text=f"%{vm.confidence:.0f}", fg=conf_col)
        if vm.position_size and hasattr(vm.position_size, 'suggested_lots'):
            self._tb_lot.config(
                text=str(vm.position_size.suggested_lots),
                fg=COLOR_ACCENT
            )
        else:
            self._tb_lot.config(text="—", fg=TEXT_DIM)

        # ── 4. TEKNİK ÖZET ───────────────────────────────────
        self._update_technical(vm)

        # ── 5. DETAY ─────────────────────────────────────────
        self._update_detail(vm)

    # ── Karar Bloğu ──────────────────────────────────────────

    def _update_decision(self, vm: SymbolDetailViewModel) -> None:
        """Karar kutusunu güncelle — BUY / WATCH / SELL."""
        ql = vm.quality_label

        # Karar mantığı
        if ql in ("A+", "A"):
            decision  = "🚀  AL"
            dec_bg    = "#0a2010"
            dec_fg    = "#4ade80"
            dec_border = "#4ade80"
        elif ql == "B":
            decision  = "🔔  İZLE — YAKLAŞIYOR"
            dec_bg    = "#1a1000"
            dec_fg    = "#fbbf24"
            dec_border = "#fbbf24"
        elif vm.trend and vm.breakout:
            decision  = "👁  WATCHLIST"
            dec_bg    = "#0a1020"
            dec_fg    = "#3b82f6"
            dec_border = "#3b82f6"
        else:
            decision  = "⏳  BEKLE"
            dec_bg    = BG_DARK
            dec_fg    = TEXT_DIM
            dec_border = BORDER

        self._decision_btn.config(
            text=decision, bg=dec_bg, fg=dec_fg,
            highlightbackground=dec_border
        )

        # Sebep metni
        reasons = []
        if vm.trend:           reasons.append("trend ↑")
        if vm.breakout:        reasons.append("kırılım")
        if vm.volume_confirm:  reasons.append("hacim onayı")
        rsi_ok = 52 <= vm.rsi <= 72
        if rsi_ok:             reasons.append(f"RSI={vm.rsi:.0f} ✓")
        else:                  reasons.append(f"RSI={vm.rsi:.0f} ✗")
        if vm.rr_ratio >= 1.8: reasons.append(f"R/R={vm.rr_ratio:.1f}x ✓")
        reason_txt = "  |  ".join(reasons[:4])

        # Eksik olanları ekle
        missing = []
        if not vm.trend:          missing.append("trend yok")
        if not vm.breakout:       missing.append("kırılım yok")
        if not vm.volume_confirm: missing.append("hacim zayıf")
        if not rsi_ok:            missing.append(f"RSI={vm.rsi:.0f} aralık dışı")
        if vm.rr_ratio < 1.8:     missing.append(f"R/R={vm.rr_ratio:.1f}x düşük")

        full_reason = reason_txt
        if missing:
            full_reason += f"\n⚠ Eksik: {', '.join(missing[:3])}"

        self._decision_reason.config(text=full_reason, fg=TEXT_DIM)

        # Kriter progress barları
        for w in self._crit_frame.winfo_children():
            w.destroy()

        criteria = [
            ("Trend",    vm.trend,          True),
            ("Kırılım",  vm.breakout,       True),
            ("Hacim",    vm.volume_confirm,  True),
            ("RSI",      rsi_ok,            True),
            ("R/R",      vm.rr_ratio >= 1.8, True),
            ("Sektör",   vm.sector_strength >= 50, vm.sector_strength >= 50),
        ]
        for name, ok, _ in criteria:
            f = tk.Frame(self._crit_frame, bg=BG_CARD); f.pack(side="left", padx=2)
            col = COLOR_POSITIVE if ok else "#374151"
            tk.Label(f, text=("✓ " if ok else "✗ ") + name,
                font=("Consolas", 7),
                bg=col if ok else BG_CARD,
                fg="#000000" if ok else TEXT_DIM,
                padx=3, pady=1
            ).pack()

    # ── Teknik Özet ──────────────────────────────────────────

    def _update_technical(self, vm: SymbolDetailViewModel) -> None:
        # Sinyal göstergeleri (renkli kutucuklar)
        sig_data = {
            "trend":   (vm.trend,          "TREND"),
            "breakout":(vm.breakout,        "BREAKOUT"),
            "volume":  (vm.volume_confirm,  "HACİM"),
            "rs":      (vm.score >= 4,      "RS+"),
        }
        for key, (active, txt) in sig_data.items():
            col = COLOR_POSITIVE if active else "#374151"
            txt_col = "#000000" if active else "#6b7280"
            self._sig_labels[key].config(
                text=f"{'✓' if active else '✗'} {txt}",
                bg=col, fg=txt_col
            )

        # RSI
        rsi_val, rsi_bar = self._tech_rows["rsi"]
        rsi_ok  = 52 <= vm.rsi <= 72
        rsi_col = COLOR_POSITIVE if rsi_ok else (
                  COLOR_WARNING if vm.rsi < 52 else COLOR_NEGATIVE)
        rsi_val.config(
            text=f"{vm.rsi:.1f}  {'✓ ideal' if rsi_ok else ('▲ aşırı alım' if vm.rsi > 72 else '▼ zayıf')}",
            fg=rsi_col
        )
        self.after(50, lambda: self._bar(rsi_bar, vm.rsi / 100, rsi_col))

        # EMA
        ema_val, ema_bar = self._tech_rows["ema"]
        ema_ok  = vm.ema9 > vm.ema21
        ema_val.config(
            text=f"{vm.ema9:.1f} / {vm.ema21:.1f}  {'↑' if ema_ok else '↓'}",
            fg=COLOR_POSITIVE if ema_ok else COLOR_NEGATIVE
        )
        self.after(50, lambda: self._bar(ema_bar, 0.8 if ema_ok else 0.2,
                   COLOR_POSITIVE if ema_ok else COLOR_NEGATIVE))

        # ATR (risk birimi)
        atr_val, _ = self._tech_rows["atr"]
        atr_pct = vm.atr / vm.price * 100 if vm.price > 0 else 0
        atr_val.config(
            text=f"₺{vm.atr:.2f}  ({atr_pct:.1f}% fiyatın)",
            fg=COLOR_WARNING if atr_pct > 2.5 else TEXT_SECONDARY
        )

        # Hacim
        vol_val, vol_bar = self._tech_rows["vol"]
        vol_m  = vm.volume / 1_000_000
        vol_ok = vm.volume >= 2_000_000
        vol_val.config(
            text=f"{vol_m:.1f}M  {'✓ yeterli' if vol_ok else '✗ düşük'}",
            fg=COLOR_POSITIVE if vol_ok else COLOR_NEGATIVE
        )
        self.after(50, lambda v=min(1.0, vol_m/10): self._bar(vol_bar, v, COLOR_ACCENT))

        # RS skoru
        rs_val, rs_bar = self._tech_rows["rs_score"]
        # rs_score ViewModel'de yok — change_pct ile endeks tahmini
        rs_approx = vm.change_pct - 0.0  # basit proxy
        rs_col    = COLOR_POSITIVE if rs_approx >= 0 else COLOR_NEGATIVE
        rs_val.config(
            text=f"{rs_approx:+.2f}%  {'endeksten güçlü ↑' if rs_approx >= 0 else 'endeksten zayıf ↓'}",
            fg=rs_col
        )
        self.after(50, lambda: self._bar(rs_bar, 0.5 + rs_approx/20,
                   rs_col))

        # Sektör gücü
        sec_val, sec_bar = self._tech_rows["sec_str"]
        ss  = vm.sector_strength
        ss_col = (COLOR_POSITIVE if ss >= 60 else
                  COLOR_WARNING  if ss >= 40 else COLOR_NEGATIVE)
        ss_lbl = "güçlü" if ss >= 60 else ("orta" if ss >= 40 else "zayıf")
        sec_val.config(
            text=f"{ss:.0f}/100  {ss_lbl}  —  {vm.sector_name or '—'}",
            fg=ss_col
        )
        self.after(50, lambda: self._bar(sec_bar, ss / 100, ss_col))

        # Rejim
        reg_val, _ = self._tech_rows["regime"]
        reg_col = (COLOR_POSITIVE if "BULL" in vm.regime_effect.upper()
                   or "YÜKSELIŞ" in vm.regime_effect or "TREND" in vm.regime_effect
                   else COLOR_WARNING if "RANGE" in vm.regime_effect.upper()
                   or "YATAY" in vm.regime_effect or "NÖTR" in vm.regime_effect
                   else COLOR_NEGATIVE)
        reg_val.config(text=vm.regime_effect or "—", fg=reg_col)

    # ── Detay ────────────────────────────────────────────────

    def _update_detail(self, vm: SymbolDetailViewModel) -> None:
        # Skorlar
        ql_col = _ql_color(vm.quality_label)
        conf_col = COLOR_POSITIVE if vm.confidence >= 65 else (
                   COLOR_WARNING if vm.confidence >= 50 else COLOR_NEGATIVE)
        flow_col = COLOR_POSITIVE if vm.flow_score >= 6 else (
                   COLOR_WARNING if vm.flow_score >= 4 else TEXT_DIM)

        self._score_cells["comb"].config(
            text=f"{vm.combined_score:.1f}", fg=ql_col)
        self._score_cells["conf"].config(
            text=f"%{vm.confidence:.0f}", fg=conf_col)
        self._score_cells["flow"].config(
            text=f"{vm.flow_score:.1f}", fg=flow_col)
        self._score_cells["ai"].config(
            text=f"{vm.ai_score:.1f}", fg=COLOR_WARNING)

        # Analiz notu
        self._note_lbl.config(text=vm.technical_summary or "")

        # Uyarılar
        for w in self._alert_frame.winfo_children():
            w.destroy()
        for alert in (vm.alerts or [])[:5]:
            col = (COLOR_NEGATIVE if any(x in alert for x in ["⚠", "🚫", "🔴"])
                   else COLOR_POSITIVE if any(x in alert for x in ["✓", "💰", "🎯", "⭐"])
                   else COLOR_WARNING)
            tk.Label(self._alert_frame, text=alert,
                font=("Consolas", 7), bg=BG_CARD, fg=col,
                anchor="w").pack(fill="x", pady=1)
