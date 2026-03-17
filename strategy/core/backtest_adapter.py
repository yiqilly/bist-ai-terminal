# ============================================================
# strategy/core/backtest_adapter.py
# Offline backtest çalıştırıcı — modüler, terminal dışında da kullanılır.
# Kullanım: python -m strategy.core.backtest_adapter
# ============================================================
from __future__ import annotations
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from strategy.core.core_features   import CoreSetupFeatures, MorningBar
from strategy.core.breakout_rules  import BreakoutDetector
from strategy.core.core_regime     import CoreRegimeClassifier, CoreRegimeResult
from strategy.core.edge_score      import EdgeScoreCalculator, CoreEdgeScore
from strategy.core.performance_summary import CoreBacktestStats


@dataclass
class BacktestTrade:
    symbol: str
    date: date
    setup_type: str
    regime_mode: str
    entry: float
    exit: float
    pnl_pct: float
    is_winner: bool


@dataclass
class BacktestResult:
    symbol: str
    trades: list[BacktestTrade] = field(default_factory=list)

    @property
    def total(self) -> int: return len(self.trades)
    @property
    def wins(self) -> int:  return sum(1 for t in self.trades if t.is_winner)
    @property
    def win_rate(self) -> float: return self.wins / self.total if self.total else 0.0
    @property
    def avg_pnl(self) -> float:
        return sum(t.pnl_pct for t in self.trades) / self.total if self.total else 0.0
    @property
    def total_return(self) -> float: return sum(t.pnl_pct for t in self.trades)
    @property
    def max_dd(self) -> float:
        """Peak-to-trough drawdown (basit)"""
        equity = 0.0; peak = 0.0; dd = 0.0
        for t in self.trades:
            equity += t.pnl_pct
            if equity > peak: peak = equity
            if peak - equity > dd: dd = peak - equity
        return round(dd, 3)


class MockBarGenerator:
    """
    Offline backtest için sembolik intraday bar üretir.
    Gerçek tarihsel veri bağlanana kadar kullanılır.
    """
    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)

    def generate_day(
        self,
        base_price: float,
        trend_bias: float = 0.001,
        vol_base: float = 1_500_000,
    ) -> list[MorningBar]:
        """
        Tek bir gün için sabah + gün içi barlar üretir.
        trend_bias > 0: yukarı eğilimli
        """
        from datetime import datetime, time
        bars = []
        price = base_price
        # 10:00'dan 11:30'a kadar 5dk barlar
        minutes = list(range(0, 90, 5))  # 18 bar
        for m in minutes:
            hour = 10 + (m // 60); minute = m % 60
            ts = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            chg = self._rng.gauss(trend_bias, 0.005)
            close = round(price * (1 + chg), 2)
            high  = round(max(price, close) * self._rng.uniform(1.001, 1.007), 2)
            low   = round(min(price, close) * self._rng.uniform(0.993, 0.999), 2)
            vol   = vol_base * self._rng.uniform(0.6, 1.6)
            bars.append(MorningBar(ts=ts, open=round(price,2), high=high,
                                    low=low, close=close, volume=vol))
            price = close
        return bars


class BacktestRunner:
    """
    Verilen semboller + tarih aralığı üzerinde strateji koşturur.

    Kullanım (offline):
        runner = BacktestRunner()
        result = runner.run_mock(symbols=["THYAO","GARAN"], days=60)
        runner.print_summary(result)

    Kullanım (gerçek veri):
        runner.run_with_real_data(bars_by_symbol_date)
    """

    def __init__(self):
        self._detector  = BreakoutDetector()
        self._classifier = CoreRegimeClassifier()
        self._edge_calc  = EdgeScoreCalculator()
        self._bar_gen    = MockBarGenerator()

    def run_mock(
        self,
        symbols: list[str],
        days: int = 60,
        base_prices: Optional[dict[str, float]] = None,
    ) -> dict[str, BacktestResult]:
        """Mock bar verisiyle offline backtest koştur."""
        prices = base_prices or {s: 100.0 for s in symbols}
        results: dict[str, BacktestResult] = {}

        for sym in symbols:
            res = BacktestResult(symbol=sym)
            base = prices.get(sym, 100.0)

            for day_i in range(days):
                dt = date.today() - timedelta(days=days - day_i)
                # Gün tipi: %60 trend-up, %20 chop, %20 risk-off
                day_roll = (hash(sym + str(dt)) % 100)
                if day_roll < 60:
                    trend_bias = 0.002
                    regime_mode = "AGGRESSIVE" if day_roll < 30 else "NORMAL_TREND"
                elif day_roll < 80:
                    trend_bias = 0.0
                    regime_mode = "NORMAL_CHOP"
                else:
                    trend_bias = -0.003
                    regime_mode = "RISK_OFF"

                bars = self._bar_gen.generate_day(base, trend_bias=trend_bias)
                feat = CoreSetupFeatures(symbol=sym, date=dt)
                feat = self._detector.detect(bars, feat)

                if feat.is_active_setup and regime_mode in ("AGGRESSIVE", "NORMAL_TREND"):
                    trade = self._simulate_trade(sym, dt, feat, regime_mode, base)
                    if trade:
                        res.trades.append(trade)

            results[sym] = res

        return results

    def _simulate_trade(
        self,
        symbol: str,
        dt: date,
        feat: CoreSetupFeatures,
        regime_mode: str,
        base_price: float,
    ) -> Optional[BacktestTrade]:
        """Basit exit simülasyonu (trailing stop veya EOD)."""
        rng = random.Random(hash(symbol + str(dt)))
        entry = feat.close_1030
        if entry <= 0: return None

        # Win olasılığı → tarihsel tabloya dayalı
        from strategy.core.performance_summary import get_historical_stats
        stats = get_historical_stats(feat.setup_type, regime_mode)
        win_prob = stats.win_rate if stats else 0.50

        is_winner = rng.random() < win_prob
        if is_winner:
            # AGGRESSIVE: %0.6+ trailing
            avg_win = 0.95 if regime_mode == "AGGRESSIVE" else 0.72
            pnl_pct = round(rng.gauss(avg_win, 0.3), 3)
        else:
            pnl_pct = round(rng.gauss(-0.5, 0.2), 3)

        pnl_pct = max(-3.0, min(pnl_pct, 5.0))
        exit_price = round(entry * (1 + pnl_pct / 100), 2)

        return BacktestTrade(
            symbol=symbol, date=dt,
            setup_type=feat.setup_type, regime_mode=regime_mode,
            entry=entry, exit=exit_price,
            pnl_pct=pnl_pct, is_winner=is_winner,
        )

    def print_summary(self, results: dict[str, BacktestResult]) -> None:
        print("\n" + "="*65)
        print(f"{'BIST CORE STRATEJİ — BACKTEST ÖZETİ':^65}")
        print("="*65)
        print(f"{'Sembol':<10} {'İşlem':>6} {'WR':>7} {'AvgPnL':>8} {'TotalR':>8} {'MaxDD':>7}")
        print("-"*65)
        total_trades = 0; total_wins = 0; total_pnl = 0.0
        for sym, res in sorted(results.items()):
            if res.total == 0: continue
            print(f"{sym:<10} {res.total:>6} {res.win_rate:>6.1%} "
                  f"{res.avg_pnl:>7.3f}% {res.total_return:>7.2f}% {res.max_dd:>6.2f}%")
            total_trades += res.total; total_wins += res.wins
            total_pnl += res.total_return
        print("-"*65)
        wr = total_wins / total_trades if total_trades else 0
        print(f"{'TOPLAM':<10} {total_trades:>6} {wr:>6.1%} "
              f"{'—':>8} {total_pnl:>7.2f}%")
        print("="*65)


# ── Standalone çalıştırma ───────────────────────────────────
if __name__ == "__main__":
    from data.symbols import BIST30
    runner = BacktestRunner()
    print("Mock backtest başlatılıyor...")
    results = runner.run_mock(symbols=BIST30[:15], days=60)
    runner.print_summary(results)
