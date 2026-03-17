# ============================================================
# ui/panels/buy_signal_popup.py
# BUY / SELL Sinyal Popup Bildirimi
#
# BUY_SIGNAL oluştuğunda:
#   - Popup pencere açılır
#   - Sesli uyarı (sistem zili)
#   - [Aldım] [İzle] [Kapat] butonları
#
# SELL_SIGNAL oluştuğunda:
#   - Kırmızı popup
#   - [Sattım] [Beklet] [Kapat] butonları
# ============================================================
import tkinter as tk
from typing import Callable, Optional
from ui.theme import *


class BuySignalPopup(tk.Toplevel):
    """
    BUY sinyali popup penceresi.
    Sinyal kaydı gösterir, kullanıcı aksiyonu alır.
    """

    def __init__(
        self,
        parent,
        signal,            # TradeSignal
        on_buy:  Callable,   # (symbol, price, lots) → None
        on_watch: Callable,  # (symbol) → None
        on_close: Callable,  # () → None
    ):
        super().__init__(parent)
        self._signal   = signal
        self._on_buy   = on_buy
        self._on_watch = on_watch
        self._on_close = on_close

        self.title(f"🚀 AL SİNYALİ — {signal.symbol}")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)
        self.attributes("-topmost", True)   # her zaman üstte

        # Ekran ortasına konumlandır
        self.update_idletasks()
        w, h = 420, 380
        x = parent.winfo_x() + (parent.winfo_width()  - w) // 2
        y = parent.winfo_y() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._build()
        self._play_sound()

        # 60 saniye sonra otomatik kapat
        self.after(60000, self._auto_close)

    def _build(self):
        sig = self._signal

        # Başlık
        hdr = tk.Frame(self, bg=COLOR_POSITIVE, pady=8)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text=f"🚀  AL SİNYALİ  —  {sig.symbol}",
            font=("Consolas", 13, "bold"),
            bg=COLOR_POSITIVE, fg="#000000"
        ).pack()

        # Kalite etiketi
        ql_bg = {"A+": "#059669", "A": "#10b981", "B": "#d97706"}.get(
            sig.quality_label, "#374151"
        )
        tk.Label(
            hdr, text=f"  {sig.quality_label}  ",
            font=("Consolas", 9, "bold"),
            bg=ql_bg, fg="white"
        ).pack(pady=(2, 0))

        # Fiyat bilgisi
        body = tk.Frame(self, bg=BG_DARK, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        def row(label, value, val_color=TEXT_PRIMARY):
            f = tk.Frame(body, bg=BG_DARK); f.pack(fill="x", pady=2)
            tk.Label(f, text=label, font=FONT_SMALL,
                     bg=BG_DARK, fg=TEXT_DIM, width=14, anchor="w").pack(side="left")
            tk.Label(f, text=value, font=("Consolas", 10, "bold"),
                     bg=BG_DARK, fg=val_color).pack(side="left")

        row("Hisse",     sig.symbol,          COLOR_ACCENT)
        row("Giriş",     f"₺{sig.entry:.2f}", TEXT_PRIMARY)
        row("Stop",      f"₺{sig.stop:.2f}",  COLOR_NEGATIVE)
        row("Hedef",     f"₺{sig.target:.2f}", COLOR_POSITIVE)
        row("R/R",       f"{sig.rr_ratio:.2f}x",
            COLOR_POSITIVE if sig.rr_ratio >= 2 else COLOR_WARNING)
        row("Güven",     f"%{sig.confidence:.0f}",
            COLOR_POSITIVE if sig.confidence >= 65 else COLOR_WARNING)
        row("Sektör",    f"{sig.sector_name} ({sig.sector_strength:.0f})",
            TEXT_SECONDARY)
        row("Sebep",     sig.reason[:40] if sig.reason else "—", TEXT_SECONDARY)

        # Ayırıcı
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=8)

        # Lot girişi
        lot_f = tk.Frame(body, bg=BG_DARK); lot_f.pack(fill="x", pady=4)
        tk.Label(lot_f, text="Lot Miktarı:", font=FONT_SMALL,
                 bg=BG_DARK, fg=TEXT_DIM, width=14, anchor="w").pack(side="left")
        self._lot_var = tk.StringVar(value="100")
        lot_entry = tk.Entry(lot_f, textvariable=self._lot_var,
                             font=("Consolas", 10), bg=BG_HEADER,
                             fg=TEXT_PRIMARY, insertbackground=COLOR_ACCENT,
                             width=8, relief="flat")
        lot_entry.pack(side="left", padx=4)

        # Butonlar
        btn_f = tk.Frame(self, bg=BG_DARK, pady=10); btn_f.pack(fill="x", padx=16)

        tk.Button(
            btn_f, text="✅  ALDIM",
            font=("Consolas", 10, "bold"),
            bg=COLOR_POSITIVE, fg="#000000", relief="flat",
            activebackground="#16a34a",
            cursor="hand2",
            command=self._on_buy_click
        ).pack(side="left", padx=4, fill="x", expand=True)

        tk.Button(
            btn_f, text="👁  İZLE",
            font=("Consolas", 10),
            bg=BG_HEADER, fg=TEXT_SECONDARY, relief="flat",
            cursor="hand2",
            command=self._on_watch_click
        ).pack(side="left", padx=4, fill="x", expand=True)

        tk.Button(
            btn_f, text="✕  KAPAT",
            font=("Consolas", 10),
            bg=BG_DARK, fg=TEXT_DIM, relief="flat",
            cursor="hand2",
            command=self._on_close_click
        ).pack(side="left", padx=4, fill="x", expand=True)

    def _on_buy_click(self):
        try:
            lots = int(self._lot_var.get())
        except ValueError:
            lots = 100
        self._on_buy(self._signal.symbol, self._signal.entry, lots)
        self.destroy()

    def _on_watch_click(self):
        self._on_watch(self._signal.symbol)
        self.destroy()

    def _on_close_click(self):
        self._on_close()
        self.destroy()

    def _auto_close(self):
        try:
            self.destroy()
        except Exception:
            pass

    def _play_sound(self):
        """Sistem uyarı sesi."""
        try:
            self.bell()
        except Exception:
            pass


class SellSignalPopup(tk.Toplevel):
    """
    SELL sinyali popup penceresi.
    """

    def __init__(
        self,
        parent,
        signal,
        on_sell:  Callable,
        on_wait:  Callable,
        on_close: Callable,
    ):
        super().__init__(parent)
        self._signal   = signal
        self._on_sell  = on_sell
        self._on_wait  = on_wait
        self._on_close = on_close

        self.title(f"⚠ SAT SİNYALİ — {signal.symbol}")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self.update_idletasks()
        w, h = 380, 300
        x = parent.winfo_x() + (parent.winfo_width()  - w) // 2
        y = parent.winfo_y() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._build()
        self._play_sound()
        self.after(90000, self._auto_close)

    def _build(self):
        sig = self._signal

        hdr = tk.Frame(self, bg=COLOR_NEGATIVE, pady=8); hdr.pack(fill="x")
        tk.Label(
            hdr, text=f"⚠  SAT SİNYALİ  —  {sig.symbol}",
            font=("Consolas", 13, "bold"),
            bg=COLOR_NEGATIVE, fg="white"
        ).pack()

        body = tk.Frame(self, bg=BG_DARK, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        def row(label, value, val_color=TEXT_PRIMARY):
            f = tk.Frame(body, bg=BG_DARK); f.pack(fill="x", pady=3)
            tk.Label(f, text=label, font=FONT_SMALL,
                     bg=BG_DARK, fg=TEXT_DIM, width=14, anchor="w").pack(side="left")
            tk.Label(f, text=value, font=("Consolas", 10, "bold"),
                     bg=BG_DARK, fg=val_color).pack(side="left")

        pnl_col = COLOR_POSITIVE if sig.pnl_pct >= 0 else COLOR_NEGATIVE
        row("Hisse",     sig.symbol,          COLOR_ACCENT)
        row("Giriş",     f"₺{sig.entry_filled:.2f}" if sig.entry_filled else "—")
        row("Anlık",     f"₺{sig.last_price:.2f}",  pnl_col)
        row("PnL %",     f"{sig.pnl_pct:+.2f}%",    pnl_col)
        row("PnL TL",    f"₺{sig.pnl_tl:+.0f}",     pnl_col)
        row("Sebep",     sig.reason[:50] if sig.reason else "—", COLOR_WARNING)

        btn_f = tk.Frame(self, bg=BG_DARK, pady=10); btn_f.pack(fill="x", padx=16)

        tk.Button(
            btn_f, text="💰  SATTIM",
            font=("Consolas", 10, "bold"),
            bg=COLOR_NEGATIVE, fg="white", relief="flat",
            cursor="hand2",
            command=lambda: [self._on_sell(sig.symbol), self.destroy()]
        ).pack(side="left", padx=4, fill="x", expand=True)

        tk.Button(
            btn_f, text="⏳  BEKLET",
            font=("Consolas", 10),
            bg=BG_HEADER, fg=TEXT_SECONDARY, relief="flat",
            cursor="hand2",
            command=lambda: [self._on_wait(sig.symbol), self.destroy()]
        ).pack(side="left", padx=4, fill="x", expand=True)

        tk.Button(
            btn_f, text="✕  KAPAT",
            font=("Consolas", 10),
            bg=BG_DARK, fg=TEXT_DIM, relief="flat",
            cursor="hand2",
            command=self._on_close_click
        ).pack(side="left", padx=4, fill="x", expand=True)

    def _on_close_click(self):
        self._on_close(); self.destroy()

    def _auto_close(self):
        try: self.destroy()
        except Exception: pass

    def _play_sound(self):
        try: self.bell()
        except Exception: pass
