# ============================================================
# strategy/smart_money.py — Smart Money / Flow Proxy Analizi
# ============================================================
import random
from data.models import SignalCandidate, SmartMoneyAnalysis


_LABELS = {
    (8, 10): "Güçlü kurumsal ilgi sinyali",
    (6,  8): "Hacim destekli yukarı hareket",
    (4,  6): "Orta düzey akış, teyit bekleniyor",
    (2,  4): "Kırılım zayıf, teyit yetersiz",
    (0,  2): "Para girişi zayıf, dikkatli ol",
}


class SmartMoneyAnalyzer:
    """
    Gerçek order-flow olmadan proxy feature'lardan
    'akıllı para' giriş skoru türetir.
    """

    def analyze(self, candidate: SignalCandidate) -> SmartMoneyAnalysis:
        c = candidate

        # 1. Volume surge ratio (volume / ortalama baz)
        avg_vol = 2_500_000
        vsr = min(c.volume / avg_vol, 3.0) / 3.0  # 0-1

        # 2. Bar range expansion (ATR'ye göre son hareket)
        price_range = abs(c.price - c.prev_price) if c.prev_price > 0 else 0
        atr_norm = min(price_range / (c.atr + 0.001), 2.0) / 2.0  # 0-1

        # 3. Close quality (fiyat EMA9'un üzerinde mi?)
        close_q = 1.0 if c.price > c.ema9 else 0.3

        # 4. Breakout follow-through
        bf = 1.0 if (c.breakout and c.trend) else (0.5 if c.breakout else 0.1)

        # 5. ATR normalized move (momentum / atr)
        atr_move = min(abs(c.momentum) / (c.atr * 0.5 + 0.001), 2.0) / 2.0
        atr_move *= (1.0 if c.momentum > 0 else 0.3)

        # 6. Relative momentum
        rel_mom = min(max((c.momentum + 5) / 10, 0), 1.0)

        # Ağırlıklı skor
        flow = (
            vsr    * 0.25 +
            atr_norm * 0.20 +
            close_q  * 0.15 +
            bf       * 0.20 +
            atr_move * 0.10 +
            rel_mom  * 0.10
        )
        flow_score = round(flow * 10, 2)

        label = next(
            (v for (lo, hi), v in _LABELS.items() if lo <= flow_score < hi),
            "Veri yetersiz"
        )

        return SmartMoneyAnalysis(
            symbol=c.symbol,
            flow_score=flow_score,
            volume_surge_ratio=round(vsr, 3),
            bar_range_expansion=round(atr_norm, 3),
            close_quality=round(close_q, 3),
            breakout_follow=round(bf, 3),
            atr_norm_move=round(atr_move, 3),
            label=label,
        )
