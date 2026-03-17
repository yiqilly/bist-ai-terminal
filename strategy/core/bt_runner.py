# ============================================================
# strategy/core/bt_runner.py
# Backtest Runner — Orkestrasyon Katmanı
#
# Sorumlulukları:
#   - Tüm sembolleri × tüm günleri döngüye al
#   - Portföy durumunu koru (nakit, açık pozisyonlar)
#   - Günlük equity kaydet (Sharpe / MaxDD için)
#   - MetricsCalculator'ı besle
#   - Sonuçları print veya dict olarak sun
#
# Çalıştırma:
#   python -m strategy.core.bt_runner
#   veya import ederek:
#       runner = BacktestRunner()
#       results = runner.run(symbols, start, end)
#       runner.print_report(results)
# ============================================================
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from strategy.core.bt_data    import DayBars, RealisticBarGenerator, CSVBarLoader
from strategy.core.bt_engine  import ExecutionEngine
from strategy.core.bt_metrics import MetricsCalculator, PortfolioMetrics, SymbolMetrics
from strategy.core.bt_models  import (
    ExecutionConfig, SizingConfig, StopConfig, PortfolioState, TradeLog
)


# ── Backtest Konfigürasyonu ──────────────────────────────────────────────────

@dataclass
class BacktestConfig:
    """
    Tek bir nesneye toplanan tüm backtest parametreleri.
    Değiştirmek için alt-config nesnelerini kullan.
    """
    initial_capital:    float = 100_000.0
    bar_size_min:       int   = 5           # 1 veya 5
    annual_volatility:  float = 0.35        # Sentetik veri için
    max_open_positions: int   = 5

    exec_cfg:  ExecutionConfig = field(default_factory=ExecutionConfig)
    size_cfg:  SizingConfig    = field(default_factory=SizingConfig)
    stop_cfg:  StopConfig      = field(default_factory=StopConfig)

    def __post_init__(self):
        # Konfigürasyonlar arası tutarlılık
        self.size_cfg.total_capital      = self.initial_capital
        self.size_cfg.max_open_positions = self.max_open_positions


# ── Backtest Sonuç Paketi ────────────────────────────────────────────────────

@dataclass
class BacktestResults:
    config:        BacktestConfig
    portfolio:     PortfolioMetrics
    symbol_stats:  dict[str, SymbolMetrics]  # per_symbol sonuçları
    all_trades:    list[TradeLog]
    equity_curve:  list[tuple[str, float]]   # [(date, equity)]
    days_run:      int
    symbols_run:   int


# ── Ana Runner ───────────────────────────────────────────────────────────────

class BacktestRunner:
    """
    Gerçekçi bar-by-bar backtest motoru.

    Kullanım A — Sentetik (demo):
        runner = BacktestRunner()
        results = runner.run_synthetic(
            symbols=["THYAO", "GARAN", "AKBNK"],
            start=date(2024, 1, 2),
            end=date(2024, 6, 30),
        )
        runner.print_report(results)

    Kullanım B — CSV (Matriks IQ):
        runner = BacktestRunner()
        results = runner.run_from_csv(
            filepath="data/bist_5m.csv",
            start=date(2024, 1, 2),
            end=date(2024, 6, 30),
        )
        runner.print_report(results)

    Kullanım C — Hazır bar dict:
        bars: dict[str, list[DayBars]] = {...}
        results = runner.run(bars)
        runner.print_report(results)
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        self._cfg    = config or BacktestConfig()
        self._engine = ExecutionEngine(
            exec_cfg=self._cfg.exec_cfg,
            size_cfg=self._cfg.size_cfg,
            stop_cfg=self._cfg.stop_cfg,
            max_positions_global=self._cfg.max_open_positions,
        )
        self._metrics = MetricsCalculator(self._cfg.initial_capital)

    # ── Giriş noktaları ──────────────────────────────────────────────────────

    def run_synthetic(
        self,
        symbols:   list[str],
        start:     date,
        end:       date,
        base_prices: Optional[dict[str, float]] = None,
    ) -> BacktestResults:
        """Sentetik (GBM) veri ile backtest."""
        gen    = RealisticBarGenerator(bar_size_min=self._cfg.bar_size_min)
        prices = base_prices or {s: 100.0 for s in symbols}

        bars_by_symbol: dict[str, list[DayBars]] = {}
        for sym in symbols:
            bars_by_symbol[sym] = gen.generate_history(
                symbol=sym, start=start, end=end,
                base_price=prices.get(sym, 100.0),
                annual_volatility=self._cfg.annual_volatility,
            )

        return self.run(bars_by_symbol)

    def run_from_csv(
        self,
        filepath: str,
        start:    Optional[date] = None,
        end:      Optional[date] = None,
        symbols:  Optional[list[str]] = None,
    ) -> BacktestResults:
        """CSV dosyasından yükle ve çalıştır."""
        loader = CSVBarLoader()
        raw    = loader.load(filepath, start=start, end=end)

        if symbols:
            raw = {s: v for s, v in raw.items() if s in symbols}

        return self.run(raw)

    def run(self, bars_by_symbol: dict[str, list[DayBars]]) -> BacktestResults:
        """
        Ana backtest döngüsü.
        bars_by_symbol: {symbol: [DayBars_gün1, DayBars_gün2, ...]}
        """
        portfolio = PortfolioState(initial_capital=self._cfg.initial_capital)
        equity_curve: list[tuple[str, float]] = []

        # Tüm günleri topla ve sırala
        all_days: list[DayBars] = []
        for days in bars_by_symbol.values():
            all_days.extend(days)
        all_days.sort(key=lambda d: (d.date, d.symbol))

        # Gün gruplarına böl
        day_groups: dict[date, list[DayBars]] = {}
        for d in all_days:
            day_groups.setdefault(d.date, []).append(d)

        days_run = 0

        for dt in sorted(day_groups.keys()):
            day_list = day_groups[dt]
            days_run += 1

            # Portföy limiti kontrolü: her gün başında kapasite değerlendir
            available_slots = self._cfg.max_open_positions - portfolio.open_count

            # Her sembolü işle (fırsat sırası: setup quality'ye göre önce yüksek kalite)
            # İlk geçişte tüm setup'ları skora göre sırala
            day_setups = self._score_day_setups(day_list, portfolio)

            # Önce mevcut açık pozisyonları olan sembolleri işle
            for day in day_list:
                if day.symbol in portfolio.open_positions:
                    closed = self._engine.process_day(day, portfolio,
                                                       regime_mode=self._guess_regime(day))

            # Sonra yeni fırsatlar (setup skoru yüksekten düşüğe)
            for score, day in day_setups:
                if day.symbol in portfolio.open_positions:
                    continue   # zaten işlendi
                if portfolio.open_count >= self._cfg.max_open_positions:
                    break      # limit doldu

                regime = self._guess_regime(day)
                self._engine.process_day(day, portfolio, regime_mode=regime)

            # Günlük equity kaydet
            eq = portfolio.cash + sum(
                pos.highest_price * pos.lots
                for pos in portfolio.open_positions.values()
            )
            equity_curve.append((str(dt), round(eq, 2)))

        # Tüm açık pozisyonları zorla kapat (backtest sonu)
        for sym, pos in list(portfolio.open_positions.items()):
            # Sembole ait son barı bul
            last_day = None
            if sym in bars_by_symbol and bars_by_symbol[sym]:
                last_day = bars_by_symbol[sym][-1]
            if last_day and last_day.bars:
                last_bar = last_day.bars[-1]
                from strategy.core.bt_models import ExitReason
                log = self._engine._close_position(pos, last_bar, portfolio,
                                                    ExitReason.FORCED_CLOSE)
                portfolio.closed_trades.append(log)
            del portfolio.open_positions[sym]

        # Metrikleri hesapla
        trades = portfolio.closed_trades
        port_metrics  = self._metrics.portfolio(trades, equity_curve,
                                                  self._cfg.initial_capital)
        sym_metrics   = self._metrics.per_symbol(trades)

        return BacktestResults(
            config=self._cfg,
            portfolio=port_metrics,
            symbol_stats=sym_metrics,
            all_trades=trades,
            equity_curve=equity_curve,
            days_run=days_run,
            symbols_run=len(bars_by_symbol),
        )

    # ── Yardımcı metodlar ────────────────────────────────────────────────────

    def _score_day_setups(
        self,
        day_list: list[DayBars],
        portfolio: PortfolioState,
    ) -> list[tuple[float, DayBars]]:
        """
        Gündeki her sembol için hızlı bir setup skoru hesapla.
        Yüksek skora sahip semboller önce işlenir.
        Bu sayede portföy limiti dolduğunda en kaliteli setuplara girilir.
        """
        scored = []
        for day in day_list:
            if day.symbol in portfolio.open_positions:
                continue
            # Sabah barlarından hızlı momentum skoru
            morning = day.bars_between(
                __import__("datetime").time(10, 0),
                __import__("datetime").time(10, 30),
            )
            if len(morning) >= 2:
                momentum = (morning[-1].close - morning[0].open) / morning[0].open * 100
                vol_score = morning[-1].volume / max(b.volume for b in morning) if morning else 0
                score = momentum * 0.7 + vol_score * 0.3
            else:
                score = 0.0
            scored.append((score, day))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _guess_regime(self, day: DayBars) -> str:
        """
        Gerçek regime engine olmadığında gün için heuristic regime tahmini.
        Gerçek veri bağlandığında bu metod dışarıdan override edilir.
        """
        if not day.bars:
            return "NORMAL_CHOP"

        # Gün içi net hareket / range oranı
        open_p  = day.bars[0].open
        close_p = day.bars[-1].close
        highs   = [b.high for b in day.bars]
        lows    = [b.low  for b in day.bars]
        day_range = (max(highs) - min(lows)) / open_p * 100 if open_p else 0
        net_move  = (close_p - open_p) / open_p * 100 if open_p else 0

        if day_range > 3.0:           return "RISK_OFF"    # çok geniş range
        if net_move >= 1.5:           return "AGGRESSIVE"
        if net_move >= 0.3:           return "NORMAL_TREND"
        if abs(net_move) < 0.3:       return "NORMAL_CHOP"
        return "RISK_OFF"

    # ── Raporlama ─────────────────────────────────────────────────────────────

    def print_report(self, results: BacktestResults, verbose: bool = False) -> None:
        """Konsola kapsamlı backtest raporu yazar."""
        p   = results.portfolio
        cfg = results.config
        W   = 72

        _line = "=" * W
        _sep  = "-" * W

        print(f"\n{_line}")
        print(f"{'BIST CORE STRATEGY — GERÇEKÇI BACKTEST RAPORU':^{W}}")
        print(_line)
        print(f"  Başlangıç Sermayesi : ₺{cfg.initial_capital:>12,.2f}")
        print(f"  Bitiş Equity        : ₺{p.final_equity:>12,.2f}")
        ret_col = "+" if p.total_return_pct >= 0 else ""
        print(f"  Toplam Getiri       : {ret_col}{p.total_return_pct:>8.2f}%")
        print(f"  İşlem Günü          : {results.days_run:>5}")
        print(f"  Sembol Sayısı       : {results.symbols_run:>5}")
        print(f"  Bar Boyutu          : {cfg.bar_size_min}m")
        print(f"  Komisyon (RT)       : %{cfg.exec_cfg.total_rt_cost*100:.2f}")
        print(f"  Max Pozisyon        : {cfg.max_open_positions}")

        print(f"\n{'PORTFÖY METRİKLERİ':^{W}}")
        print(_sep)
        print(f"  {'İşlem Sayısı':<28} {p.total_trades:>10}")
        print(f"  {'Kazanan İşlem':<28} {p.total_wins:>10}  ({p.win_rate:.1%})")
        print(f"  {'Win Rate':<28} {p.win_rate:>9.1%}")
        print(f"  {'Profit Factor':<28} {p.profit_factor:>10.3f}")
        print(f"  {'Avg Trade':<28} {p.avg_trade_pct:>+9.4f}%")
        print(f"  {'Best Trade':<28} {p.best_trade_pct:>+9.4f}%")
        print(f"  {'Worst Trade':<28} {p.worst_trade_pct:>+9.4f}%")
        print(f"  {'Expectancy':<28} {p.expectancy_pct:>+9.4f}%")
        print(f"  {'Sharpe Ratio':<28} {p.sharpe_ratio:>10.3f}")
        print(f"  {'Sortino Ratio':<28} {p.sortino_ratio:>10.3f}")
        print(f"  {'Max Drawdown':<28} {p.max_dd_pct:>9.2f}%  (₺{p.max_dd_tl:,.0f})")
        print(f"  {'Net PnL (TL)':<28} ₺{p.total_net_pnl:>10,.2f}")
        print(f"  {'Toplam Komisyon':<28} ₺{p.total_commission:>10,.2f}")
        print(f"  {'Toplam Slippage':<28} ₺{p.total_slippage:>10,.2f}")

        print(f"\n{'EXIT NEDENLERİ':^{W}}")
        print(_sep)
        tot = max(p.total_trades, 1)
        print(f"  {'Stop Loss':<28} {p.stop_exits:>5}  ({p.stop_exits/tot:.1%})")
        print(f"  {'Trailing Stop':<28} {p.trailing_exits:>5}  ({p.trailing_exits/tot:.1%})")
        print(f"  {'Target':<28} {p.target_exits:>5}  ({p.target_exits/tot:.1%})")
        print(f"  {'End of Day':<28} {p.eod_exits:>5}  ({p.eod_exits/tot:.1%})")

        # Setup breakdown
        if p.by_setup:
            print(f"\n{'SETUP BAZLI PERFORMANS':^{W}}")
            print(_sep)
            print(f"  {'Setup':<30} {'İşlem':>6} {'WR':>7} {'AvgPnL':>8} {'TotalPnL':>10}")
            print(f"  {'-'*30} {'-'*6} {'-'*7} {'-'*8} {'-'*10}")
            for k, v in sorted(p.by_setup.items()):
                print(f"  {k:<30} {v['trades']:>6} {v['win_rate']:>6.1%} "
                      f"{v['avg_pnl']:>+7.4f}% ₺{v['total_pnl']:>9,.0f}")

        # Regime breakdown
        if p.by_regime:
            print(f"\n{'REJİM BAZLI PERFORMANS':^{W}}")
            print(_sep)
            print(f"  {'Rejim':<30} {'İşlem':>6} {'WR':>7} {'AvgPnL':>8} {'TotalPnL':>10}")
            print(f"  {'-'*30} {'-'*6} {'-'*7} {'-'*8} {'-'*10}")
            for k, v in sorted(p.by_regime.items()):
                print(f"  {k:<30} {v['trades']:>6} {v['win_rate']:>6.1%} "
                      f"{v['avg_pnl']:>+7.4f}% ₺{v['total_pnl']:>9,.0f}")

        # Sembol bazlı özet
        print(f"\n{'SEMBOL BAZLI ÖZET':^{W}}")
        print(_sep)
        print(f"  {'Sembol':<10} {'İşlem':>6} {'WR':>7} {'PF':>6} "
              f"{'AvgPnL':>8} {'TotalPnL':>10} {'MaxDD':>7}")
        print(f"  {'-'*10} {'-'*6} {'-'*7} {'-'*6} {'-'*8} {'-'*10} {'-'*7}")

        for sym, sm in sorted(p.by_symbol.items(),
                               key=lambda x: x[1].total_net_pnl, reverse=True):
            if sm.trade_count == 0: continue
            pf_str = f"{sm.profit_factor:.2f}" if sm.profit_factor != float("inf") else "∞"
            print(f"  {sym:<10} {sm.trade_count:>6} {sm.win_rate:>6.1%} "
                  f"{pf_str:>6} {sm.avg_trade_pct:>+7.4f}% "
                  f"₺{sm.total_net_pnl:>9,.0f} {sm.max_dd_pct:>6.2f}%")

        # Verbose: trade log
        if verbose and results.all_trades:
            print(f"\n{'TRADE LOG (ilk 30)':^{W}}")
            print(_sep)
            print(f"  {'#':>4} {'Sembol':<8} {'Tarih':<12} {'Setup':<22} "
                  f"{'Entry':>7} {'Exit':>7} {'PnL%':>7} {'Neden':<15}")
            print(f"  {'-'*4} {'-'*8} {'-'*12} {'-'*22} "
                  f"{'-'*7} {'-'*7} {'-'*7} {'-'*15}")
            for t in results.all_trades[:30]:
                sign = "+" if t.pnl_pct >= 0 else ""
                print(f"  {t.trade_id:>4} {t.symbol:<8} {str(t.date):<12} "
                      f"{t.setup_type:<22} {t.raw_entry:>7.2f} {t.raw_exit:>7.2f} "
                      f"{sign}{t.pnl_pct:>6.3f}% {t.exit_reason.value:<15}")

        print(f"\n{_line}\n")

    def to_csv(self, results: BacktestResults, filepath: str) -> None:
        """Trade logunu CSV dosyasına yazar."""
        import csv
        if not results.all_trades:
            print("Kaydedilecek trade yok.")
            return

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results.all_trades[0].to_dict().keys())
            writer.writeheader()
            for t in results.all_trades:
                writer.writerow(t.to_dict())
        print(f"Trade log kaydedildi: {filepath} ({len(results.all_trades)} satır)")

    def to_dict(self, results: BacktestResults) -> dict:
        """Sonuçları JSON-uyumlu dict'e çevirir."""
        p = results.portfolio
        return {
            "summary": {
                "initial_capital":    results.config.initial_capital,
                "final_equity":       p.final_equity,
                "total_return_pct":   round(p.total_return_pct, 4),
                "total_trades":       p.total_trades,
                "win_rate":           round(p.win_rate, 4),
                "profit_factor":      round(p.profit_factor, 4),
                "avg_trade_pct":      round(p.avg_trade_pct, 4),
                "expectancy_pct":     round(p.expectancy_pct, 4),
                "sharpe_ratio":       round(p.sharpe_ratio, 4),
                "sortino_ratio":      round(p.sortino_ratio, 4),
                "max_dd_pct":         round(p.max_dd_pct, 4),
                "max_dd_tl":          round(p.max_dd_tl, 2),
                "total_commission":   round(p.total_commission, 2),
                "total_slippage":     round(p.total_slippage, 2),
            },
            "by_setup":  p.by_setup,
            "by_regime": p.by_regime,
            "by_symbol": {
                sym: {
                    "trades":         sm.trade_count,
                    "win_rate":       round(sm.win_rate, 4),
                    "profit_factor":  round(sm.profit_factor, 4) if sm.profit_factor != float("inf") else 99.0,
                    "avg_trade_pct":  round(sm.avg_trade_pct, 4),
                    "total_net_pnl":  round(sm.total_net_pnl, 2),
                    "max_dd_pct":     round(sm.max_dd_pct, 4),
                    "sharpe":         round(sm.sharpe_ratio, 4),
                    "expectancy_pct": round(sm.expectancy_pct, 4),
                }
                for sym, sm in p.by_symbol.items()
            },
            "trades": [t.to_dict() for t in results.all_trades],
            "equity_curve": results.equity_curve,
        }
