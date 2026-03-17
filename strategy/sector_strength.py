# ============================================================
# strategy/sector_strength.py
# Sektör Güç Motoru
#
# Her sektör için:
#   - Ortalama fiyat değişimi
#   - Momentum
#   - Hacim aktivitesi
#   - Score katkısı
#   - 0-100 güç puanı
#   - Dönen para / relative activity
# ============================================================
from __future__ import annotations

import math
from typing import Optional

from data.models import SignalCandidate, MarketSnapshot
from data.sector_map import SYMBOL_SECTOR, SectorSnapshot, group_by_sector, SECTORS


class SectorStrengthEngine:
    """
    SignalCandidate listesini ve MarketSnapshot'ı kullanarak
    sektör bazlı performans hesaplar.

    Kullanım:
        engine = SectorStrengthEngine()
        sectors = engine.compute(candidates, snapshot)
    """

    # Güç puanı ağırlıkları
    _W_CHANGE   = 0.30
    _W_MOMENTUM = 0.25
    _W_VOLUME   = 0.20
    _W_SCORE    = 0.15
    _W_ADV_RATIO = 0.10

    def compute(
        self,
        candidates:  list[SignalCandidate],
        snapshot:    MarketSnapshot,
        sector_filter: Optional[list[str]] = None,
    ) -> dict[str, SectorSnapshot]:
        """
        Tüm sektörler için SectorSnapshot üret.
        sector_filter: sadece bu sektörleri hesapla (None = tümü)
        """
        # Sembol → candidate map
        cand_map: dict[str, SignalCandidate] = {c.symbol: c for c in candidates}

        # Sektör bazlı sembol grupları
        active_symbols = list(snapshot.ticks.keys())
        groups = group_by_sector(active_symbols)

        results: dict[str, SectorSnapshot] = {}

        for sector, syms in groups.items():
            if sector_filter and sector not in sector_filter:
                continue
            ss = self._compute_sector(sector, syms, cand_map, snapshot)
            results[sector] = ss

        # Hacim normalizasyonu — tüm sektörlere göre relative
        self._normalize_volume_activity(results)

        return results

    def _compute_sector(
        self,
        sector:   str,
        symbols:  list[str],
        cand_map: dict[str, SignalCandidate],
        snapshot: MarketSnapshot,
    ) -> SectorSnapshot:
        ss = SectorSnapshot(name=sector, symbols=list(symbols))

        changes:   list[float] = []
        momentums: list[float] = []
        scores:    list[float] = []
        rsis:      list[float] = []
        volumes:   list[float] = []

        top_change  = -999.0; top_sym   = "—"
        weak_change =  999.0; weak_sym  = "—"

        for sym in symbols:
            tick = snapshot.ticks.get(sym)
            cand = cand_map.get(sym)
            if not tick:
                continue

            # Değişim
            if cand and cand.prev_price > 0:
                chg = (cand.price - cand.prev_price) / cand.prev_price * 100
            else:
                chg = 0.0
            changes.append(chg)

            if chg > 0:   ss.advancing += 1
            elif chg < 0: ss.declining += 1

            if chg > top_change:  top_change = chg; top_sym = sym
            if chg < weak_change: weak_change = chg; weak_sym = sym

            # Momentum, Skor, RSI
            if cand:
                momentums.append(cand.momentum)
                scores.append(float(cand.score))
                rsis.append(cand.rsi)

            # Hacim
            volumes.append(tick.volume)

        if not changes:
            return ss

        ss.avg_change_pct = round(_mean(changes), 3)
        ss.avg_momentum   = round(_mean(momentums), 3)
        ss.avg_score      = round(_mean(scores), 2)
        ss.avg_rsi        = round(_mean(rsis), 1) if rsis else 50.0
        ss.total_volume   = sum(volumes)
        ss.avg_volume     = _mean(volumes)
        ss.top_symbol     = top_sym
        ss.top_change     = round(top_change, 2) if top_sym != "—" else 0.0
        ss.weak_symbol    = weak_sym
        ss.weak_change    = round(weak_change, 2) if weak_sym != "—" else 0.0

        # Güç puanı hesapla (0-100)
        ss.strength = self._strength_score(ss)
        ss.strength_label = _strength_label(ss.strength)
        ss.trend_label, ss.trend_color = _trend_label(ss.avg_change_pct, ss.avg_momentum)

        return ss

    def _strength_score(self, ss: SectorSnapshot) -> float:
        """
        0-100 sektör güç puanı.
        Bileşenler: değişim, momentum, hacim(normalize sonra), skor, adv_ratio
        """
        # Değişim bileşeni: -3% → 0 puan, +3% → 100 puan
        chg_score = max(0, min(100, (ss.avg_change_pct + 3) / 6 * 100))

        # Momentum bileşeni: -5 → 0, +5 → 100
        mom_score = max(0, min(100, (ss.avg_momentum + 5) / 10 * 100))

        # Score bileşeni: 0 → 0, 6 → 100
        score_comp = max(0, min(100, ss.avg_score / 6 * 100))

        # Yükseliş oranı: 0% → 0, 100% → 100
        adv_score = ss.adv_ratio * 100

        # Hacim bileşeni — normalize_volume_activity sonrası doldurulur
        vol_score = ss.volume_activity

        strength = (
            chg_score   * self._W_CHANGE    +
            mom_score   * self._W_MOMENTUM  +
            vol_score   * self._W_VOLUME    +
            score_comp  * self._W_SCORE     +
            adv_score   * self._W_ADV_RATIO
        )
        return round(strength, 1)

    def _normalize_volume_activity(self, results: dict[str, SectorSnapshot]) -> None:
        """
        Sektör hacimlerini birbirine göre normalize et (0-100).
        En yüksek hacimli sektör → 100, en düşük → 0.
        """
        if not results:
            return
        volumes = [ss.total_volume for ss in results.values() if ss.total_volume > 0]
        if not volumes:
            return
        min_v = min(volumes)
        max_v = max(volumes)
        rng   = max_v - min_v or 1.0

        for ss in results.values():
            ss.volume_activity = round((ss.total_volume - min_v) / rng * 100, 1)
            # Güç puanını volume sonrası yeniden hesapla
            ss.strength = self._strength_score(ss)
            ss.strength_label = _strength_label(ss.strength)

    def fırsat_bonus(self, symbol: str, sectors: dict[str, SectorSnapshot]) -> float:
        """
        Opportunity scanner için sektör bonus/ceza.
        Güçlü sektör → +0.5, Zayıf sektör → -0.3
        """
        from data.sector_map import get_sector
        sec = get_sector(symbol)
        ss  = sectors.get(sec)
        if not ss:
            return 0.0
        if ss.strength >= 70: return  0.5
        if ss.strength >= 55: return  0.2
        if ss.strength <= 30: return -0.3
        if ss.strength <= 40: return -0.1
        return 0.0

    def sector_reason(self, symbol: str, sectors: dict[str, SectorSnapshot]) -> str:
        """Opportunity scanner 'sebep' satırı için sektör açıklaması."""
        from data.sector_map import get_sector
        sec = get_sector(symbol)
        ss  = sectors.get(sec)
        if not ss:
            return ""
        if ss.strength >= 70:
            return f"{sec} sektörü güçlü ({ss.strength:.0f})"
        if ss.strength <= 35:
            return f"{sec} sektörü zayıf ({ss.strength:.0f})"
        return f"{sec} ({ss.strength:.0f})"

    def sorted_sectors(
        self,
        results: dict[str, SectorSnapshot],
        by: str = "strength",
    ) -> list[SectorSnapshot]:
        """Sektörleri belirtilen alana göre sırala."""
        key_fn = {
            "strength":      lambda s: s.strength,
            "change":        lambda s: s.avg_change_pct,
            "volume":        lambda s: s.total_volume,
            "momentum":      lambda s: s.avg_momentum,
        }.get(by, lambda s: s.strength)
        return sorted(results.values(), key=key_fn, reverse=True)


# ── Yardımcı ─────────────────────────────────────────────────

def _mean(lst: list[float]) -> float:
    return sum(lst) / len(lst) if lst else 0.0


def _strength_label(s: float) -> str:
    if s >= 75: return "ÇOK GÜÇLÜ"
    if s >= 60: return "GÜÇLÜ"
    if s >= 45: return "NÖTR"
    if s >= 30: return "ZAYIF"
    return "ÇOK ZAYIF"


def _trend_label(change: float, momentum: float) -> tuple[str, str]:
    combined = change * 0.6 + momentum * 0.4
    if combined >  1.5: return "YÜKSELİŞ ↑↑", "#4ade80"
    if combined >  0.3: return "POZİTİF ↑",   "#86efac"
    if combined < -1.5: return "DÜŞÜŞ ↓↓",    "#f87171"
    if combined < -0.3: return "NEGATİF ↓",   "#fca5a5"
    return "YATAY →", "#94a3b8"
