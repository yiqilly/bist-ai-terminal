# ============================================================
# strategy/rules.py — Sinyal Skorlama Kuralları
# ============================================================
from config import SIGNAL_FILTER
from data.models import SignalCandidate


def score_candidate(c: SignalCandidate) -> int:
    """
    Adaya 0-6 arası puan ver.
    Her kural 1 puan ekler.
    """
    score = 0
    if SIGNAL_FILTER["rsi_min"] <= c.rsi <= SIGNAL_FILTER["rsi_max"]:
        score += 1
    if c.trend:
        score += 1
    if c.breakout:
        score += 1
    if c.volume_confirm:
        score += 1
    if c.momentum > 1.0:
        score += 1
    if c.ema9 > c.ema21:
        score += 1
    return score


def passes_filter(c: SignalCandidate) -> bool:
    """Filtreyi geçen sinyaller best-list'e girer."""
    f = SIGNAL_FILTER
    return (
        c.score >= f["min_score"]
        and f["rsi_min"] <= c.rsi <= f["rsi_max"]
        and (not f["require_trend"] or c.trend)
        and (not f["require_breakout"] or c.breakout)
        and (not f["require_volume_confirm"] or c.volume_confirm)
    )


def quality_label(score: int) -> str:
    if score >= 6:
        return "A+"
    elif score >= 5:
        return "A"
    elif score >= 4:
        return "B"
    else:
        return "C"
