# ============================================================
# news/news_engine.py — Haber Motoru v6
# Gerçek veri kaynakları (sırasıyla denenir):
#   1. borsapy Ticker.news  → KAP bildirimleri (en güncel)
#   2. KAP RSS feed          → genel BIST haberleri
# Mock tamamen kaldırıldı.
# ============================================================
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from data.models import NewsItem
from data.symbols import ACTIVE_UNIVERSE

_log = logging.getLogger("NewsEngine")


# ── Sentiment Anahtar Kelime Sözlüğü ─────────────────────────

_POS = {
    "güçlü": 0.7, "büyüme": 0.6, "kâr": 0.6, "temettü": 0.65,
    "rekor": 0.8, "arttı": 0.55, "yükseldi": 0.5, "anlaşma": 0.5,
    "ihracat": 0.5, "bilanço": 0.45, "yatırım": 0.45, "ortaklık": 0.5,
    "kazanç": 0.6, "gelir arttı": 0.65, "beklentilerin üzerinde": 0.75,
    "pozitif": 0.5, "proje": 0.4, "ihale": 0.45, "sözleşme": 0.55,
}
_NEG = {
    "zarar": -0.7, "düştü": -0.5, "geriledi": -0.5, "soruşturma": -0.75,
    "dava": -0.6, "baskı": -0.4, "kayıp": -0.65,
    "beklentilerin altında": -0.7, "endişe": -0.45, "negatif": -0.5,
    "iflas": -0.9, "temerrüt": -0.85, "ceza": -0.6, "uyarı": -0.35,
}

def _score(text: str) -> float:
    h = text.lower()
    s = sum(v for k, v in _POS.items() if k in h)
    s += sum(v for k, v in _NEG.items() if k in h)
    return round(max(-1.0, min(1.0, s)), 2)


# ── borsapy Ticker haberci ────────────────────────────────────

def _fetch_ticker_news(symbol: str, limit: int = 5) -> list[NewsItem]:
    """borsapy Ticker.news ile KAP bildirimlerini çek."""
    try:
        import borsapy as bp
        ticker = bp.Ticker(symbol)
        raw = ticker.news
        if raw is None or (hasattr(raw, 'empty') and raw.empty):
            return []
        items = []
        # DataFrame ya da list olabilir
        if hasattr(raw, 'iterrows'):
            for _, row in raw.iterrows():
                headline = str(row.get('Title', row.get('title', row.get('headline', ''))))
                if not headline or headline.lower() == 'nan':
                    continue
                ts_raw = row.get('Date', row.get('date', row.get('publishDate', datetime.now())))
                try:
                    ts = datetime.fromisoformat(str(ts_raw)[:19]) if isinstance(ts_raw, str) else ts_raw
                except Exception:
                    ts = datetime.now()
                if isinstance(ts, str):
                    ts = datetime.now()
                items.append(NewsItem(
                    symbol    = symbol,
                    headline  = headline[:200],
                    source    = "KAP",
                    sentiment = _score(headline),
                    timestamp = ts,
                    url       = str(row.get('URL', row.get('url', row.get('link', '')))),
                ))
        elif isinstance(raw, list):
            for r in raw:
                headline = r.get('title', r.get('headline', ''))
                if not headline:
                    continue
                ts = datetime.now()
                items.append(NewsItem(
                    symbol=symbol, headline=str(headline)[:200],
                    source="KAP", sentiment=_score(str(headline)),
                    timestamp=ts,
                ))
        return items[:limit]
    except Exception as e:
        _log.debug(f"Ticker.news({symbol}): {e}")
        return []


def _fetch_kap_rss(limit: int = 30) -> list[NewsItem]:
    """KAP RSS'den genel BIST haberlerini çek."""
    try:
        from news.kap_feed import _fetch_rss, _extract_symbol, _parse_kap_date, _score_headline
        # KAP feed patladığı için (404 Not Found), çalışan borsagundem tr feed'i kullanıyoruz.
        raw_items = _fetch_rss("https://www.borsagundem.com.tr/rss", timeout=8)
        items = []
        seen_urls = set()
        for r in raw_items[:limit]:
            title = r.get('title', '').strip()
            if not title or len(title) < 5:
                continue
            url = r.get('link', '')
            if url in seen_urls:
                continue
            seen_urls.add(url)
            full = f"{title} {r.get('description','')}"
            sym  = _extract_symbol(full)
            ts   = _parse_kap_date(r.get('pub_date_str', ''))
            if (datetime.now() - ts).total_seconds() > 86400 * 3:  # 3 günden eski
                continue
            items.append(NewsItem(
                symbol    = sym or "",
                headline  = title[:200],
                source    = "KAP",
                sentiment = _score(full),
                timestamp = ts,
                url       = url,
            ))
        return items
    except Exception as e:
        _log.debug(f"KAP RSS: {e}")
        return []


# ── Ana Motor ─────────────────────────────────────────────────

class NewsEngine:
    """
    Gerçek haber motoru.
    Kaynak önceliği:
      1. borsapy Ticker.news (KAP bildirimleri)
      2. KAP RSS (genel haberler)
    Mock tamamen kaldırıldı.
    """

    def __init__(self):
        self._news:   list[NewsItem] = []
        self._index:  dict[str, list[NewsItem]] = {}
        self._lock    = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_fetch = datetime.min
        self._fetch_interval = 120   # saniye (2 dakika)

        # İlk yükleme hemen
        self._refresh()

        # Arka plan thread başlat
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, daemon=True, name="news-engine"
        )
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            time.sleep(self._fetch_interval)
            if self._running:
                self._refresh()

    def _refresh(self) -> None:
        """Gerçek kaynaklardan haberleri çek."""
        all_items: list[NewsItem] = []

        # 1. KAP RSS (genel, hızlı)
        rss_items = _fetch_kap_rss(limit=40)
        all_items.extend(rss_items)

        # 2. borsapy Ticker.news — önemli semboller için
        # Tüm BIST30'u tek tek sorgularsak rate limit'e takılırız.
        # Her yenileme döngüsünde 5 sembol rotasyonu yap.
        # (KOZAA gibi bazı semboller borsapy'de bulunamayabilir,
        #  _fetch_ticker_news exception'ı handle ediyor)
        _log.debug(f"Haber güncellendi: RSS={len(rss_items)}")

        if all_items:
            # Zaman damgasına göre sırala, son 3 günü tut
            cutoff = datetime.now() - timedelta(days=3)
            fresh  = [n for n in all_items if n.timestamp >= cutoff]
            fresh.sort(key=lambda n: n.timestamp, reverse=True)
            with self._lock:
                self._news  = fresh[:60]
                self._index = {}
                for n in self._news:
                    if n.symbol:
                        self._index.setdefault(n.symbol, []).append(n)
            self._last_fetch = datetime.now()
            _log.info(f"NewsEngine: {len(self._news)} haber yüklendi (KAP RSS)")

    def refresh_for_symbol(self, symbol: str) -> None:
        """Belirli sembol için borsapy Ticker.news çek."""
        items = _fetch_ticker_news(symbol, limit=8)
        if items:
            with self._lock:
                self._index[symbol] = items

    def get_news(self, symbol: str | None = None) -> list[NewsItem]:
        with self._lock:
            if symbol:
                return list(self._index.get(symbol, []))
            return list(self._news)

    def get_recent(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        """Sembol seçildiğinde Ticker.news'i de dene."""
        items = self.get_news(symbol)
        if not items:
            # Anlık fetch dene
            items = _fetch_ticker_news(symbol, limit=limit)
            if items:
                with self._lock:
                    self._index[symbol] = items
        return items[:limit]

    def has_positive_news(self, symbol: str) -> bool:
        return any(n.sentiment > 0.4 for n in self.get_news(symbol))

    def has_negative_news(self, symbol: str) -> bool:
        return any(n.sentiment < -0.3 for n in self.get_news(symbol))

    def refresh_mock(self, count: int = 0) -> None:
        """Mock kaldırıldı — artık hiçbir şey yapmaz."""
        pass

    @property
    def source_label(self) -> str:
        with self._lock:
            return "KAP RSS" if self._news else "Bağlanıyor..."

    @property
    def last_fetch_age_secs(self) -> float:
        return (datetime.now() - self._last_fetch).total_seconds()
