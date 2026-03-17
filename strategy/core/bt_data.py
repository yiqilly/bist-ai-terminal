# ============================================================
# strategy/core/bt_data.py
# Backtest Veri Katmanı
#
# İki kaynak desteklenir:
#   A) Gerçek CSV/dict — Matriks IQ'dan dışa aktarılmış
#      Format: {symbol: {date: [OHLCVBar, ...]}}
#
#   B) RealisticBarGenerator — Sentetik ama gerçekçi
#      Gerçek veriden önce stratejiyi test etmek için.
#      GBM (Geometric Brownian Motion) tabanlı.
#
# Bar granülaritesi: 1m veya 5m
# ============================================================
from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterator


# ── Temel OHLCV Bar ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class OHLCVBar:
    """
    Tek bir intraday bar.
    ts  : bar'ın kapanış zamanı (veya başlangıcı — tutarlı olun)
    """
    symbol: str
    timestamp:     datetime
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float

    @property
    def date(self) -> date:
        return self.timestamp.date()

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2

    @property
    def body_pct(self) -> float:
        """Gövde yüzdesi: |close-open|/open"""
        return abs(self.close - self.open) / self.open * 100 if self.open else 0.0


# ── Günlük Bar Dizisi ────────────────────────────────────────────────────────

@dataclass
class DayBars:
    """Bir sembol için tek günün bar listesi."""
    symbol: str
    date:   date
    bars:   list[OHLCVBar]

    def bars_between(self, t_start: time, t_end: time) -> list[OHLCVBar]:
        return [b for b in self.bars if t_start <= b.timestamp.time() <= t_end]

    def bars_after(self, t_start: time) -> list[OHLCVBar]:
        return [b for b in self.bars if b.timestamp.time() > t_start]

    @property
    def open_price(self) -> float:
        return self.bars[0].open if self.bars else 0.0

    @property
    def close_price(self) -> float:
        return self.bars[-1].close if self.bars else 0.0


# ── Gerçekçi Bar Üretici ─────────────────────────────────────────────────────

class RealisticBarGenerator:
    """
    GBM (Geometric Brownian Motion) + hacim + intraday gün içi profil.

    Özellikleri:
    - Her gün bağımsız seed → tekrarlanabilir
    - İntraday volatilite profili: sabah & kapanış yüksek, öğle düşük
    - Gerçekçi hacim dağılımı (U-şekli: sabah ve kapanışta yoğun)
    - Rejim bazlı trend bias (AGGRESSIVE / NORMAL_TREND / CHOP / RISK_OFF)
    - Gap oluşumu (gün açılışında önceki kapanıştan sapma)
    """

    # BIST seans saatleri
    MARKET_OPEN  = time(10, 0)
    MARKET_CLOSE = time(18, 0)

    # İntraday volatilite çarpanları (saat başına, 10-18 arası)
    # Daha gerçekçi U-şekli: sabah açılış ve kapanış saatleri yüksek
    _VOL_MULTIPLIER = {
        10: 1.8,   # Açılış — yüksek
        11: 1.2,
        12: 0.9,
        13: 0.8,   # Öğle — düşük
        14: 0.85,
        15: 0.9,
        16: 1.0,
        17: 1.3,   # Kapanış öncesi
    }

    # Hacim dağılım ağırlıkları (aynı saatler için)
    _VOL_WEIGHT = {
        10: 2.5, 11: 1.4, 12: 1.0, 13: 0.8,
        14: 0.9, 15: 1.1, 16: 1.3, 17: 1.8,
    }

    def __init__(self, bar_size_min: int = 5):
        """
        bar_size_min: 1 veya 5 dakika
        """
        assert bar_size_min in (1, 5), "Bar boyutu 1m veya 5m olmalı"
        self.bar_size = bar_size_min

    def generate_day(
        self,
        symbol: str,
        dt: date,
        base_price: float,
        annual_volatility: float = 0.35,   # BIST hisseleri için tipik ~%35
        regime_mode: str = "NORMAL_TREND",
        gap_pct: float = 0.0,              # gün açılış gap'i
    ) -> DayBars:
        """
        Tek bir gün için tam seans bar listesi üretir.
        """
        rng = random.Random(hash(f"{symbol}_{dt}"))

        # Rejim bazlı drift (yıllık → bar bazına çevir)
        drift_map = {
            "AGGRESSIVE":   0.30,
            "NORMAL_TREND": 0.15,
            "NORMAL_CHOP":  0.00,
            "RISK_OFF":    -0.25,
        }
        annual_drift = drift_map.get(regime_mode, 0.10)

        # Bar başına parametreler
        bars_per_year  = 252 * (480 // self.bar_size)   # 480dk = 8 saatlik seans
        dt_bar         = 1 / bars_per_year
        sigma_bar      = annual_volatility * math.sqrt(dt_bar)
        mu_bar         = (annual_drift - 0.5 * annual_volatility ** 2) * dt_bar

        # Gap uygula
        price = base_price * (1 + gap_pct)

        bars: list[OHLCVBar] = []
        current = datetime.combine(dt, self.MARKET_OPEN)
        end_dt  = datetime.combine(dt, self.MARKET_CLOSE)

        while current < end_dt:
            hour     = current.hour
            vol_mult = self._VOL_MULTIPLIER.get(hour, 1.0)
            vol_w    = self._VOL_WEIGHT.get(hour, 1.0)

            # GBM adımı
            z      = rng.gauss(0, 1)
            ln_ret = mu_bar + sigma_bar * vol_mult * z
            close  = round(price * math.exp(ln_ret), 2)

            # High/Low: gerçekçi gölge genişliği
            shadow = abs(close - price) * rng.uniform(1.1, 2.2)
            if close >= price:
                high = round(close  + shadow * rng.uniform(0.05, 0.4),  2)
                low  = round(price  - shadow * rng.uniform(0.05, 0.25), 2)
            else:
                high = round(price  + shadow * rng.uniform(0.05, 0.25), 2)
                low  = round(close  - shadow * rng.uniform(0.05, 0.4),  2)

            # Hacim
            base_vol_bar = 2_000_000 / (480 / self.bar_size)
            volume = round(base_vol_bar * vol_w * rng.uniform(0.5, 1.8))

            bars.append(OHLCVBar(
                symbol=symbol, timestamp=current,
                open=round(price, 2), high=high, low=low, close=close, volume=volume,
            ))

            price    = close
            current += timedelta(minutes=self.bar_size)

        return DayBars(symbol=symbol, date=dt, bars=bars)

    def generate_history(
        self,
        symbol: str,
        start: date,
        end: date,
        base_price: float,
        annual_volatility: float = 0.35,
        regime_schedule: dict[date, str] | None = None,
    ) -> list[DayBars]:
        """
        Tarih aralığı için tüm işlem günlerini üretir.
        regime_schedule: {date: mode} — belirli günlere rejim ata
        """
        result: list[DayBars] = []
        current = start
        price   = base_price

        while current <= end:
            # Hafta içi günleri (BIST Cumartesi-Pazar kapalı)
            if current.weekday() < 5:
                mode = (regime_schedule or {}).get(current, "NORMAL_TREND")

                # Gerçekçi rejim dağılımı yoksa basit heuristic
                if regime_schedule is None:
                    day_hash = hash(f"{symbol}_{current}") % 100
                    if day_hash < 25:   mode = "AGGRESSIVE"
                    elif day_hash < 55: mode = "NORMAL_TREND"
                    elif day_hash < 75: mode = "NORMAL_CHOP"
                    else:               mode = "RISK_OFF"

                # Gap simülasyonu (%70 gap yok, %30 küçük gap)
                rng   = random.Random(hash(f"gap_{symbol}_{current}"))
                gap   = rng.gauss(0, 0.003) if rng.random() < 0.3 else 0.0

                day = self.generate_day(
                    symbol, current, price,
                    annual_volatility=annual_volatility,
                    regime_mode=mode, gap_pct=gap,
                )
                if day.bars:
                    result.append(day)
                    price = day.close_price

            current += timedelta(days=1)

        return result


# ── CSV Yükleyici (Matriks IQ veya diğer kaynaklar) ─────────────────────────

class CSVBarLoader:
    """
    CSV dosyasından OHLCV bar yükler.

    Beklenen format (Matriks IQ dışa aktarımı):
        Symbol,Date,Time,Open,High,Low,Close,Volume
        THYAO,2024-01-02,10:00,150.20,151.00,149.80,150.60,1234567

    Alternatif: Date+Time birleşik sütun (datetime formatı)
    """

    def load(
        self,
        filepath: str | Path,
        symbol: str | None = None,
        start: date | None = None,
        end:   date | None = None,
    ) -> dict[str, list[DayBars]]:
        """
        CSV'den {symbol: [DayBars, ...]} döndürür.
        symbol filtresi verilirse sadece o sembol yüklenir.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Bar dosyası bulunamadı: {filepath}")

        raw: dict[str, dict[date, list[OHLCVBar]]] = {}

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get("Symbol") or row.get("symbol") or ""
                if symbol and sym != symbol:
                    continue

                # Tarih ayrıştırma — birden fazla format dene
                dt = self._parse_date(row.get("Date") or row.get("date") or "")
                if dt is None:
                    continue
                if start and dt < start:
                    continue
                if end   and dt > end:
                    continue

                ts = self._parse_ts(
                    row.get("Date") or row.get("date") or "",
                    row.get("Time") or row.get("time") or "00:00",
                )

                bar = OHLCVBar(
                    symbol=sym, timestamp=ts,
                    open=float(row.get("Open")  or row.get("open")  or 0),
                    high=float(row.get("High")  or row.get("high")  or 0),
                    low= float(row.get("Low")   or row.get("low")   or 0),
                    close=float(row.get("Close") or row.get("close") or 0),
                    volume=float(row.get("Volume") or row.get("volume") or 0),
                )

                raw.setdefault(sym, {}).setdefault(dt, []).append(bar)

        # Sırala ve DayBars'a çevir
        result: dict[str, list[DayBars]] = {}
        for sym, day_dict in raw.items():
            days = []
            for dt, bars in sorted(day_dict.items()):
                bars.sort(key=lambda b: b.timestamp)
                days.append(DayBars(symbol=sym, date=dt, bars=bars))
            result[sym] = days

        return result

    @staticmethod
    def _parse_date(s: str) -> date | None:
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y%m%d"):
            try:
                return datetime.strptime(s.split()[0], fmt).date()
            except Exception:
                pass
        return None

    @staticmethod
    def _parse_ts(date_str: str, time_str: str) -> datetime:
        d = CSVBarLoader._parse_date(date_str) or date.today()
        try:
            t = datetime.strptime(time_str.strip(), "%H:%M").time()
        except Exception:
            t = time(10, 0)
        return datetime.combine(d, t)
