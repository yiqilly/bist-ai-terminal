# ============================================================
# strategy/liquidity.py — Likidite / Execution Quality
# ============================================================
from data.models import SignalCandidate, LiquidityAnalysis


class LiquidityAnalyzer:
    """
    Her hisse için işlem uygulanabilirliği değerlendirir.
    Spread proxy, hacim kalitesi, fiyat seviyesi hesaplar.
    """

    def analyze(self, candidate: SignalCandidate) -> LiquidityAnalysis:
        c = candidate

        # Hacim seviyesi
        if c.volume >= 4_000_000:
            vol_score = 1.0; vol_label = "Yüksek"
        elif c.volume >= 2_000_000:
            vol_score = 0.7; vol_label = "Orta"
        elif c.volume >= 800_000:
            vol_score = 0.4; vol_label = "Düşük"
        else:
            vol_score = 0.1; vol_label = "Çok Düşük"

        # Spread proxy: ATR / price * 100 → düşük = iyi
        spread_proxy = c.atr / (c.price + 0.001) * 100
        if spread_proxy < 1.0:
            spread_q = 1.0
        elif spread_proxy < 2.0:
            spread_q = 0.7
        elif spread_proxy < 3.5:
            spread_q = 0.4
        else:
            spread_q = 0.2

        # Fiyat seviyesi (çok düşük fiyat = yüksek spread etkisi)
        price_q = 1.0 if c.price >= 10 else (0.6 if c.price >= 3 else 0.3)

        # Uygulanabilir max lot (yaklaşık)
        lot_feasibility = max(1, int(c.volume / (c.price * 500 + 1)))
        lot_feasibility = min(lot_feasibility, 50_000)

        # Birleşik skor
        liq = (vol_score * 0.50 + spread_q * 0.30 + price_q * 0.20)
        liq_score = round(liq * 10, 2)

        if liq_score >= 7:
            exec_q = "İyi"
        elif liq_score >= 4:
            exec_q = "Orta"
        else:
            exec_q = "Kötü"

        return LiquidityAnalysis(
            symbol=c.symbol,
            liquidity_score=liq_score,
            volume_level=vol_label,
            spread_quality=round(spread_q, 3),
            execution_quality=exec_q,
            lot_feasibility=lot_feasibility,
        )
