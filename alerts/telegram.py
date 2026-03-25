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
        emoji = "🔵" if "CORE" in str(sig.setup_type) else "🟣"
        shield = "🛡" if "CORE" in str(sig.setup_type) else "⚡"
        weight_pct = int(sig.weight * 100)
        self.send(
            f"{emoji} <b>BIST EDGE YENİ SİNYAL</b> {emoji}\n"
            f"────────────────────\n"
            f"📌 <b>Hisse:</b> #{sig.symbol}\n"
            f"{shield} <b>Strateji:</b> {sig.setup_type} (Sermaye: %{weight_pct})\n\n"
            f"📉 <b>Giriş Fiyatı:</b> ₺{sig.entry:.2f}\n"
            f"🛑 <b>Zarar Kes:</b> ₺{sig.stop:.2f}\n"
            f"🎯 <b>Kar Al Hedefi:</b> ₺{sig.target:.2f}\n\n"
            f"⚖️ <b>Risk/Ödül:</b> {sig.rr_ratio:.1f}x\n"
            f"📊 <b>RS Puanı:</b> {sig.rs_score:.2f}\n\n"
            f"📝 <b>Analiz Notu:</b>\n"
            f"<i>{getattr(sig, 'detail', '')}</i>\n\n"
            f"⏱ <b>Zaman:</b> {datetime.now().strftime('%H:%M:%S')}"
        )

    def send_watch(self, sig):
        state_val = sig.state.value if hasattr(sig.state, 'value') else sig.state
        self.send(
            f"👁 <b>İZLEMEYE ALINDI</b> 👁\n"
            f"────────────────────\n"
            f"📌 <b>Hisse:</b> #{sig.symbol}\n"
            f"🔎 <b>Durum:</b> {state_val}\n"
            f"🛡 <b>Strateji:</b> {sig.setup_type}\n\n"
            f"💵 <b>Fiyat:</b> ₺{sig.entry:.2f}\n"
            f"📊 <b>RS Puanı:</b> {sig.rs_score:.2f}\n\n"
            f"📝 <b>İzleme Sebebi:</b>\n<i>{getattr(sig, 'detail', '')}</i>\n\n"
            f"⏱ <b>Zaman:</b> {datetime.now().strftime('%H:%M:%S')}"
        )

    def send_sell(self, symbol: str, reason: str):
        self.send(
            f"⚠️ <b>SAT SİNYALİ YAKALANDI</b> ⚠️\n"
            f"────────────────────\n"
            f"📌 <b>Hisse:</b> #{symbol}\n"
            f"🛑 <b>Neden:</b> {reason}\n\n"
            f"⏱ <b>Sinyal Zamanı:</b> {datetime.now().strftime('%H:%M:%S')}"
        )
