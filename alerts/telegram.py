# ============================================================
# alerts/telegram.py — Telegram Bildirim Gönderici
# ============================================================
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token   = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)
        if self.enabled:
            logger.info("Telegram aktif.")

    def send(self, text: str):
        if not self.enabled:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                timeout=5,
            ).raise_for_status()
        except Exception as e:
            logger.error(f"Telegram hatası: {e}")

    def send_buy(self, sig):
        emoji = "🚀" if sig.setup_type == "CORE_EDGE" else "⚡"
        weight_pct = int(sig.weight * 100)
        self.send(
            f"{emoji} <b>AL SİNYALİ — {sig.symbol}</b>\n\n"
            f"<b>Strateji:</b> {sig.setup_type} (%{weight_pct} ağırlık)\n"
            f"<b>Giriş:</b> ₺{sig.entry:.2f}\n"
            f"<b>Stop:</b> ₺{sig.stop:.2f}\n"
            f"<b>Hedef:</b> ₺{sig.target:.2f}\n"
            f"<b>R/R:</b> {sig.rr_ratio:.1f}x\n"
            f"<b>Detay:</b> {sig.detail}\n"
            f"<b>Zaman:</b> {datetime.now().strftime('%H:%M:%S')}"
        )

    def send_sell(self, symbol: str, reason: str):
        self.send(
            f"⚠️ <b>SAT SİNYALİ — {symbol}</b>\n\n"
            f"<b>Neden:</b> {reason}\n"
            f"<b>Zaman:</b> {datetime.now().strftime('%H:%M:%S')}"
        )
