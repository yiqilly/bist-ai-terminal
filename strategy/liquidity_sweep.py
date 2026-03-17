# ============================================================
# strategy/liquidity_sweep.py
# Liquidity Sweep Detector
#
# False breakoutları tespit eder.
# Sweep: fiyat önemli seviyeyi aşar → hızla geri döner.
# Bu genellikle smart money'nin piyasayı "süpürmesi"dir.
#
# Tespit edilen sweep durumları:
#   NONE           → sweep yok, normal hareket
#   BEAR_SWEEP     → düşük seviye süpürüldü, yukarı döndü (bullish)
#   BULL_SWEEP     → yüksek seviye süpürüldü, aşağı döndü (bearish)
#   FAKE_BREAKOUT  → breakout oluştu ama geri döndü (bearish)
#
# BEAR_SWEEP + pullback → güçlü al fırsatı sinyali
# FAKE_BREAKOUT         → breakout sinyallerini filtrele
# ============================================================
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from data.models import BarData


@dataclass
class SweepResult:
    sweep_type:  str   = "NONE"    # NONE | BEAR_SWEEP | BULL_SWEEP | FAKE_BREAKOUT
    detected:    bool  = False
    spike_ratio: float = 0.0       # hacim spike oranı (sweep barının volume / ort. volume)
    revert_pct:  float = 0.0       # geri dönüş % (sweep sonrası kapanış ne kadar döndü)
    level_swept: float = 0.0       # süpürülen fiyat seviyesi
    label:       str   = "—"

    @property
    def is_bullish_setup(self) -> bool:
        """BEAR_SWEEP: düşük süpürüldü → bullish setup."""
        return self.detected and self.sweep_type == "BEAR_SWEEP"

    @property
    def is_fake_breakout(self) -> bool:
        return self.detected and self.sweep_type == "FAKE_BREAKOUT"

    @property
    def setup_bonus(self) -> float:
        """Opportunity score için bonus: bullish sweep → +1.0"""
        if self.is_bullish_setup and self.spike_ratio >= 1.5:
            return 1.0
        if self.is_bullish_setup:
            return 0.5
        return 0.0


class LiquiditySweepDetector:
    """
    Son N bar'ı analiz ederek liquidity sweep tespiti yapar.

    Kullanım:
        detector = LiquiditySweepDetector()
        result   = detector.detect(bars, current_price)
    """

    def __init__(
        self,
        lookback:          int   = 5,    # kaç bar geriye bak
        spike_threshold:   float = 1.4,  # hacim spike için: current_vol / avg_vol
        revert_threshold:  float = 0.4,  # geri dönüş eşiği % olarak
        min_sweep_pct:     float = 0.15, # minimum sweep mesafesi %
    ):
        self._lookback   = lookback
        self._spike      = spike_threshold
        self._revert     = revert_threshold
        self._min_sweep  = min_sweep_pct / 100.0

    def detect(
        self,
        bars: list[BarData],
        current_price: float | None = None,
    ) -> SweepResult:
        """
        Son N bar'ı analiz et.

        bars: son barlar (eskiden yeniye sıralı)
        current_price: anlık fiyat (opsiyonel, son bar close olarak kullanılır)
        """
        if len(bars) < 3:
            return SweepResult()

        # Son N bar
        recent = bars[-self._lookback:] if len(bars) >= self._lookback else bars
        last   = bars[-1]
        price  = current_price or last.close

        # Ortalama hacim
        avg_vol = sum(b.volume for b in recent) / len(recent) if recent else 0
        if avg_vol <= 0:
            return SweepResult()

        # ── Bear Sweep Tespiti ────────────────────────────────
        # Son bar: düşük seviyeyi kırdı, kapanışta geri döndü
        # Yani: low < önceki n-bar minimum LOW
        #       close > bar'ın low'unun yakınında değil
        prev_bars = bars[-(self._lookback + 1):-1] if len(bars) > self._lookback else bars[:-1]
        if prev_bars:
            prev_low = min(b.low for b in prev_bars)
            prev_high = max(b.high for b in prev_bars)

            bar_range = last.high - last.low
            if bar_range > 0:
                # Bear sweep: son bar prev_low'u süpürdü
                if last.low < prev_low * (1 - self._min_sweep):
                    revert_pct = (last.close - last.low) / bar_range * 100
                    spike_ratio = last.volume / avg_vol if avg_vol > 0 else 1.0
                    if revert_pct >= self._revert * 100:
                        return SweepResult(
                            sweep_type  = "BEAR_SWEEP",
                            detected    = True,
                            spike_ratio = round(spike_ratio, 2),
                            revert_pct  = round(revert_pct, 1),
                            level_swept = round(prev_low, 2),
                            label       = f"🔍 Bear Sweep — hacim {spike_ratio:.1f}x",
                        )

                # Fake breakout: son bar prev_high'ı geçti, kapanışta geri döndü
                if last.high > prev_high * (1 + self._min_sweep):
                    revert_pct = (last.high - last.close) / bar_range * 100
                    spike_ratio = last.volume / avg_vol if avg_vol > 0 else 1.0
                    if revert_pct >= self._revert * 100 and spike_ratio >= self._spike:
                        return SweepResult(
                            sweep_type  = "FAKE_BREAKOUT",
                            detected    = True,
                            spike_ratio = round(spike_ratio, 2),
                            revert_pct  = round(revert_pct, 1),
                            level_swept = round(prev_high, 2),
                            label       = f"⚠ Sahte Kırılım — {spike_ratio:.1f}x hacim",
                        )

                # Bull sweep: son bar prev_high'ı geçti, geri dönüş olmadı
                # (bu bullish confirmation, sweep değil — bonus yok)

        return SweepResult()

    def detect_from_candidate(
        self,
        price: float,
        high_day: float,
        low_day: float,
        volume: float,
        avg_volume: float = 0.0,
    ) -> SweepResult:
        """
        Bar verisi yokken sadece anlık veriyle hızlı tespit.
        SnapshotCache'den gelen verilerle çalışır.
        """
        if avg_volume <= 0:
            return SweepResult()

        spike_ratio = volume / avg_volume

        # Day range içindeki pozisyon
        day_range = high_day - low_day
        if day_range <= 0:
            return SweepResult()

        pos_in_range = (price - low_day) / day_range   # 0-1 arası

        # Gün içinde süpürme: düşük nokta yakınında açık, yükseldi
        if pos_in_range > 0.70 and spike_ratio >= self._spike:
            revert_pct = pos_in_range * 100
            return SweepResult(
                sweep_type  = "BEAR_SWEEP",
                detected    = True,
                spike_ratio = round(spike_ratio, 2),
                revert_pct  = round(revert_pct, 1),
                level_swept = round(low_day, 2),
                label       = f"🔍 İntraday Sweep — {spike_ratio:.1f}x",
            )

        return SweepResult()
