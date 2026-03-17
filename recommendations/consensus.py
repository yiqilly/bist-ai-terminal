# ============================================================
# recommendations/consensus.py — Kurum Konsensüs Hesabı
# ============================================================
from data.models import BrokerRecommendation, BrokerConsensus
from datetime import datetime


_BUY_WORDS  = {"AL", "Endeks Üstü Getiri"}
_SELL_WORDS = {"SAT", "Endeks Altı Getiri"}


class ConsensusEngine:
    def compute(
        self,
        symbol: str,
        recs: list[BrokerRecommendation],
        current_price: float,
    ) -> BrokerConsensus:
        if not recs:
            return BrokerConsensus(
                symbol=symbol, total_recs=0,
                buy_count=0, hold_count=0, sell_count=0,
                avg_target=current_price, current_price=current_price,
                potential_pct=0.0, consensus="—",
            )

        buy  = sum(1 for r in recs if r.recommendation in _BUY_WORDS)
        sell = sum(1 for r in recs if r.recommendation in _SELL_WORDS)
        hold = len(recs) - buy - sell
        avg_target = sum(r.target_price for r in recs) / len(recs)
        potential  = round((avg_target / current_price - 1) * 100, 1) if current_price > 0 else 0.0
        latest     = max(recs, key=lambda r: r.report_date).report_date

        if buy > sell and buy >= len(recs) * 0.5:
            consensus = "AL"
        elif sell > buy and sell >= len(recs) * 0.5:
            consensus = "SAT"
        else:
            consensus = "TUT"

        return BrokerConsensus(
            symbol=symbol, total_recs=len(recs),
            buy_count=buy, hold_count=hold, sell_count=sell,
            avg_target=round(avg_target, 2), current_price=current_price,
            potential_pct=potential, consensus=consensus,
            latest_report=latest,
        )

    def top_picks(
        self,
        all_symbols: list[str],
        broker_engine,
        prices: dict[str, float],
        top_n: int = 15,
    ) -> list[BrokerConsensus]:
        """En çok 'AL' tavsiyesi alan hisseler."""
        results = []
        for sym in all_symbols:
            recs = broker_engine.get_for_symbol(sym)
            price = prices.get(sym, 0.0)
            if recs:
                results.append(self.compute(sym, recs, price))
        # Önce AL sayısına göre, sonra potansiyele göre sırala
        results.sort(key=lambda x: (x.buy_count, x.potential_pct), reverse=True)
        return results[:top_n]
