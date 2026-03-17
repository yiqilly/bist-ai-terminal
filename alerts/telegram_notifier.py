# ============================================================
# alerts/telegram_notifier.py
# Telegram Bildirim Sistemi
# ============================================================
import requests
import logging
from datetime import datetime
from signals.notification_store import NotificationCenter, Notification

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """
    NotificationCenter'ı dinler ve yeni bildirimleri Telegram'a iletir.
    """
    def __init__(self, token: str, chat_id: str = None):
        self.token = token
        self.chat_id = chat_id
        self._is_enabled = False
        
        if token and chat_id:
            self._is_enabled = True
            logger.info("Telegram Notifier aktif edildi.")

    def send_message(self, text: str):
        if not self._is_enabled or not self.chat_id:
            return
            
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        try:
            resp = requests.post(url, json=payload, timeout=5)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram mesajı gönderilemedi: {e}")

    def on_notification(self, n: Notification):
        """NotificationCenter'dan gelen her bildirimi formatlayıp gönderir."""
        if not self._is_enabled:
            return
            
        # Sadece BUY, SELL ve önemli ALERT'leri gönder (Haber kalabalığı yapmasın diye)
        if n.type not in ["BUY", "SELL", "ALERT"]:
            return
            
        emoji = "🚀" if n.type == "BUY" else "⚠️" if n.type == "SELL" else "🔔"
        
        msg = (
            f"{emoji} <b>BIST TERMINAL BİLDİRİMİ</b>\n\n"
            f"<b>Tip:</b> {n.type}\n"
            f"<b>Hisse:</b> #{n.symbol}\n"
            f"<b>Mesaj:</b> {n.message}\n"
            f"<b>Detay:</b> {n.detail or 'Yok'}\n"
            f"<b>Zaman:</b> {n.ts.strftime('%H:%M:%S')}\n"
        )
        self.send_message(msg)

    def bind(self, center: NotificationCenter):
        """Merkezi bildirim deposuna bağlanır."""
        center.on_new(self.on_notification)
        logger.info("Telegram Notifier NotificationCenter'a bağlandı.")
