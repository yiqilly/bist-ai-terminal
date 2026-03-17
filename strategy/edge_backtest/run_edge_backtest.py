#!/usr/bin/env python3
# ============================================================
# strategy/edge_backtest/run_edge_backtest.py
# Edge-Based BIST Backtest — CLI Runner
#
# Usage:
#   python -m strategy.edge_backtest.run_edge_backtest
#   python -m strategy.edge_backtest.run_edge_backtest --capital 200000
# ============================================================
from __future__ import annotations

import argparse
import sys
import os
import pandas as pd
from datetime import date, timedelta

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from strategy.edge_backtest.daily_data import load_index_and_universe, download_daily
from strategy.edge_backtest.edge_signals import scan_universe, RS_THRESHOLD, VOL_THRESHOLD, CONSOLIDATION_THRESHOLD
from strategy.edge_backtest.trade_simulator import TradeSimulator, SimConfig


def parse_args():
    p = argparse.ArgumentParser(description="BIST Edge-Based Backtest")
    p.add_argument("--days", type=int, default=365, help="Lookback days (default: 365)")
    p.add_argument("--capital", type=float, default=50_000, help="Initial capital TL")
    p.add_argument("--risk", type=float, default=1.5, help="Risk per trade %%")
    p.add_argument("--max-pos", type=int, default=5, help="Max concurrent positions")
    p.add_argument("--max-hold", type=int, default=45, help="Max hold days")
    p.add_argument("--atr-stop", type=float, default=2.0, help="ATR stop multiplier")
    p.add_argument("--atr-trail", type=float, default=2.5, help="ATR trailing multiplier")
    p.add_argument("--no-cache", action="store_true", help="Force re-download data")
    p.add_argument("--verbose", action="store_true", help="Show trade log")
    p.add_argument("--universe", type=str, default="BIST100",
                   choices=["BIST30", "BIST50", "BIST100"],
                   help="Symbol universe")
    return p.parse_args()


def get_universe_symbols(name: str) -> list[str]:
    from data.symbols import BIST30, BIST50, BIST100
    return {"BIST30": BIST30, "BIST50": BIST50, "BIST100": BIST100}[name]

def compute_historical_sector_momentum(stock_data: dict[str, pd.DataFrame], index_df: pd.DataFrame) -> pd.DataFrame:
    import pandas as pd
    from data.sector_map import get_sector
    
    symbols = list(stock_data.keys())
    sector_map = {sym: get_sector(sym) for sym in symbols}
    
    # 1. Compute 20d returns for all stocks
    returns_list = []
    for sym, df in stock_data.items():
        ret20 = df["Close"].pct_change(20)
        ret20.name = sym
        returns_list.append(ret20)
        
    all_ret = pd.concat(returns_list, axis=1) # index is Date, columns are symbols
    
    # 2. Group by sector
    sectors = set(sector_map.values())
    if "Bilinmiyor" in sectors:
        sectors.remove("Bilinmiyor")
        
    sector_returns = pd.DataFrame(index=all_ret.index)
    for sec in sectors:
        sec_syms = [s for s, s_sec in sector_map.items() if s_sec == sec and s in all_ret.columns]
        if sec_syms:
            sector_returns[sec] = all_ret[sec_syms].mean(axis=1)
            
    # 3. Index Return
    idx_ret20 = index_df["Close"].pct_change(20)
    
    # 4. Create Boolean Mask: Is Sector Strong?
    # Strong = (Sector Return > 0) AND (Sector Return > Index Return OR Sector in Top 50%)
    is_strong = pd.DataFrame(False, index=sector_returns.index, columns=sector_returns.columns)
    
    for date in is_strong.index:
        row = sector_returns.loc[date].dropna()
        if row.empty:
            continue
            
        i_ret = idx_ret20.loc[date] if date in idx_ret20.index else 0
        median_ret = row.median()
        
        # Determine strong sectors on this date
        strong_secs = row[(row > 0) & ((row > i_ret) | (row >= median_ret))].index
        for s in strong_secs:
            is_strong.loc[date, s] = True
            
    return is_strong, sector_map


def main():
    args = parse_args()
    end = date.today()
    start = end - timedelta(days=args.days + 60)  # extra 60 days for indicator warmup

    W = 72
    _line = "=" * W
    _sep = "-" * W

    print(f"\n{_line}")
    print(f"{'BIST EDGE-BASED BACKTEST':^{W}}")
    print(_line)
    print(f"  Universe       : {args.universe}")
    print(f"  Period         : {end - timedelta(days=args.days)} -> {end} ({args.days} days)")
    print(f"  Capital        : TL{args.capital:,.0f}")
    print(f"  Risk/Trade     : %{args.risk}")
    print(f"  Max Positions  : {args.max_pos}")
    print(f"  Max Hold       : {args.max_hold} days")
    print(f"  Stop           : {args.atr_stop}x ATR")
    print(f"  Trailing Stop  : {args.atr_trail}x ATR")
    print(f"\n  Edge Criteria:")
    print(f"    RS vs XU100  : > {RS_THRESHOLD}")
    print(f"    Volume Exp.  : > {VOL_THRESHOLD}x avg")
    print(f"    Consolidation: ATR/Close < {CONSOLIDATION_THRESHOLD}")
    print(f"    Breakout     : Close > 20-day High")
    print(_line)

    # ── 1. Data Download ─────────────────────────────────────
    print(f"\n{'PHASE 1: DATA DOWNLOAD':^{W}}")
    print(_sep)

    symbols = get_universe_symbols(args.universe)
    index_df, stock_data = load_index_and_universe(
        start=start, end=end,
        universe=symbols,
        cache=not args.no_cache,
    )

    print(f"  Index : {'OK' if not index_df.empty else 'FAIL'} XU100 ({len(index_df)} bars)")
    print(f"  Stocks: {len(stock_data)} symbols loaded")

    if not stock_data:
        print("\n  [X] No data available. Check internet connection.")
        return

    # If index failed, use equal-weight proxy
    if index_df.empty:
        print("  -> Building equal-weight index proxy...")
        closes = pd.DataFrame({sym: df["Close"] for sym, df in stock_data.items()})
        index_df = pd.DataFrame({"Close": closes.mean(axis=1)})
        # Add OHLV for compatibility
        index_df["Open"] = index_df["Close"]
        index_df["High"] = index_df["Close"]
        index_df["Low"] = index_df["Close"]
        index_df["Volume"] = 0

    # ── 2. Edge Signal Scan ──────────────────────────────────
    print(f"\n{'PHASE 2: EDGE SIGNAL SCAN':^{W}}")
    print(_sep)

    signals = scan_universe(stock_data, index_df)

    if signals.empty:
        print("  [X] No edge signals found with current thresholds.")
        print("  Try relaxing: RS > 1.2, Volume > 2.5x")
        return

    # Filter signals to the actual backtest period (not warmup)
    bt_start = end - timedelta(days=args.days)
    signals = signals[signals.index.date >= bt_start]

    # ── Market Trend Filter ──────────────────────────────
    # Only keep signals on days where XU100 Close > SMA(50)
    print("  -> Applying Market Trend Filter (XU100 > 50-day SMA)...")
    index_df["sma50"] = index_df["Close"].rolling(50, min_periods=50).mean()
    uptrend_dates = index_df[index_df["Close"] > index_df["sma50"]].index
    
    initial_signal_count = len(signals)
    signals = signals[signals.index.isin(uptrend_dates)]
    print(f"  -> Dropped {initial_signal_count - len(signals)} signals due to index downtrend.")
    
    # ── Sector Momentum Filter ───────────────────────────
    print("  -> Applying Historical Sector Momentum Filter...")
    is_strong_sector, sector_map = compute_historical_sector_momentum(stock_data, index_df)
    
    def is_signal_valid(row):
        date = row.name
        sym = row["symbol"]
        sec = sector_map.get(sym, "Bilinmiyor")
        
        # If sector unknown or date not in strong mask, accept it conditionally or reject it.
        if sec == "Bilinmiyor" or date not in is_strong_sector.index:
            return True # Don't penalize unmapped stocks
            
        # Is the sector strong on this date?
        return is_strong_sector.loc[date, sec]
        
    initial_signal_count = len(signals)
    mask = signals.apply(is_signal_valid, axis=1)
    signals = signals[mask]
    print(f"  -> Dropped {initial_signal_count - len(signals)} signals due to weak sector momentum.")

    n_signals = len(signals)
    n_symbols = signals["symbol"].nunique() if not signals.empty else 0
    print(f"  Signals found : {n_signals}")
    print(f"  Unique symbols: {n_symbols}")

    if n_signals > 0:
        # Top symbols by signal count
        top_syms = signals["symbol"].value_counts().head(10)
        print(f"\n  Top Signal Symbols:")
        for sym, cnt in top_syms.items():
            print(f"    {sym:<10} {cnt:>3} signals")

    # ── 3. Trade Simulation (Unified Shared Capital) ────────────
    print(f"\n{'PHASE 3: UNIFIED SIMULATION (DYNAMIC CASH)':^{W}}")
    print(_sep)
    
    # 3.1 Tag Core Signals
    if not signals.empty:
        signals["strategy_name"] = "core"
        signals["max_hold_days"] = args.max_hold
        signals["atr_stop_mult"] = args.atr_stop
        signals["atr_trail_mult"] = args.atr_trail

    # 3.2 Extract and Tag Swing Signals
    from strategy.edge_backtest.short_term_signals import scan_swing_universe
    print("  -> Scanning universe for Swing signals...")
    signals_swing = scan_swing_universe(stock_data, index_df)
    
    # Apply market trend and sector filters to swing
    if not signals_swing.empty:
        signals_swing = signals_swing[signals_swing.index.isin(uptrend_dates)]
        mask_swing = signals_swing.apply(is_signal_valid, axis=1)
        signals_swing = signals_swing[mask_swing]
        
        signals_swing["strategy_name"] = "swing"
        signals_swing["max_hold_days"] = 3
        signals_swing["atr_stop_mult"] = 1.0
        signals_swing["atr_trail_mult"] = 1.0

    print(f"  -> Swing signals found: {len(signals_swing) if not signals_swing.empty else 0}")

    # 3.3 Combine All Signals
    if signals_swing.empty:
        all_signals = signals
    elif signals.empty:
        all_signals = signals_swing
    else:
        all_signals = pd.concat([signals, signals_swing], ignore_index=False)
        
    # 3.4 Run Unified Simulator
    config = SimConfig(
        initial_capital=args.capital,
        risk_per_trade_pct=args.risk,
        max_positions=args.max_pos, # e.g. 5 slots. If 2 are full of Core, 3 can be Swing.
        max_hold_days=45, # Defaults (overridden by signal params)
    )
    print(f"\n  -> Running UNIFIED Simulator (Cap: TL{args.capital:,.0f}, Core+Swing)...")
    sim = TradeSimulator(config)
    result = sim.run(all_signals, stock_data)

    # ── 4. Report ────────────────────────────────────────────
    print(f"\n{_line}")
    print(f"{'UNIFIED SHARED-CAPITAL BACKTEST RESULTS':^{W}}")
    print(_line)
    
    print(f"\n  {'METRIC':<30} {'VALUE':>20}")
    print(f"  {_sep}")
    print(f"  {'Initial Capital':<30} {'TL' + f'{config.initial_capital:,.0f}':>20}")
    print(f"  {'Final Equity':<30} {'TL' + f'{result.final_equity:,.0f}':>20}")

    ret_str = f"{'+' if result.total_return_pct >= 0 else ''}{result.total_return_pct:.2f}%"
    print(f"  {'Total Return':<30} {ret_str:>20}")
    print(f"  {'Number of Trades':<30} {result.total_trades:>20}")
    print(f"  {'Win Rate':<30} {f'{result.win_rate:.1%}':>20}")
    print(f"  {'Profit Factor':<30} {f'{result.profit_factor:.3f}':>20}")
    print(f"  {'Max Drawdown':<30} {f'{result.max_drawdown_pct:.2f}% (TL{result.max_drawdown_tl:,.0f})':>20}")
    print(f"  {'Avg Hold Days':<30} {f'{result.avg_hold_days:.1f}':>20}")
    
    min_hold = min((t.hold_days for t in result.trades), default=0)
    max_hold = max((t.hold_days for t in result.trades), default=0)
    print(f"  {'Min/Max Hold Days':<30} {min_hold:>8} / {max_hold:<9}")

    # 5. Breakdown by Strategy
    core_trades = [t for t in result.trades if t.strategy_name == "core"]
    swing_trades = [t for t in result.trades if t.strategy_name == "swing"]
    
    print(f"\n  {'STRATEGY BREAKDOWN':<30}")
    print(f"  {'Strategy':<10} {'Trades':>8} {'Win%':>8} {'Avg PnL':>10}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*10}")
    for str_name, t_list in [("Core", core_trades), ("Swing", swing_trades)]:
        n = len(t_list)
        if n == 0:
            continue
        wr = sum(1 for t in t_list if t.is_winner) / n
        avg_pnl = sum(t.pnl_pct for t in t_list) / n
        print(f"  {str_name:<10} {n:>8} {wr:>8.1%} {avg_pnl:>+9.2f}%")

    combined_trades = result.trades
    total_trades = result.total_trades

    # Best / Worst Trade
    best = max(combined_trades, key=lambda t: t.pnl_pct, default=None)
    worst = min(combined_trades, key=lambda t: t.pnl_pct, default=None)
    if best:
        print(f"\n  {'BEST TRADE':<30}")
        print(f"    {best.symbol:<8} {str(best.entry_date):<12} -> {str(best.exit_date):<12}")
        print(f"    Entry: TL{best.entry_price:.2f}  Exit: TL{best.exit_price:.2f}  "
              f"PnL: {best.pnl_pct:+.2f}%  TL{best.pnl_net:,.0f}  ({best.exit_reason})")
    if worst:
        print(f"\n  {'WORST TRADE':<30}")
        print(f"    {worst.symbol:<8} {str(worst.entry_date):<12} -> {str(worst.exit_date):<12}")
        print(f"    Entry: TL{worst.entry_price:.2f}  Exit: TL{worst.exit_price:.2f}  "
              f"PnL: {worst.pnl_pct:+.2f}%  TL{worst.pnl_net:,.0f}  ({worst.exit_reason})")

    # Exit breakdown
    exits = {}
    for t in combined_trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
        
    if exits:
        print(f"\n  {'EXIT REASONS':<30}")
        for reason, count in sorted(exits.items(), key=lambda x: -x[1]):
            pct = count / max(total_trades, 1) * 100
            print(f"    {reason:<20} {count:>5}  ({pct:.1f}%)")

    # Per-symbol breakdown
    if combined_trades:
        print(f"\n  {'SYMBOL BREAKDOWN':<30}")
        print(f"  {'Symbol':<10} {'Trades':>6} {'WR':>7} {'AvgPnL':>8} {'TotalPnL':>12}")
        print(f"  {'-'*10} {'-'*6} {'-'*7} {'-'*8} {'-'*12}")

        sym_trades: dict[str, list] = {}
        for t in combined_trades:
            sym_trades.setdefault(t.symbol, []).append(t)

        sorted_syms = sorted(
            sym_trades.items(),
            key=lambda x: sum(t.pnl_net for t in x[1]),
            reverse=True,
        )

        for sym, trades in sorted_syms[:20]:
            n = len(trades)
            w = sum(1 for t in trades if t.is_winner)
            wr = w / n if n else 0
            avg_pnl = sum(t.pnl_pct for t in trades) / n
            total_pnl = sum(t.pnl_net for t in trades)
            print(f"  {sym:<10} {n:>6} {wr:>6.1%} {avg_pnl:>+7.2f}% {'TL' + f'{total_pnl:,.0f}':>12}")

    # Verbose trade log
    if args.verbose and combined_trades:
        print(f"\n  {'TRADE LOG':^{W}}")
        print(f"  {_sep}")
        print(f"  {'#':>4} {'Symbol':<8} {'Entry Date':<12} {'Exit Date':<12} "
              f"{'Entry':>8} {'Exit':>8} {'PnL%':>7} {'PnL TL':>10} {'Reason':<15}")
        for i, t in enumerate(sorted(combined_trades, key=lambda x: x.entry_date)):
            sign = "+" if t.pnl_pct >= 0 else ""
            print(f"  {i+1:>4} {t.symbol:<8} {str(t.entry_date):<12} "
                  f"{str(t.exit_date):<12} {t.entry_price:>8.2f} {t.exit_price:>8.2f} "
                  f"{sign}{t.pnl_pct:>6.2f}% {'TL' + f'{t.pnl_net:,.0f}':>10} {t.exit_reason:<15}")

    print(f"\n{_line}\n")


if __name__ == "__main__":
    main()
