# ============================================================
# strategy/relative_strength_engine.py
# Relative Strength Engine — FAZ 4
#
# Her hisse için endekse ve sektöre göre güç hesapla.
#
# RS_vs_index  = stock_return - index_return
# RS_vs_sector = stock_return - sector_avg_return
#
# Label:
#   LEADER   → RS > +1.0
#   STRONG   → RS > 0
#   NEUTRAL  → RS ≈ 0
#   LAGGARD  → RS < 0
#   WEAK     → RS < -1.0
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from data.models import SignalCandidate, MarketSnapshot


@dataclass
class RSResult:
    symbol:       str
    stock_return: float = 0.0     # hissenin % getirisi (anlık vs prev_close)
    index_return: float = 0.0     # endeks ortalama getirisi
    sector_return: float = 0.0    # sektör ortalama getirisi
    rs_vs_index:  float = 0.0     # RS = stock - index
    rs_vs_sector: float = 0.0     # RS = stock - sector
    label:        str   = "NEUTRAL"   # LEADER | STRONG | NEUTRAL | LAGGARD | WEAK
    sector_rank:  int   = 0           # sektörde kaçıncı (1 = en güçlü)
    universe_rank: int  = 0           # tüm evrende sıra
    color:        str   = "#94a3b8"

    @property
    def is_leader(self) -> bool:
        return self.label in ("LEADER", "STRONG")

    @property
    def score(self) -> float:
        """0-10 arası normalize RS skoru."""
        return max(0.0, min(10.0, 5.0 + self.rs_vs_index * 2))


class RelativeStrengthEngine:
    """
    Tüm candidates için RS hesaplar.
    Sektör karşılaştırması için sector_map kullanır.
    """

    def compute(
        self,
        candidates: list[SignalCandidate],
        snapshot:   MarketSnapshot,
        sector_returns: dict[str, float] | None = None,  # sektör adı → ort. getiri
    ) -> dict[str, RSResult]:
        """
        Döndürür: symbol → RSResult mapping.
        """
        if not candidates:
            return {}

        # Endeks getirisi = tüm hisselerin ağırlıksız ortalaması
        returns = {}
        for c in candidates:
            if c.prev_price > 0:
                ret = (c.price - c.prev_price) / c.prev_price * 100
            else:
                ret = 0.0
            returns[c.symbol] = ret

        index_return = sum(returns.values()) / len(returns) if returns else 0.0

        # Sektör getirileri hesapla (yoksa parametreden al)
        if sector_returns is None:
            sector_returns = self._calc_sector_returns(candidates, returns)

        # Her hisse için RS
        results: dict[str, RSResult] = {}
        for c in candidates:
            ret   = returns.get(c.symbol, 0.0)
            rs_i  = round(ret - index_return, 3)

            from data.sector_map import get_sector
            sec   = get_sector(c.symbol)
            sec_r = sector_returns.get(sec, index_return)
            rs_s  = round(ret - sec_r, 3)

            label, color = self._label(rs_i)
            results[c.symbol] = RSResult(
                symbol        = c.symbol,
                stock_return  = round(ret, 3),
                index_return  = round(index_return, 3),
                sector_return = round(sec_r, 3),
                rs_vs_index   = rs_i,
                rs_vs_sector  = rs_s,
                label         = label,
                color         = color,
            )

        # Universe rank (RS vs index'e göre)
        sorted_syms = sorted(results, key=lambda s: results[s].rs_vs_index, reverse=True)
        for rank, sym in enumerate(sorted_syms, 1):
            results[sym].universe_rank = rank

        # Sektör içi sıra
        self._assign_sector_ranks(results, candidates)

        return results

    def _calc_sector_returns(
        self,
        candidates: list[SignalCandidate],
        returns: dict[str, float],
    ) -> dict[str, float]:
        from data.sector_map import get_sector
        sector_data: dict[str, list[float]] = {}
        for c in candidates:
            sec = get_sector(c.symbol)
            sector_data.setdefault(sec, []).append(returns.get(c.symbol, 0.0))
        return {
            sec: sum(rets) / len(rets)
            for sec, rets in sector_data.items() if rets
        }

    def _assign_sector_ranks(
        self,
        results: dict[str, RSResult],
        candidates: list[SignalCandidate],
    ) -> None:
        from data.sector_map import get_sector
        # Sektör grupları
        sectors: dict[str, list[str]] = {}
        for c in candidates:
            sec = get_sector(c.symbol)
            sectors.setdefault(sec, []).append(c.symbol)
        for sec, syms in sectors.items():
            sorted_syms = sorted(
                syms,
                key=lambda s: results[s].rs_vs_sector if s in results else 0,
                reverse=True,
            )
            for rank, sym in enumerate(sorted_syms, 1):
                if sym in results:
                    results[sym].sector_rank = rank

    def _label(self, rs: float) -> tuple[str, str]:
        if rs > 1.5:  return ("LEADER",  "#4ade80")
        if rs > 0.3:  return ("STRONG",  "#86efac")
        if rs > -0.3: return ("NEUTRAL", "#94a3b8")
        if rs > -1.5: return ("LAGGARD", "#fb923c")
        return          ("WEAK",    "#ef4444")

    def get_leaders(
        self,
        results: dict[str, RSResult],
        top_n: int = 10,
    ) -> list[RSResult]:
        """En güçlü RS'leri döndür."""
        return sorted(results.values(), key=lambda r: r.rs_vs_index, reverse=True)[:top_n]

    def get_laggards(
        self,
        results: dict[str, RSResult],
        top_n: int = 5,
    ) -> list[RSResult]:
        return sorted(results.values(), key=lambda r: r.rs_vs_index)[:top_n]
