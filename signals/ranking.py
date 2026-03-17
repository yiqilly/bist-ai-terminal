# ============================================================
# signals/ranking.py — Sinyal Sıralama (güncellenmiş)
# ============================================================
from data.models import SignalCandidate, RankedSignal, RegimeResult
from risk.risk_engine import RiskEngine
from signals.combined_scoring import CombinedScorer


class SignalRanker:
    def __init__(self, risk_engine: RiskEngine, scorer: CombinedScorer):
        self._risk   = risk_engine
        self._scorer = scorer

    def rank(
        self,
        candidates: list[SignalCandidate],
        regime: RegimeResult | None = None,
        all_candidates: list[SignalCandidate] | None = None,
    ) -> list[RankedSignal]:
        ranked = []
        for i, c in enumerate(candidates, start=1):
            risk_profile = self._risk.calculate(c)
            signal = RankedSignal(candidate=c, risk=risk_profile, rank=i)
            signal = self._scorer.enrich(signal, regime, all_candidates)
            ranked.append(signal)

        # combined_score'a göre yeniden sırala
        ranked.sort(key=lambda s: s.combined_score, reverse=True)
        for i, s in enumerate(ranked, start=1):
            s.rank = i
        return ranked
