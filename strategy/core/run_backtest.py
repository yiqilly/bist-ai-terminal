#!/usr/bin/env python3
# ============================================================
# strategy/core/run_backtest.py
# Standalone Backtest Çalıştırıcı
#
# Kullanım:
#   python strategy/core/run_backtest.py
#   python strategy/core/run_backtest.py --days 120 --bars 1 --capital 200000
#   python strategy/core/run_backtest.py --csv path/to/file.csv
#
# Parametreler:
#   --days     : Kaç günlük sentetik veri (varsayılan: 90)
#   --bars     : Bar boyutu dakika — 1 veya 5 (varsayılan: 5)
#   --capital  : Başlangıç sermayesi TL (varsayılan: 100000)
#   --risk     : Trade başına risk % (varsayılan: 1.0)
#   --stop     : Stop mesafesi % (varsayılan: 0.6)
#   --target   : R/R oranı (varsayılan: 2.5)
#   --trailing : Trailing mesafesi % (varsayılan: 0.6)
#   --symbols  : Virgülle ayrılmış semboller (varsayılan: BIST30)
#   --csv      : CSV dosya yolu (verilirse sentetik devre dışı)
#   --verbose  : Trade logunu göster
#   --save-csv : Trade logunu dosyaya kaydet
# ============================================================
from __future__ import annotations

import argparse
import sys
import os
from datetime import date, timedelta

# Proje kökünü path'e ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from strategy.core.bt_runner import BacktestRunner, BacktestConfig
from strategy.core.bt_models import ExecutionConfig, SizingConfig, StopConfig
from data.symbols import BIST30


def parse_args():
    p = argparse.ArgumentParser(description="BIST Core Strategy Backtest")
    p.add_argument("--days",     type=int,   default=90)
    p.add_argument("--bars",     type=int,   default=5,       choices=[1, 5])
    p.add_argument("--capital",  type=float, default=100_000)
    p.add_argument("--risk",     type=float, default=1.0,
                   help="Trade başına risk yüzdesi")
    p.add_argument("--stop",     type=float, default=0.6,
                   help="Stop mesafesi yüzdesi (0.6 = %%0.6)")
    p.add_argument("--target",   type=float, default=2.5,
                   help="R/R oranı")
    p.add_argument("--trailing", type=float, default=0.6,
                   help="Trailing stop mesafesi %%")
    p.add_argument("--symbols",  type=str,   default="",
                   help="Virgülle ayrılmış semboller, boşsa BIST30")
    p.add_argument("--csv",      type=str,   default="",
                   help="CSV veri dosyası yolu")
    p.add_argument("--verbose",  action="store_true")
    p.add_argument("--save-csv", type=str,   default="",
                   help="Trade logunu bu dosyaya kaydet")
    return p.parse_args()


def build_config(args) -> BacktestConfig:
    exec_cfg = ExecutionConfig(
        commission_entry=0.0015,
        commission_exit=0.0015,
        slippage_entry=0.0005,
        slippage_exit=0.0005,
    )
    size_cfg = SizingConfig(
        total_capital=args.capital,
        risk_per_trade_pct=args.risk,
        max_open_positions=5,
    )
    stop_cfg = StopConfig(
        initial_stop_pct=args.stop / 100,
        target_rr=args.target,
        trailing_activation=args.stop / 100 * 0.67,  # stop'un 2/3'ünde aktive
        trailing_pct=args.trailing / 100,
    )
    return BacktestConfig(
        initial_capital=args.capital,
        bar_size_min=args.bars,
        exec_cfg=exec_cfg,
        size_cfg=size_cfg,
        stop_cfg=stop_cfg,
    )


def main():
    args    = parse_args()
    config  = build_config(args)
    runner  = BacktestRunner(config=config)

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] or BIST30
    end     = date.today()
    start   = end - timedelta(days=args.days)

    print(f"\nBIST Core Strategy — Gerçekçi Backtest Motoru")
    print(f"Semboller  : {len(symbols)} adet")
    print(f"Tarih      : {start} → {end}")
    print(f"Bar boyutu : {args.bars}m")
    print(f"Sermaye    : ₺{args.capital:,.0f}")
    print(f"Risk/Trade : %{args.risk}")
    print(f"Stop       : %{args.stop}  |  R/R: {args.target}x  |  Trailing: %{args.trailing}")
    print(f"Komisyon   : %{config.exec_cfg.commission_entry*100:.2f} giriş + "
          f"%{config.exec_cfg.commission_exit*100:.2f} çıkış")
    print(f"Slippage   : %{config.exec_cfg.slippage_entry*100:.2f} giriş + "
          f"%{config.exec_cfg.slippage_exit*100:.2f} çıkış\n")

    if args.csv:
        print(f"Veri kaynağı: CSV — {args.csv}")
        results = runner.run_from_csv(args.csv, start=start, end=end, symbols=symbols)
    else:
        print("Veri kaynağı: Sentetik (GBM)")
        results = runner.run_synthetic(symbols=symbols, start=start, end=end)

    runner.print_report(results, verbose=args.verbose)

    if args.save_csv:
        runner.to_csv(results, args.save_csv)


if __name__ == "__main__":
    main()
