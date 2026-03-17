# ============================================================
# ui/panels/position_panel.py
# Açık Pozisyonlar Yönetim Paneli
#
# Kolonlar: Hisse | Giriş | Anlık | Lot | Stop | Hedef | PnL% | PnL TL | Durum
# Aksiyonlar: Sat | Stop güncelle | Target güncelle
# ============================================================
import tkinter as tk
from tkinter import ttk, simpledialog
from typing import Callable, Optional
from ui.theme import *


class PositionPanel(tk.Frame):
    """Açık pozisyonları ve SELL sinyallerini gösteren panel."""

    COLS = [
        ("Hisse",   60),  ("Giriş",   70),  ("Anlık",   70),
        ("Lot",     45),  ("Stop",    70),   ("Hedef",   70),
        ("PnL%",    60),  ("PnL TL",  75),   ("Durum",   90),
    ]

    def __init__(
        self,
        parent,
        signal_engine,     # TradeSignalEngine
        on_sell:   Optional[Callable] = None,
        **kwargs
    ):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self._engine   = signal_engine
        self._on_sell  = on_sell
        self._positions = []
        self._build()

    def _build(self):
        # Başlık
        hdr = tk.Frame(self, bg=PANEL_TITLE_BG, pady=4); hdr.pack(fill="x")
        tk.Label(hdr, text="◈  AÇIK POZİSYONLAR",
                 font=FONT_TITLE, bg=PANEL_TITLE_BG, fg=PANEL_TITLE_FG).pack(side="left", padx=10)
        self._pnl_lbl = tk.Label(hdr, text="", font=FONT_SMALL,
                                  bg=PANEL_TITLE_BG, fg=TEXT_SECONDARY)
        self._pnl_lbl.pack(side="right", padx=10)

        # Treeview
        style = ttk.Style()
        style.configure("Pos.Treeview",
            background=TABLE_ROW_EVEN, foreground=TEXT_PRIMARY,
            fieldbackground=TABLE_ROW_EVEN, rowheight=22,
            font=FONT_SMALL, borderwidth=0)
        style.configure("Pos.Treeview.Heading",
            background=BG_HEADER, foreground=COLOR_ACCENT,
            font=FONT_HEADER, relief="flat")
        style.map("Pos.Treeview",
            background=[("selected", TABLE_SELECT)],
            foreground=[("selected", TEXT_PRIMARY)])

        cols = [c[0] for c in self.COLS]
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   style="Pos.Treeview", height=8)
        for col, width in self.COLS:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=width, anchor="center", stretch=False)

        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Aksiyon butonları
        btn_f = tk.Frame(self, bg=BG_PANEL, pady=4)
        btn_f.pack(fill="x", padx=8)

        def btn(txt, cmd, color=BG_HEADER):
            b = tk.Button(btn_f, text=txt, command=cmd,
                          font=("Consolas", 8), bg=color, fg=TEXT_PRIMARY,
                          relief="flat", cursor="hand2", padx=8)
            b.pack(side="left", padx=4)
            return b

        btn("💰 Sat", self._do_sell, color="#7f1d1d")
        btn("🔄 Stop Güncelle", self._do_update_stop)
        btn("🎯 Target Güncelle", self._do_update_target)

    def update(self) -> None:
        """Engine'den pozisyonları al ve göster."""
        positions   = self._engine.get_positions()
        sell_signals = self._engine.get_sell_signals()
        all_pos = positions + sell_signals
        self._positions = all_pos

        for row in self._tree.get_children():
            self._tree.delete(row)

        total_pnl = 0.0
        for i, sig in enumerate(all_pos):
            pnl_pct = sig.pnl_pct
            pnl_tl  = sig.pnl_tl
            total_pnl += pnl_tl

            pnl_col_tag = "pos" if pnl_pct >= 0 else "neg"
            state_txt   = "⚠ SAT" if sig.state.value == "SELL_SIGNAL" else "✓ Açık"
            state_tag   = "sell" if sig.state.value == "SELL_SIGNAL" else "open"

            stop   = sig.stop_updated   if sig.stop_updated   else sig.stop
            target = sig.target_updated if sig.target_updated else sig.target

            tag = f"row_{i}_{state_tag}_{pnl_col_tag}"
            self._tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                sig.symbol,
                f"₺{sig.entry_filled:.2f}" if sig.entry_filled else f"₺{sig.entry:.2f}",
                f"₺{sig.last_price:.2f}",
                sig.lots if sig.lots else "—",
                f"₺{stop:.2f}",
                f"₺{target:.2f}",
                f"{pnl_pct:+.2f}%",
                f"₺{pnl_tl:+.0f}",
                state_txt,
            ))

            row_bg = TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN
            pnl_fg = COLOR_POSITIVE if pnl_pct >= 0 else COLOR_NEGATIVE
            sel_bg = "#7f1d1d" if sig.state.value == "SELL_SIGNAL" else TABLE_SELECT

            self._tree.tag_configure(tag,
                foreground=pnl_fg,
                background=row_bg)

        # Özet
        count = len(all_pos)
        if count:
            pnl_col = COLOR_POSITIVE if total_pnl >= 0 else COLOR_NEGATIVE
            self._pnl_lbl.config(
                text=f"{count} pozisyon  |  Toplam: ₺{total_pnl:+.0f}",
                fg=pnl_col
            )
        else:
            self._pnl_lbl.config(text="Açık pozisyon yok", fg=TEXT_DIM)

    def _selected_signal(self):
        sel = self._tree.selection()
        if not sel:
            return None
        idx = int(sel[0])
        if idx < len(self._positions):
            return self._positions[idx]
        return None

    def _do_sell(self):
        sig = self._selected_signal()
        if not sig:
            return
        self._engine.mark_position_closed(sig.symbol)
        if self._on_sell:
            self._on_sell(sig.symbol)
        self.update()

    def _do_update_stop(self):
        sig = self._selected_signal()
        if not sig:
            return
        current = sig.stop_updated if sig.stop_updated else sig.stop
        val = simpledialog.askfloat(
            "Stop Güncelle",
            f"{sig.symbol} için yeni stop seviyesi (mevcut: ₺{current:.2f}):",
            minvalue=0.01
        )
        if val:
            self._engine.update_levels(sig.symbol, stop=val)
            self.update()

    def _do_update_target(self):
        sig = self._selected_signal()
        if not sig:
            return
        current = sig.target_updated if sig.target_updated else sig.target
        val = simpledialog.askfloat(
            "Target Güncelle",
            f"{sig.symbol} için yeni hedef fiyatı (mevcut: ₺{current:.2f}):",
            minvalue=0.01
        )
        if val:
            self._engine.update_levels(sig.symbol, target=val)
            self.update()
