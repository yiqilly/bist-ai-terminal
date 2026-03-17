# ============================================================
# recommendations/broker_engine.py — Aracı Kurum Önerileri v2
# Gerçek veri: borsapy Ticker.recommendations
# Mock kaldırıldı.
# ============================================================
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from data.models import BrokerRecommendation

_log = logging.getLogger("BrokerEngine")


def _fetch_recommendations(symbol: str) -> list[BrokerRecommendation]:
    """borsapy Ticker.recommendations ile gerçek kurum önerilerini çek."""
    try:
        import borsapy as bp
        ticker = bp.Ticker(symbol)
        recs = ticker.recommendations
        if recs is None or (hasattr(recs, 'empty') and recs.empty):
            return []
        result = []
        if isinstance(recs, dict) and recs:
            # We assume it's an aggregated summary rather than a list of individual brokers.
            broker = "Konsensüs"
            rec    = str(recs.get('recommendation', ''))
            
            # The API returns 'target_price' as a string like "183.00 TRY"
            target_raw = recs.get('target_price', '0')
            target = 0.0
            if isinstance(target_raw, str):
                import re
                match = re.search(r'[\d,.]+', target_raw)
                if match:
                    try:
                        target = float(match.group().replace(',', ''))
                    except ValueError:
                        pass
            elif isinstance(target_raw, (int, float)):
                target = float(target_raw)
                
            date = datetime.now()
            
            if rec:
                result.append(BrokerRecommendation(
                    symbol         = symbol,
                    broker         = broker,
                    recommendation = _normalize_rec(rec),
                    target_price   = target,
                    report_date    = date,
                ))
                
        return result
    except Exception as e:
        _log.debug(f"Broker({symbol}): {e}")
        return []


def _normalize_rec(raw: str) -> str:
    r = raw.strip().upper()
    if any(x in r for x in ("BUY", "AL", "OUTPERFORM", "OVERWEIGHT", "STRONG BUY")):
        return "AL"
    if any(x in r for x in ("SELL", "SAT", "UNDERPERFORM", "UNDERWEIGHT")):
        return "SAT"
    if any(x in r for x in ("HOLD", "TUT", "NEUTRAL", "EQUAL", "MARKET PERFORM")):
        return "TUT"
    return raw[:20]


class BrokerEngine:
    """
    Aracı kurum öneri motoru.
    Gerçek veri: borsapy Ticker.recommendations
    """

    def __init__(self):
        self._recs:   dict[str, list[BrokerRecommendation]] = {}
        self._lock    = threading.RLock()
        self._fetched: set[str] = set()

    def get_for_symbol(self, symbol: str) -> list[BrokerRecommendation]:
        """
        Sembol için önerileri döndür.
        İlk kez istendiğinde borsapy'den çeker.
        """
        with self._lock:
            if symbol in self._recs:
                return list(self._recs[symbol])
        # Cache'de yok → arka planda fetch et
        threading.Thread(
            target=self._bg_fetch, args=(symbol,), daemon=True
        ).start()
        return []

    def _bg_fetch(self, symbol: str) -> None:
        if symbol in self._fetched:
            return
        self._fetched.add(symbol)
        items = _fetch_recommendations(symbol)
        with self._lock:
            self._recs[symbol] = items
        if items:
            _log.debug(f"Broker({symbol}): {len(items)} öneri yüklendi")

    def refresh_mock(self, symbols=None, prices=None) -> None:
        """Mock kaldırıldı — hiçbir şey yapmaz."""
        pass

    def potential_pct(self, rec: BrokerRecommendation) -> float:
        """Mevcut fiyata göre hedef fiyat potansiyeli."""
        return 0.0  # Mevcut fiyat olmadan hesaplanamaz
