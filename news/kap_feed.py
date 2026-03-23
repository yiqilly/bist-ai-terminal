# ============================================================
# news/kap_feed.py
# KAP (Kamuyu Aydınlatma Platformu) RSS Haber Çekici
#
# KAP resmi RSS endpoint'i üzerinden gerçek BIST haberleri.
# Fallback: Investing.com RSS, Yahoo Finance RSS.
# Mock tamamen kaldırıldı.
# ============================================================
from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from data.models import NewsItem
from data.symbols import ACTIVE_UNIVERSE

_log = logging.getLogger("KapFeed")

# ── RSS Kaynakları ────────────────────────────────────────────

_FEEDS = [
    # KAP bildirim RSS'i — BIST/KAP açıklamaları
    {
        "name": "KAP",
        "url":  "https://www.kap.org.tr/tr/rss/bildirim-listesi",
        "type": "kap",
    },
    # Borsa İstanbul haberleri
    {
        "name": "Borsa Gündem",
        "url":  "https://borsagundem.com/feed/",
        "type": "generic",
    },
    # Yahoo Finance TR hisseleri — her sembol için opsiyonel
    # {
    #     "name": "Yahoo Finance",
    #     "url":  "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}.IS&region=TR",
    #     "type": "yahoo_per_symbol",
    # },
]

# ── Sentiment Anahtar Kelime Sözlüğü ─────────────────────────

_POSITIVE_KEYWORDS = {
    "güçlü": 0.7, "büyüme": 0.6, "kâr": 0.6, "temettü": 0.65,
    "rekor": 0.8, "arttı": 0.55, "yükseldi": 0.55, "anlaşma": 0.5,
    "ihracat": 0.5, "bilanço": 0.5, "hedef": 0.4, "yatırım": 0.45,
    "ortaklık": 0.5, "prim": 0.55, "kazanç": 0.6, "gelir arttı": 0.65,
    "beklentilerin üzerinde": 0.75, "pozitif": 0.5,
}

_NEGATIVE_KEYWORDS = {
    "zarar": -0.7, "düştü": -0.55, "geriledi": -0.5, "soruşturma": -0.75,
    "dava": -0.6, "baskı": -0.45, "kayıp": -0.65, "beklentilerin altında": -0.7,
    "endişe": -0.45, "risk": -0.3, "negatif": -0.5, "sermaye artırımı": 0.2,
    "iflas": -0.9, "temerrüt": -0.85, "ceza": -0.6,
}


def _score_headline(headline: str) -> float:
    """Başlığı analiz ederek -1.0 ile +1.0 arası sentiment skoru döndür."""
    h = headline.lower()
    score = 0.0
    for kw, val in _POSITIVE_KEYWORDS.items():
        if kw in h:
            score += val
    for kw, val in _NEGATIVE_KEYWORDS.items():
        if kw in h:
            score += val  # negatif değerler
    return max(-1.0, min(1.0, score))


def _extract_symbol(text: str) -> Optional[str]:
    """Haber metninden BIST sembolünü tespit et."""
    text_upper = text.upper()
    for sym in ACTIVE_UNIVERSE:
        if sym in text_upper:
            return sym
    return None


def _parse_kap_date(date_str: str) -> datetime:
    """KAP / RSS tarih string'ini datetime'a çevir."""
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",   # RFC 2822
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=None)
        except (ValueError, AttributeError):
            continue
    return datetime.now()


def _fetch_rss(url: str, timeout: int = 8) -> list[dict]:
    """
    RSS URL'ini çek ve ham item listesi döndür.
    Her item: {title, link, pub_date_str, description}
    """
    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (BIST Terminal RSS Reader)",
            "Accept": "application/rss+xml, application/xml, text/xml",
        })
        with urlopen(req, timeout=timeout) as resp:
            content = resp.read()

        root = ET.fromstring(content)
        # RSS 2.0 yapısı
        items = []
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            link  = item.findtext("link")  or ""
            pub   = item.findtext("pubDate") or item.findtext("dc:date") or ""
            desc  = item.findtext("description") or ""
            if title:
                items.append({
                    "title":        title.strip(),
                    "link":         link.strip(),
                    "pub_date_str": pub.strip(),
                    "description":  desc.strip(),
                })
        return items

    except URLError as e:
        _log.debug(f"RSS erişim hatası {url}: {e}")
        return []
    except ET.ParseError as e:
        _log.debug(f"RSS parse hatası {url}: {e}")
        return []
    except Exception as e:
        _log.debug(f"RSS bilinmeyen hata {url}: {e}")
        return []


# ── Ana Feed Sınıfı ───────────────────────────────────────────

class KapFeed:
    """
    KAP ve diğer RSS kaynaklarından gerçek haber çeker.
    Arka planda belirli aralıklarla yeniler.
    """

    def __init__(
        self,
        refresh_interval: int = 120,   # saniye (2 dakika)
        max_items: int = 60,
    ):
        self._interval  = refresh_interval
        self._max       = max_items
        self._news:     list[NewsItem] = []
        self._index:    dict[str, list[NewsItem]] = {}
        self._lock      = threading.RLock()
        self._thread:   Optional[threading.Thread] = None
        self._running   = False
        self._last_urls: set[str] = set()   # duplicate URL önlemi

    def start(self) -> None:
        """Arka plan yenileme thread'ini başlat."""
        if self._running:
            return
        self._running = True
        # İlk yüklemeyi hemen yap
        self._refresh()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="kap-feed"
        )
        self._thread.start()
        _log.info(f"KapFeed başlatıldı ({self._interval}s aralık)")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            time.sleep(self._interval)
            if self._running:
                self._refresh()

    def _refresh(self) -> None:
        """Tüm kaynaklardan haberleri çek ve birleştir."""
        new_items: list[NewsItem] = []

        for feed_cfg in _FEEDS:
            try:
                raw_items = _fetch_rss(feed_cfg["url"])
                for item in raw_items:
                    news = self._parse_item(item, feed_cfg["name"])
                    if news and news.url not in self._last_urls:
                        new_items.append(news)
                        self._last_urls.add(news.url)
            except Exception as e:
                _log.debug(f"Feed {feed_cfg['name']} hatası: {e}")

        if not new_items:
            _log.debug("Yeni haber bulunamadı.")
            return

        with self._lock:
            combined = new_items + self._news
            # Zaman damgasına göre sırala, max_items ile sınırla
            combined.sort(key=lambda n: n.timestamp, reverse=True)
            self._news  = combined[:self._max]
            self._index = {}
            for n in self._news:
                if n.symbol:
                    self._index.setdefault(n.symbol, []).append(n)

        _log.info(f"KapFeed: {len(new_items)} yeni haber, toplam {len(self._news)}")

    def _parse_item(self, item: dict, source: str) -> Optional[NewsItem]:
        """Ham RSS item'ı NewsItem'a dönüştür."""
        title = item["title"]
        if not title or len(title) < 5:
            return None

        # Sembol tespit et
        full_text = f"{title} {item.get('description','')}"
        symbol = _extract_symbol(full_text)

        # Tarih parse
        pub_date = _parse_kap_date(item["pub_date_str"])

        # Çok eski haberleri atla (24 saatten eski)
        if (datetime.now() - pub_date).total_seconds() > 86400:
            return None

        # Sentiment
        sentiment = _score_headline(full_text)

        return NewsItem(
            symbol    = symbol or "",   # sembol bulunamadıysa genel haber
            headline  = title[:200],
            source    = source,
            sentiment = round(sentiment, 2),
            timestamp = pub_date,
            url       = item.get("link", ""),
        )

    # ── Sorgu Metodları ──────────────────────────────────────

    def get_news(self, symbol: str | None = None) -> list[NewsItem]:
        with self._lock:
            if symbol:
                return list(self._index.get(symbol, []))
            return list(self._news)

    def get_recent(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        return self.get_news(symbol)[:limit]

    def has_positive_news(self, symbol: str) -> bool:
        return any(n.sentiment > 0.4 for n in self.get_news(symbol))

    def has_negative_news(self, symbol: str) -> bool:
        return any(n.sentiment < -0.3 for n in self.get_news(symbol))

    @property
    def total_count(self) -> int:
        with self._lock:
            return len(self._news)
