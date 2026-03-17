# ============================================================
# strategy/core/bt_metrics.py
# Backtest Performans Metrikleri
#
# Hesaplanan metrikler:
#   Temel    : WR, AvgTrade, TotalReturn, TradeCount
#   Risk     : MaxDrawdown (equity curve), AvgR, WorstTrade
#   Kalite   : ProfitFactor, Expectancy, Sharpe, Sortino
#   Dağılım  : Kazanan/Kaybeden avg, setup bazlı breakdown
#   Maliyet  : Toplam komisyon, slippage
# ============================================================
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

from strategy.core.bt_models import TradeLog, ExitReason


# ── Metrik Dataclass'ları ─────────────────────────────────────────────────────

@dataclass
class SymbolMetrics:
    """Tek sembol için metrikler."""
    symbol: str

    # Hacim
    trade_count:  int   = 0
    win_count:    int   = 0
    loss_count:   int   = 0

    # Oran
    win_rate:     float = 0.0   # 0-1

    # Getiri (TL bazlı)
    total_net_pnl:    float = 0.0
    total_gross_pnl:  float = 0.0
    total_commission: float = 0.0
    total_slippage:   float = 0.0
    avg_trade_pct:    float = 0.0
    avg_win_pct:      float = 0.0
    avg_loss_pct:     float = 0.0
    best_trade_pct:   float = 0.0
    worst_trade_pct:  float = 0.0

    # Risk
    profit_factor:    float = 0.0   # Gross Win / |Gross Loss|
    expectancy_pct:   float = 0.0   # WR*AvgWin - (1-WR)*|AvgLoss|
    avg_r:            float = 0.0   # Net PnL / Initial Risk
    max_dd_pct:       float = 0.0   # Equity curve peak-to-trough (%)

    # Kalite
    sharpe_ratio:     float = 0.0
    sortino_ratio:    float = 0.0

    # Exit dağılımı
    stop_exits:       int   = 0
    trailing_exits:   int   = 0
    target_exits:     int   = 0
    eod_exits:        int   = 0

    # Setup dağılımı
    by_setup: dict[str, dict] = field(default_factory=dict)
    by_regime: dict[str, dict] = field(default_factory=dict)

    # Süre
    avg_hold_minutes: float = 0.0


@dataclass
class PortfolioMetrics:
    """Tüm portföy için birleşik metrikler."""
    # Sermaye
    initial_capital:  float = 0.0
    final_equity:     float = 0.0
    total_return_pct: float = 0.0

    # Hacim
    total_trades:     int   = 0
    total_wins:       int   = 0
    win_rate:         float = 0.0

    # Getiri
    total_net_pnl:    float = 0.0
    total_commission: float = 0.0
    total_slippage:   float = 0.0
    avg_trade_pct:    float = 0.0
    best_trade_pct:   float = 0.0
    worst_trade_pct:  float = 0.0

    # Risk
    profit_factor:    float = 0.0
    expectancy_pct:   float = 0.0
    max_dd_pct:       float = 0.0
    max_dd_tl:        float = 0.0
    sharpe_ratio:     float = 0.0
    sortino_ratio:    float = 0.0

    # Exit dağılımı
    stop_exits:       int   = 0
    trailing_exits:   int   = 0
    target_exits:     int   = 0
    eod_exits:        int   = 0

    # Setup bazlı özet
    by_setup:  dict[str, dict] = field(default_factory=dict)
    by_regime: dict[str, dict] = field(default_factory=dict)

    # Günlük equity serisi (MaxDD için)
    equity_curve: list[tuple[str, float]] = field(default_factory=list)

    # Sembol bazlı
    by_symbol: dict[str, SymbolMetrics] = field(default_factory=dict)


# ── Metrik Hesaplayıcı ───────────────────────────────────────────────────────

class MetricsCalculator:
    """
    TradeLog listesinden tüm metrikleri hesaplar.

    Kullanım:
        calc = MetricsCalculator(initial_capital=100_000)
        sym_metrics  = calc.per_symbol(trades)
        port_metrics = calc.portfolio(trades, equity_curve)
    """

    def __init__(self, initial_capital: float = 100_000.0):
        self._capital = initial_capital

    # ── Sembol bazlı ────────────────────────────────────────────────────────

    def per_symbol(self, trades: list[TradeLog]) -> dict[str, SymbolMetrics]:
        """Her sembol için ayrı metrik üret."""
        grouped: dict[str, list[TradeLog]] = {}
        for t in trades:
            grouped.setdefault(t.symbol, []).append(t)

        return {sym: self._symbol_metrics(sym, tl)
                for sym, tl in grouped.items()}

    def _symbol_metrics(self, symbol: str, trades: list[TradeLog]) -> SymbolMetrics:
        if not trades:
            return SymbolMetrics(symbol=symbol)

        m = SymbolMetrics(symbol=symbol)
        m.trade_count  = len(trades)
        m.win_count    = sum(1 for t in trades if t.is_winner)
        m.loss_count   = m.trade_count - m.win_count
        m.win_rate     = m.win_count / m.trade_count

        # PnL
        m.total_net_pnl    = sum(t.net_pnl_tl    for t in trades)
        m.total_gross_pnl  = sum(t.gross_pnl_tl  for t in trades)
        m.total_commission = sum(t.commission_tl  for t in trades)
        m.total_slippage   = sum(t.slippage_tl    for t in trades)

        pnl_pcts = [t.pnl_pct for t in trades]
        m.avg_trade_pct = statistics.mean(pnl_pcts)
        m.best_trade_pct  = max(pnl_pcts)
        m.worst_trade_pct = min(pnl_pcts)

        wins  = [t.pnl_pct for t in trades if t.is_winner]
        losses= [t.pnl_pct for t in trades if not t.is_winner]
        m.avg_win_pct  = statistics.mean(wins)   if wins   else 0.0
        m.avg_loss_pct = statistics.mean(losses) if losses else 0.0

        # Profit factor
        gross_win  = sum(t.gross_pnl_tl for t in trades if t.gross_pnl_tl > 0)
        gross_loss = sum(abs(t.gross_pnl_tl) for t in trades if t.gross_pnl_tl < 0)
        m.profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

        # Expectancy
        m.expectancy_pct = (
            m.win_rate * m.avg_win_pct -
            (1 - m.win_rate) * abs(m.avg_loss_pct)
        )

        # Avg R (initial risk bazlı)
        r_multiples = []
        for t in trades:
            if t.initial_risk > 0:
                r_multiples.append(t.net_pnl_tl / t.initial_risk)
        m.avg_r = statistics.mean(r_multiples) if r_multiples else 0.0

        # Sharpe (trade başına PnL serisi üzerinden)
        m.sharpe_ratio  = self._sharpe(pnl_pcts)
        m.sortino_ratio = self._sortino(pnl_pcts)

        # MaxDD (sembol equity eğrisi)
        m.max_dd_pct = self._max_dd_pct(pnl_pcts)

        # Exit dağılımı
        for t in trades:
            if   t.exit_reason == ExitReason.STOP_LOSS:     m.stop_exits     += 1
            elif t.exit_reason == ExitReason.TRAILING_STOP: m.trailing_exits += 1
            elif t.exit_reason == ExitReason.TARGET:        m.target_exits   += 1
            elif t.exit_reason == ExitReason.END_OF_DAY:    m.eod_exits      += 1

        # Hold süresi
        m.avg_hold_minutes = statistics.mean(t.hold_minutes for t in trades)

        # Setup breakdown
        m.by_setup  = self._breakdown(trades, key="setup_type")
        m.by_regime = self._breakdown(trades, key="regime_mode")

        return m

    # ── Portföy bazlı ───────────────────────────────────────────────────────

    def portfolio(
        self,
        trades: list[TradeLog],
        equity_curve: list[tuple[str, float]],   # [(date_str, equity), ...]
        initial_capital: float | None = None,
    ) -> PortfolioMetrics:
        capital = initial_capital or self._capital

        if not trades:
            p = PortfolioMetrics(initial_capital=capital, final_equity=capital)
            p.equity_curve = equity_curve
            return p

        p = PortfolioMetrics(initial_capital=capital)
        p.equity_curve    = equity_curve
        p.total_trades    = len(trades)
        p.total_wins      = sum(1 for t in trades if t.is_winner)
        p.win_rate        = p.total_wins / p.total_trades

        p.total_net_pnl    = sum(t.net_pnl_tl    for t in trades)
        p.total_commission = sum(t.commission_tl  for t in trades)
        p.total_slippage   = sum(t.slippage_tl    for t in trades)

        pnl_pcts = [t.pnl_pct for t in trades]
        p.avg_trade_pct   = statistics.mean(pnl_pcts)
        p.best_trade_pct  = max(pnl_pcts)
        p.worst_trade_pct = min(pnl_pcts)

        gross_win  = sum(t.gross_pnl_tl for t in trades if t.gross_pnl_tl > 0)
        gross_loss = sum(abs(t.gross_pnl_tl) for t in trades if t.gross_pnl_tl < 0)
        p.profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

        wins   = [t.pnl_pct for t in trades if t.is_winner]
        losses = [t.pnl_pct for t in trades if not t.is_winner]
        avg_w  = statistics.mean(wins)   if wins   else 0.0
        avg_l  = statistics.mean(losses) if losses else 0.0
        p.expectancy_pct = p.win_rate * avg_w - (1 - p.win_rate) * abs(avg_l)

        # Equity curve bazlı MaxDD
        if equity_curve:
            equities = [e for _, e in equity_curve]
            p.final_equity     = equities[-1]
            p.total_return_pct = (p.final_equity / capital - 1) * 100
            p.max_dd_pct, p.max_dd_tl = self._max_dd_equity(equities, capital)
        else:
            p.final_equity     = capital + p.total_net_pnl
            p.total_return_pct = p.total_net_pnl / capital * 100

        # Sharpe / Sortino (günlük equity getirileri üzerinden)
        if len(equity_curve) >= 2:
            daily_rets = [
                (equity_curve[i][1] / equity_curve[i-1][1]) - 1
                for i in range(1, len(equity_curve))
            ]
            p.sharpe_ratio  = self._sharpe(daily_rets, annualize=True)
            p.sortino_ratio = self._sortino(daily_rets, annualize=True)
        else:
            p.sharpe_ratio  = self._sharpe(pnl_pcts)
            p.sortino_ratio = self._sortino(pnl_pcts)

        # Exit dağılımı
        for t in trades:
            if   t.exit_reason == ExitReason.STOP_LOSS:     p.stop_exits     += 1
            elif t.exit_reason == ExitReason.TRAILING_STOP: p.trailing_exits += 1
            elif t.exit_reason == ExitReason.TARGET:        p.target_exits   += 1
            elif t.exit_reason == ExitReason.END_OF_DAY:    p.eod_exits      += 1

        p.by_setup  = self._breakdown(trades, key="setup_type")
        p.by_regime = self._breakdown(trades, key="regime_mode")

        # Sembol bazlı
        p.by_symbol = self.per_symbol(trades)

        return p

    # ── İstatistik yardımcıları ──────────────────────────────────────────────

    @staticmethod
    def _sharpe(
        returns: list[float],
        risk_free: float = 0.0,
        annualize: bool = False,
    ) -> float:
        if len(returns) < 2:
            return 0.0
        mu  = statistics.mean(returns) - risk_free
        std = statistics.stdev(returns)
        if std == 0:
            return 0.0
        ratio = mu / std
        return round(ratio * math.sqrt(252) if annualize else ratio, 3)

    @staticmethod
    def _sortino(
        returns: list[float],
        target: float = 0.0,
        annualize: bool = False,
    ) -> float:
        if len(returns) < 2:
            return 0.0
        mu = statistics.mean(returns) - target
        neg = [r for r in returns if r < target]
        if not neg:
            return float("inf")
        downside_std = math.sqrt(sum((r - target) ** 2 for r in neg) / len(returns))
        if downside_std == 0:
            return 0.0
        ratio = mu / downside_std
        return round(ratio * math.sqrt(252) if annualize else ratio, 3)

    @staticmethod
    def _max_dd_pct(pnl_pcts: list[float]) -> float:
        """Trade bazlı bileşik equity eğrisinden MaxDD %."""
        equity = 100.0; peak = 100.0; dd = 0.0
        for p in pnl_pcts:
            equity *= (1 + p / 100)
            if equity > peak: peak = equity
            drop = (peak - equity) / peak * 100
            if drop > dd: dd = drop
        return round(dd, 3)

    @staticmethod
    def _max_dd_equity(
        equities: list[float],
        initial: float,
    ) -> tuple[float, float]:
        """Gerçek equity eğrisinden MaxDD (% ve TL)."""
        peak = initial; dd_pct = 0.0; dd_tl = 0.0
        for e in equities:
            if e > peak: peak = e
            drop_tl  = peak - e
            drop_pct = drop_tl / peak * 100
            if drop_pct > dd_pct:
                dd_pct = drop_pct
                dd_tl  = drop_tl
        return round(dd_pct, 3), round(dd_tl, 2)

    @staticmethod
    def _breakdown(trades: list[TradeLog], key: str) -> dict[str, dict]:
        """Setup veya regime bazlı performans tablosu."""
        groups: dict[str, list[TradeLog]] = {}
        for t in trades:
            k = getattr(t, key, "?")
            groups.setdefault(k, []).append(t)

        result = {}
        for k, tl in groups.items():
            wins = [t for t in tl if t.is_winner]
            result[k] = {
                "trades":   len(tl),
                "wins":     len(wins),
                "win_rate": round(len(wins) / len(tl), 3),
                "avg_pnl":  round(statistics.mean(t.pnl_pct for t in tl), 4),
                "total_pnl":round(sum(t.net_pnl_tl for t in tl), 2),
            }
        return result
