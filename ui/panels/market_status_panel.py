# ============================================================
# ui/panels/market_status_panel.py
# Bağlantı / Veri Kaynağı Durum Göstergesi
#
# Top bar'da küçük bir widget:
#   ● REALTIME  |  BIST30: 28/30  |  Son: 12:45:03  |  borsapy
# ============================================================
import tkinter as tk
from datetime import datetime
from ui.theme import *
from config import UNIVERSE


class MarketStatusBar(tk.Frame):
    """
    Üst bara eklenen gerçek zamanlı bağlantı durumu göstergesi.
    market_bus referansıyla güncellenir.
    """

    def __init__(self, parent, market_bus, **kwargs):
        super().__init__(parent, bg=BG_HEADER, **kwargs)
        self._bus = market_bus
        self._build()

    def _build(self):
        # Bağlantı noktası
        self._dot = tk.Label(self, text="●", font=FONT_SMALL,
                              bg=BG_HEADER, fg=COLOR_WARNING)
        self._dot.pack(side="left", padx=(0, 2))

        self._status = tk.Label(self, text="BAĞLANIYOR",
                                 font=FONT_SMALL, bg=BG_HEADER, fg=COLOR_WARNING)
        self._status.pack(side="left", padx=(0, 8))

        tk.Label(self, text="|", font=FONT_SMALL,
                 bg=BG_HEADER, fg=TEXT_DIM).pack(side="left", padx=2)

        self._symbols_lbl = tk.Label(self, text=f"{UNIVERSE}: —",
                                      font=FONT_SMALL, bg=BG_HEADER, fg=TEXT_SECONDARY)
        self._symbols_lbl.pack(side="left", padx=(4, 8))

        tk.Label(self, text="|", font=FONT_SMALL,
                 bg=BG_HEADER, fg=TEXT_DIM).pack(side="left", padx=2)

        self._update_lbl = tk.Label(self, text="Son: —",
                                     font=FONT_SMALL, bg=BG_HEADER, fg=TEXT_SECONDARY)
        self._update_lbl.pack(side="left", padx=(4, 8))

        tk.Label(self, text="|", font=FONT_SMALL,
                 bg=BG_HEADER, fg=TEXT_DIM).pack(side="left", padx=2)

        self._source_lbl = tk.Label(self, text="—",
                                     font=("Consolas", 8, "bold"),
                                     bg=BG_HEADER, fg=COLOR_ACCENT)
        self._source_lbl.pack(side="left", padx=4)

    def refresh(self, snapshot=None):
        """Her update döngüsünde çağrılır."""
        connected = self._bus.is_connected
        source    = self._bus.source_label

        # Renk ve metin
        if connected:
            dot_color  = COLOR_POSITIVE
            status_txt = "CANLI"
            status_col = COLOR_POSITIVE
        else:
            dot_color  = COLOR_NEGATIVE
            status_txt = "KESİLDİ"
            status_col = COLOR_NEGATIVE

        self._dot.config(fg=dot_color)
        self._status.config(text=status_txt, fg=status_col)
        self._source_lbl.config(text=source.upper())

        # Sembol sayısı
        if snapshot:
            n = len(snapshot.ticks)
            # Find the total size based on UNIVERSE
            total = 30 if UNIVERSE == "BIST30" else (50 if UNIVERSE == "BIST50" else 100)
            self._symbols_lbl.config(text=f"{UNIVERSE}: {n}/{total}")

        # Son güncelleme
        try:
            lu = self._bus.last_update
            age = (datetime.now() - lu).total_seconds()
            if age < 5:
                age_col = COLOR_POSITIVE
            elif age < 15:
                age_col = COLOR_WARNING
            else:
                age_col = COLOR_NEGATIVE
            self._update_lbl.config(
                text=f"Son: {lu.strftime('%H:%M:%S')}",
                fg=age_col
            )
        except Exception:
            pass
