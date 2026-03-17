# ============================================================
# strategy/edge_backtest/trade_simulator.py
# Trade Simulator — Daily Timeframe
#
# Entry: next-day open after all 4 edge conditions fire
# Stop: entry - 2 × ATR(14)
# Trailing stop: highest - 1.5 × ATR(14)
# Max hold: 20 trading days
# Position sizing: fixed fractional (1.5% risk per trade)
# Max concurrent positions: 5
# Commission: 0.15% each way
# ============================================================
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd


# ── Configuration ────────────────────────────────────────────

@dataclass
class SimConfig:
    initial_capital: float = 50_000.0
    risk_per_trade_pct: float = 1.5    # percent of capital risked per trade
    max_positions: int = 5           # Reverted back to 5 (20%)
    max_hold_days: int = 45          # increased from 20 to allow trends
    atr_stop_mult: float = 2.0        # stop = entry - mult × ATR
    atr_trail_mult: float = 2.5       # widened from 1.5 to 2.5
    commission_pct: float = 0.0015    # 0.15% each way
    slippage_pct: float = 0.0005      # 0.05% each way


# ── Trade Record ─────────────────────────────────────────────

@dataclass
class Trade:
    trade_id: int
    symbol: str
    entry_date: date
    entry_price: float
    shares: int
    stop_price: float
    atr_at_entry: float
    exit_date: Optional[date] = None
    exit_price: float = 0.0
    exit_reason: str = ""
    highest_price: float = 0.0
    pnl_gross: float = 0.0
    pnl_net: float = 0.0
    pnl_pct: float = 0.0
    hold_days: int = 0
    commission: float = 0.0
    strategy_name: str = "core"

    @property
    def is_winner(self) -> bool:
        return self.pnl_net > 0


# ── Open Position Tracker ────────────────────────────────────

@dataclass
class OpenPosition:
    symbol: str
    entry_date: date
    entry_price: float
    shares: int
    stop_price: float
    atr: float
    highest_price: float = 0.0
    days_held: int = 0
    trade_id: int = 0
    strategy_name: str = "core"
    max_hold_days: int = 45
    atr_stop_mult: float = 2.0
    atr_trail_mult: float = 2.5

    def __post_init__(self):
        self.highest_price = self.entry_price


# ── Simulator ────────────────────────────────────────────────

class TradeSimulator:
    """
    Day-by-day trade simulator.

    Usage:
        sim = TradeSimulator(config)
        result = sim.run(signals_df, stock_data)
    """

    def __init__(self, config: Optional[SimConfig] = None):
        self.cfg = config or SimConfig()
        self.cash = self.cfg.initial_capital
        self.positions: dict[str, OpenPosition] = {}
        self.closed_trades: list[Trade] = []
        self.equity_curve: list[tuple[str, float]] = []
        self._trade_counter = 0

    def run(
        self,
        signals_df: pd.DataFrame,
        stock_data: dict[str, pd.DataFrame],
    ) -> SimResult:
        """
        Run the simulation day by day.

        signals_df: DataFrame with edge signals (index=date, columns include
                    'symbol', 'Close', 'atr', 'edge_active')
        stock_data: {symbol: DataFrame} with daily OHLCV
        """
        self.cash = self.cfg.initial_capital
        self.positions = {}
        self.closed_trades = []
        self.equity_curve = []
        self._trade_counter = 0

        # Collect all unique trading dates across all symbols
        all_dates = set()
        for sym, df in stock_data.items():
            all_dates.update(df.index.date)
        all_dates = sorted(all_dates)

        if not all_dates:
            return self._build_result()

        # Build signal lookup: {date: [(score, symbol, close, atr, strat, mhd, asm, atm), ...]}
        signal_dates: dict[date, list[tuple[float, str, float, float, str, int, float, float]]] = {}
        if not signals_df.empty:
            for idx, row in signals_df.iterrows():
                dt = idx.date() if hasattr(idx, 'date') else idx
                sym = row["symbol"]
                close = row["Close"]
                atr = row["atr"] if pd.notna(row.get("atr", np.nan)) else close * 0.02
                score = row.get("edge_score", 0.0)
                strat = row.get("strategy_name", "core")
                mhd = row.get("max_hold_days", self.cfg.max_hold_days)
                asm = row.get("atr_stop_mult", self.cfg.atr_stop_mult)
                atm = row.get("atr_trail_mult", self.cfg.atr_trail_mult)
                signal_dates.setdefault(dt, []).append((score, sym, close, atr, strat, mhd, asm, atm))

        # Day-by-day simulation
        for i, today in enumerate(all_dates):
            # 1. Manage existing positions
            self._manage_positions(today, stock_data)

            # 2. Check for new entries (signals from YESTERDAY → enter at today's open)
            if i > 0:
                yesterday = all_dates[i - 1]
                if yesterday in signal_dates:
                    # Sort today's signals by edge_score descending so we take the best first
                    daily_signals = signal_dates[yesterday]
                    daily_signals.sort(key=lambda x: x[0], reverse=True)
                    
                    for score, sym, sig_close, sig_atr, strat, mhd, asm, atm in daily_signals:
                        self._try_entry(sym, today, sig_atr, strat, mhd, asm, atm, stock_data)

            # 3. Record equity
            equity = self._compute_equity(today, stock_data)
            self.equity_curve.append((str(today), round(equity, 2)))

        # Force-close remaining positions at last available price
        self._force_close_all(all_dates[-1], stock_data)

        return self._build_result()

    # ── Entry ────────────────────────────────────────────────

    def _try_entry(
        self,
        symbol: str,
        today: date,
        signal_atr: float,
        strategy_name: str,
        max_hold: int,
        stop_mult: float,
        trail_mult: float,
        stock_data: dict[str, pd.DataFrame],
    ) -> None:
        """Try to open a position at today's open."""
        if symbol in self.positions:
            return
        if len(self.positions) >= self.cfg.max_positions:
            return

        df = stock_data.get(symbol)
        if df is None:
            return

        # Get today's data
        today_rows = df[df.index.date == today]
        if today_rows.empty:
            return

        today_bar = today_rows.iloc[0]
        open_price = today_bar["Open"]

        if open_price <= 0 or np.isnan(open_price):
            return

        # Apply slippage to entry
        fill_price = open_price * (1 + self.cfg.slippage_pct)

        # ATR for stop — use signal day ATR
        atr = signal_atr if signal_atr > 0 else fill_price * 0.02

        # Stop price
        stop = fill_price - stop_mult * atr

        # Position sizing: Fixed Fractional (Equity / Max Positions)
        # This fully deploys capital and compounds returns over time.
        current_equity = self._compute_equity(today, stock_data)
        target_allocation = current_equity / self.cfg.max_positions
        
        # We can only buy with available cash (apply 98% buffer to be safe against commissions)
        available_target = min(target_allocation, self.cash * 0.98)
        
        shares = math.floor(available_target / (fill_price * (1 + self.cfg.commission_pct)))
        if shares <= 0:
            return
            
        cost = fill_price * shares
        entry_commission = cost * self.cfg.commission_pct
        total_cost = cost + entry_commission

        self.cash -= total_cost
        self._trade_counter += 1

        self.positions[symbol] = OpenPosition(
            symbol=symbol,
            entry_date=today,
            entry_price=fill_price,
            shares=shares,
            stop_price=stop,
            atr=atr,
            trade_id=self._trade_counter,
            strategy_name=strategy_name,
            max_hold_days=max_hold,
            atr_stop_mult=stop_mult,
            atr_trail_mult=trail_mult
        )

    # ── Position Management ──────────────────────────────────

    def _manage_positions(
        self,
        today: date,
        stock_data: dict[str, pd.DataFrame],
    ) -> None:
        """Check stops, trailing stops, and max hold for all positions."""
        to_close: list[tuple[str, float, str]] = []

        for sym, pos in list(self.positions.items()):
            df = stock_data.get(sym)
            if df is None:
                continue

            today_rows = df[df.index.date == today]
            if today_rows.empty:
                pos.days_held += 1
                continue

            bar = today_rows.iloc[0]
            pos.days_held += 1

            high = bar["High"]
            low = bar["Low"]
            close = bar["Close"]

            # Update highest price
            if high > pos.highest_price:
                pos.highest_price = high

            # Trailing stop ONLY activates after price moves 1x ATR above entry
            # Before that, only the initial stop is used
            profit_atr = (pos.highest_price - pos.entry_price) / pos.atr if pos.atr > 0 else 0
            trailing_active = profit_atr >= 1.0
            
            if trailing_active:
                trailing_stop = pos.highest_price - pos.atr_trail_mult * pos.atr
                effective_stop = max(pos.stop_price, trailing_stop)
            else:
                effective_stop = pos.stop_price
                trailing_stop = 0  # not yet active

            # Check stop hit
            if low <= effective_stop:
                exit_price = max(effective_stop, bar["Open"])  # gap-down protection
                exit_price = min(exit_price, bar["High"])  # can't exit above high
                reason = "trailing_stop" if trailing_active and trailing_stop > pos.stop_price else "stop_loss"
                to_close.append((sym, exit_price, reason))
                continue

            # Max hold
            if pos.days_held >= pos.max_hold_days:
                to_close.append((sym, close, "max_hold"))
                continue

        # Close positions
        for sym, exit_price, reason in to_close:
            self._close_position(sym, today, exit_price, reason)

    def _close_position(
        self,
        symbol: str,
        exit_date: date,
        exit_price: float,
        reason: str,
    ) -> None:
        """Close a position and record the trade."""
        pos = self.positions.pop(symbol, None)
        if pos is None:
            return

        # Apply slippage + commission to exit
        fill_exit = exit_price * (1 - self.cfg.slippage_pct)
        exit_commission = fill_exit * pos.shares * self.cfg.commission_pct
        entry_commission = pos.entry_price * pos.shares * self.cfg.commission_pct

        gross_pnl = (fill_exit - pos.entry_price) * pos.shares
        total_commission = entry_commission + exit_commission
        net_pnl = gross_pnl - total_commission

        pnl_pct = (fill_exit / pos.entry_price - 1) * 100

        # Return cash
        self.cash += fill_exit * pos.shares - exit_commission

        trade = Trade(
            trade_id=pos.trade_id,
            symbol=symbol,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            shares=pos.shares,
            stop_price=pos.stop_price,
            atr_at_entry=pos.atr,
            exit_date=exit_date,
            exit_price=fill_exit,
            exit_reason=reason,
            highest_price=pos.highest_price,
            pnl_gross=round(gross_pnl, 2),
            pnl_net=round(net_pnl, 2),
            pnl_pct=round(pnl_pct, 4),
            hold_days=pos.days_held,
            commission=round(total_commission, 2),
            strategy_name=pos.strategy_name,
        )
        self.closed_trades.append(trade)

    def _force_close_all(
        self,
        last_date: date,
        stock_data: dict[str, pd.DataFrame],
    ) -> None:
        """Force close all remaining positions at last close."""
        for sym in list(self.positions.keys()):
            df = stock_data.get(sym)
            if df is not None and len(df) > 0:
                close = df["Close"].iloc[-1]
            else:
                close = self.positions[sym].entry_price
            self._close_position(sym, last_date, close, "end_of_backtest")

    # ── Equity ───────────────────────────────────────────────

    def _compute_equity(
        self,
        today: date,
        stock_data: dict[str, pd.DataFrame],
    ) -> float:
        """Current equity = cash + market value of open positions."""
        pos_value = 0.0
        for sym, pos in self.positions.items():
            df = stock_data.get(sym)
            if df is not None:
                today_rows = df[df.index.date == today]
                if not today_rows.empty:
                    pos_value += today_rows.iloc[0]["Close"] * pos.shares
                else:
                    pos_value += pos.highest_price * pos.shares
            else:
                pos_value += pos.entry_price * pos.shares
        return self.cash + pos_value

    # ── Result Builder ───────────────────────────────────────

    def _build_result(self) -> SimResult:
        return SimResult(
            trades=self.closed_trades,
            equity_curve=self.equity_curve,
            initial_capital=self.cfg.initial_capital,
            final_equity=self.equity_curve[-1][1] if self.equity_curve else self.cfg.initial_capital,
        )


# ── Result Dataclass ─────────────────────────────────────────

@dataclass
class SimResult:
    trades: list[Trade]
    equity_curve: list[tuple[str, float]]
    initial_capital: float
    final_equity: float

    # ── Computed Metrics ─────────────────────────────────────

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winners(self) -> list[Trade]:
        return [t for t in self.trades if t.is_winner]

    @property
    def losers(self) -> list[Trade]:
        return [t for t in self.trades if not t.is_winner]

    @property
    def win_rate(self) -> float:
        return len(self.winners) / self.total_trades if self.total_trades else 0.0

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity / self.initial_capital - 1) * 100

    @property
    def profit_factor(self) -> float:
        gross_wins = sum(t.pnl_gross for t in self.winners)
        gross_losses = sum(abs(t.pnl_gross) for t in self.losers)
        return gross_wins / gross_losses if gross_losses > 0 else float("inf")

    @property
    def max_drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.initial_capital
        max_dd = 0.0
        for _, eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 2)

    @property
    def max_drawdown_tl(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.initial_capital
        max_dd = 0.0
        for _, eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 2)

    @property
    def best_trade(self) -> Optional[Trade]:
        return max(self.trades, key=lambda t: t.pnl_pct) if self.trades else None

    @property
    def worst_trade(self) -> Optional[Trade]:
        return min(self.trades, key=lambda t: t.pnl_pct) if self.trades else None

    @property
    def avg_trade_pct(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.pnl_pct for t in self.trades) / len(self.trades)

    @property
    def avg_win_pct(self) -> float:
        w = self.winners
        return sum(t.pnl_pct for t in w) / len(w) if w else 0.0

    @property
    def avg_loss_pct(self) -> float:
        l = self.losers
        return sum(t.pnl_pct for t in l) / len(l) if l else 0.0

    @property
    def total_commission(self) -> float:
        return sum(t.commission for t in self.trades)

    @property
    def sharpe_ratio(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        import statistics
        daily_rets = []
        for i in range(1, len(self.equity_curve)):
            prev = self.equity_curve[i-1][1]
            curr = self.equity_curve[i][1]
            if prev > 0:
                daily_rets.append(curr / prev - 1)
        if len(daily_rets) < 2:
            return 0.0
        mu = statistics.mean(daily_rets)
        std = statistics.stdev(daily_rets)
        if std == 0:
            return 0.0
        return round(mu / std * (252 ** 0.5), 3)

    @property
    def expectancy(self) -> float:
        if not self.trades:
            return 0.0
        return self.win_rate * self.avg_win_pct - (1 - self.win_rate) * abs(self.avg_loss_pct)

    @property
    def avg_hold_days(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.hold_days for t in self.trades) / len(self.trades)

    @property
    def exit_breakdown(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for t in self.trades:
            result[t.exit_reason] = result.get(t.exit_reason, 0) + 1
        return result
