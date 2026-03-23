# ============================================================
# news/sentiment.py — Haber Sentiment Skoru
# ============================================================
from data.models import NewsItem
import math


class SentimentScorer:
    """
    Bir hissenin haberlerinden sayısal sentiment skoru üretir.
    Gerçek NLP / API entegrasyonu için bu sınıf genişletilebilir.
    """

    def score_for_symbol(self, symbol: str, news_items: list[NewsItem]) -> float:
        """
        -1.0 ile +1.0 arası birleşik sentiment skoru.
        Taze haberler daha ağırlıklı sayılır.
        """
        relevant = [n for n in news_items if n.symbol == symbol]
        if not relevant:
            return 0.0

        weighted_sum = 0.0
        weight_total = 0.0
        for item in relevant:
            age_min = item.age_minutes
            # Taze haber (< 30 dk) daha ağırlıklı
            freshness = math.exp(-age_min / 60)
            weighted_sum  += item.sentiment * freshness
            weight_total  += freshness

        return round(weighted_sum / weight_total, 3) if weight_total > 0 else 0.0

    def news_rank_bonus(self, sentiment: float) -> float:
        """
        AI ranking'e eklenecek haber bonusu/cezası.
        Pozitif: +0 ile +0.5
        Negatif: -0.5 ile 0
        """
        if sentiment > 0.5:
            return 0.5
        elif sentiment > 0.2:
            return 0.2
        elif sentiment < -0.5:
            return -0.5
        elif sentiment < -0.2:
            return -0.2
        return 0.0
