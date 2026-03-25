# ============================================================
# alerts/telegram.py — Telegram Bildirim Gönderici
# ============================================================
import json
import logging
import threading
import requests
from datetime import datetime

from config import CAPITAL_TL, MAX_POSITIONS, RISK_PER_TRADE_PCT

logger = logging.getLogger(__name__)


def _calc_quantity(entry: float, stop: float) -> int:
    """Risk yönetimine göre lot hesapla."""
    if entry <= 0 or stop <= 0 or entry <= stop:
        return 0
    risk_per_trade = CAPITAL_TL * (RISK_PER_TRADE_PCT / 100)
    stop_distance  = entry - stop
    qty = int(risk_per_trade / stop_distance)
    return max(qty, 1)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token    = token
        self.chat_id  = chat_id
        self.enabled  = bool(token and chat_id)
        # Onay bekleyen sinyaller: {callback_data: sig}
        self._pending: dict = {}

        if self.enabled:
            logger.info("Telegram aktif.")
            # Onay callback'lerini dinle
            t = threading.Thread(target=self._poll_loop, daemon=True, name="tg-poll")
            t.start()

    # ── Temel Gönderici ───────────────────────────────────────

    def send(self, text: str, reply_markup: dict = None):
        if not self.enabled:
            return None
        payload = {
            "chat_id":    self.chat_id,
            "text":       text,
            "parse_mode": "HTML",
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json=payload,
                timeout=5,
            )
            r.raise_for_status()
            return r.json().get("result", {}).get("message_id")
        except Exception as e:
            logger.error(f"Telegram hatası: {e}")
            return None

    def answer_callback(self, callback_query_id: str, text: str = ""):
        """Buton tıklamasını onayla (Telegram'daki spinner'ı kapat)."""
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
                timeout=5,
            )
        except Exception:
            pass

    def edit_message(self, message_id: int, text: str):
        """Mesajı güncelle (butonları kaldır, durumu göster)."""
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/editMessageText",
                json={
                    "chat_id":    self.chat_id,
                    "message_id": message_id,
                    "text":       text,
                    "parse_mode": "HTML",
                },
                timeout=5,
            )
        except Exception:
            pass

    # ── AL Sinyali (butonlu) ──────────────────────────────────

    def send_buy(self, sig):
        qty        = _calc_quantity(sig.entry, sig.stop)
        risk_tl    = qty * (sig.entry - sig.stop)
        stop_pct   = (sig.stop   - sig.entry) / sig.entry * 100
        target_pct = (sig.target - sig.entry) / sig.entry * 100

        callback_ok  = f"BUY_OK_{sig.symbol}"
        callback_no  = f"BUY_NO_{sig.symbol}"

        text = (
            f"🔵 <b>AL SİNYALİ: #{sig.symbol}</b>\n"
            f"────────────────────\n"
            f"💵 <b>Giriş  :</b> ₺{sig.entry:.2f}\n"
            f"🛑 <b>Stop   :</b> ₺{sig.stop:.2f}  ({stop_pct:.1f}%)\n"
            f"🎯 <b>Hedef  :</b> ₺{sig.target:.2f}  ({target_pct:+.1f}%)\n"
            f"📦 <b>Adet   :</b> {qty} lot\n"
            f"⚖️ <b>R/R    :</b> {sig.rr_ratio:.1f}x\n"
            f"📊 <b>RS     :</b> {sig.rs_score:.2f}\n"
            f"💸 <b>Risk   :</b> ₺{risk_tl:,.0f}\n\n"
            f"<i>{getattr(sig, 'detail', '')}</i>\n"
            f"⏱ {datetime.now().strftime('%H:%M:%S')}"
        )

        markup = {"inline_keyboard": [[
            {"text": "✅ TAKIBE AL", "callback_data": callback_ok},
            {"text": "❌ GEÇ",       "callback_data": callback_no},
        ]]}

        msg_id = self.send(text, reply_markup=markup)

        if msg_id:
            self._pending[callback_ok] = {
                "sig": sig, "qty": qty, "msg_id": msg_id,
                "action": "buy", "symbol": sig.symbol,
            }
            self._pending[callback_no] = {
                "msg_id": msg_id, "action": "skip", "symbol": sig.symbol,
            }

    # ── İzleme Bildirimi ─────────────────────────────────────

    def send_watch(self, sig):
        state_val = sig.state.value if hasattr(sig.state, 'value') else sig.state
        self.send(
            f"👁 <b>İZLEMEYE ALINDI: #{sig.symbol}</b>\n"
            f"────────────────────\n"
            f"🔎 <b>Durum :</b> {state_val}\n"
            f"📊 <b>RS    :</b> {sig.rs_score:.2f}\n\n"
            f"<i>{getattr(sig, 'detail', '')}</i>\n"
            f"⏱ {datetime.now().strftime('%H:%M:%S')}"
        )

    # ── Sat Bildirimi ─────────────────────────────────────────

    def send_sell(self, symbol: str, reason: str):
        self.send(
            f"🔴 <b>ÇIKIŞ: #{symbol}</b>\n"
            f"────────────────────\n"
            f"🛑 <b>Neden :</b> {reason}\n"
            f"⏱ {datetime.now().strftime('%H:%M:%S')}"
        )

    # ── Callback Polling ──────────────────────────────────────

    _last_update_id = 0

    def _poll_loop(self):
        """Buton tıklamalarını dinle (getUpdates long-polling)."""
        while True:
            try:
                r = requests.get(
                    f"https://api.telegram.org/bot{self.token}/getUpdates",
                    params={"offset": self._last_update_id + 1, "timeout": 30},
                    timeout=35,
                )
                updates = r.json().get("result", [])
                for upd in updates:
                    self._last_update_id = upd["update_id"]
                    cq = upd.get("callback_query")
                    if cq:
                        self._handle_callback(cq)
            except Exception as e:
                logger.debug(f"Telegram poll hatasi: {e}")
                import time; time.sleep(5)

    def _handle_callback(self, cq: dict):
        data    = cq.get("data", "")
        cq_id   = cq["id"]
        pending = self._pending.pop(data, None)

        if pending is None:
            self.answer_callback(cq_id, "⚠️ Süresi dolmuş")
            return

        msg_id = pending["msg_id"]
        symbol = pending["symbol"]

        if pending["action"] == "buy":
            sig = pending["sig"]
            qty = pending["qty"]
            self.answer_callback(cq_id, "✅ Takibe alındı!")
            self.edit_message(
                msg_id,
                f"✅ <b>TAKİBE ALINDI: #{symbol}</b>\n"
                f"💵 Giriş: ₺{sig.entry:.2f} | Adet: {qty} lot\n"
                f"🛑 Stop: ₺{sig.stop:.2f} | 🎯 Hedef: ₺{sig.target:.2f}\n"
                f"⏱ {datetime.now().strftime('%H:%M:%S')}"
            )
            logger.info(f"Telegram onaylandi: {symbol} {qty} lot @ {sig.entry}")

        elif pending["action"] == "skip":
            # Karşı callback'i de temizle
            other = data.replace("BUY_NO_", "BUY_OK_") if "NO" in data else data.replace("BUY_OK_", "BUY_NO_")
            self._pending.pop(other, None)
            self.answer_callback(cq_id, "❌ Geçildi")
            self.edit_message(
                msg_id,
                f"❌ <b>GEÇİLDİ: #{symbol}</b>\n"
                f"⏱ {datetime.now().strftime('%H:%M:%S')}"
            )
