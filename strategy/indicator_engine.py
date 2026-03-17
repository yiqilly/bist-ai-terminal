# ============================================================
# strategy/indicator_engine.py
# Merkezi İndikatör Hesaplama Motoru v1
# SnapshotCache'den bağımsız, ham veri üzerinde çalışır.
# ============================================================
import math
from typing import List, Optional

class IndicatorEngine:
    @staticmethod
    def ema(values: List[float], period: int) -> float:
        if not values or period <= 0:
            return 0.0
        if len(values) < period:
            return float(values[-1]) if values else 0.0
            
        k = 2.0 / (period + 1)
        ema = float(values[0])
        for val in values[1:]:
            ema = (float(val) * k) + (ema * (1 - k))
        return float(round(ema, 3))

    @staticmethod
    def rsi(values: List[float], period: int = 14) -> float:
        if len(values) < period + 1:
            return 50.0
            
        gains = 0.0
        losses = 0.0
        
        for i in range(1, period + 1):
            diff = float(values[i]) - float(values[i-1])
            if diff > 0:
                gains += diff
            else:
                losses -= diff
                
        avg_gain = gains / period
        avg_loss = losses / period
        
        if avg_loss == 0:
            return 100.0
            
        for i in range(period + 1, len(values)):
            diff = float(values[i]) - float(values[i-1])
            gain = max(diff, 0.0)
            loss = max(-diff, 0.0)
            
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
            
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(round(rsi, 2))

    @staticmethod
    def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        if len(closes) < 2:
            return float(highs[0]) - float(lows[0]) if highs else 1.0
            
        tr_list = []
        for i in range(1, len(closes)):
            tr = max(
                float(highs[i]) - float(lows[i]),
                abs(float(highs[i]) - float(closes[i-1])),
                abs(float(lows[i]) - float(closes[i-1]))
            )
            tr_list.append(tr)
            
        if not tr_list:
            return 1.0
            
        atr = sum(tr_list[:period]) / min(len(tr_list), period)
        for tr in tr_list[period:]:
            atr = (atr * (period - 1) + tr) / period
            
        return float(round(atr, 4))

    @staticmethod
    def boll(values: List[float], period: int = 20, std_dev: int = 2):
        if len(values) < period:
            return 0.0, 0.0, 0.0
            
        slice_vals = [float(x) for x in values[-period:]]
        sma = sum(slice_vals) / period
        variance = sum((x - sma) ** 2 for x in slice_vals) / period
        sd = math.sqrt(variance)
        
        upper = sma + (std_dev * sd)
        lower = sma - (std_dev * sd)
        return float(round(upper, 3)), float(round(sma, 3)), float(round(lower, 3))
