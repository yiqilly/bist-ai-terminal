# ============================================================
# strategy/core/bt_engine.py
# Bar-by-Bar Execution Engine
#
# Sorumlulukları:
#   1. Sabah penceresi bitince setup detection'ı tetikle
#      (mevcut BreakoutDetector — dokunulmadı)
#   2. Breakout barında entry aç
#   3. Her sonraki barda:
#      - stop/trailing stop hit kontrolü
#      - target hit kontrolü
#      - EOD exit kontrolü
#   4. Pozisyon kapanınca TradeLog oluştur
#   5. PortfolioState'i güncelle
# ============================================================
from __future__ import annotations

import math
from datetime import date, datetime, time
from typing import Optional

from strategy.core.bt_data   import OHLCVBar, DayBars
from strategy.core.bt_models import (
    ExecutionConfig, SizingConfig, StopConfig,
    OpenPosition, TradeLog, PortfolioState, ExitReason,
)
from strategy.core.core_features  import CoreSetupFeatures, MorningBar
from strategy.core.breakout_rules import BreakoutDetector


# ── Saat sabitleri (BreakoutDetector ile senkron) ────────────────────────────
_T_MORN_START = time(10,  0)
_T_MORN_END   = time(10, 30)
_T_BO_END     = time(10, 45)
_T_PB_END     = time(11, 10)
_T_RB_END     = time(11, 30)


def _to_morning_bar(b: OHLCVBar) -> MorningBar:
    """OHLCVBar → MorningBar dönüşümü (BreakoutDetector uyumlu)."""
    from strategy.core.core_features import MorningBar as MB
    return MB(timestamp=b.timestamp, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume)


# ── Execution Engine ─────────────────────────────────────────────────────────

class ExecutionEngine:
    """
    Tek bir sembol + tek bir gün için bar-by-bar simülasyon.

    Kullanım:
        engine  = ExecutionEngine(exec_cfg, size_cfg, stop_cfg)
        engine.process_day(day_bars, portfolio, regime_mode)
    """

    def __init__(
        self,
        exec_cfg:  ExecutionConfig,
        size_cfg:  SizingConfig,
        stop_cfg:  StopConfig,
        max_positions_global: int = 5,
    ):
        self._exec  = exec_cfg
        self._size  = size_cfg
        self._stop  = stop_cfg
        self._max   = max_positions_global
        self._bd    = BreakoutDetector()

    # ── Ana işlem döngüsü ────────────────────────────────────────────────────

    def process_day(
        self,
        day: DayBars,
        portfolio: PortfolioState,
        regime_mode: str = "NORMAL_TREND",
    ) -> list[TradeLog]:
        """
        Tek bir günün tüm barlarını işler.
        Döndürür: gün içinde kapanan işlemlerin listesi.
        """
        bars          = day.bars
        symbol        = day.symbol
        eod_t         = self._parse_eod()
        closed_today:  list[TradeLog] = []

        # ── AŞAMA 1: Setup detection ─────────────────────────
        setup = self._detect_setup(bars, symbol, day.date)

        # ── AŞAMA 2: Breakout barında entry ──────────────────
        entry_bar   = self._find_entry_bar(bars, setup)
        trade_opened = False

        # ── AŞAMA 3: Bar-by-bar döngü ────────────────────────
        active: OpenPosition | None = portfolio.open_positions.get(symbol)

        for bar in bars:
            bar_t = bar.timestamp.time()

            # EOD: açık pozisyonu kapat
            if bar_t >= eod_t and active:
                log = self._close_position(
                    active, bar, portfolio, ExitReason.END_OF_DAY
                )
                closed_today.append(log)
                del portfolio.open_positions[symbol]
                active = None
                continue

            # Aktif pozisyon varsa yönet
            if active:
                log = self._manage_position(active, bar, portfolio)
                if log:
                    closed_today.append(log)
                    del portfolio.open_positions[symbol]
                    active = None
                continue

            # Entry kontrolü — breakout barında pozisyon aç
            if (
                not trade_opened
                and entry_bar
                and bar.timestamp == entry_bar.timestamp
                and setup.is_active_setup
                and portfolio.open_count < self._max
                and regime_mode in ("AGGRESSIVE", "NORMAL_TREND")
            ):
                pos = self._open_position(bar, setup, portfolio, regime_mode)
                if pos:
                    portfolio.open_positions[symbol] = pos
                    active        = pos
                    trade_opened  = True

        # Gün sonu EOD'a ulaşamadıysak son barda kapat
        if active and symbol in portfolio.open_positions:
            last_bar = bars[-1]
            log = self._close_position(
                active, last_bar, portfolio, ExitReason.END_OF_DAY
            )
            closed_today.append(log)
            del portfolio.open_positions[symbol]

        return closed_today

    # ── Setup Detection ──────────────────────────────────────────────────────

    def _detect_setup(self, bars: list[OHLCVBar], symbol: str, dt: date) -> CoreSetupFeatures:
        """
        Mevcut BreakoutDetector'ı kullanır — dokunulmadı.
        OHLCVBar listesini MorningBar listesine çevirir.
        """
        morning_bars = [_to_morning_bar(b) for b in bars]
        features     = CoreSetupFeatures(symbol=symbol, date=dt)
        return self._bd.detect(morning_bars, features)

    def _find_entry_bar(
        self,
        bars: list[OHLCVBar],
        setup: CoreSetupFeatures,
    ) -> OHLCVBar | None:
        """
        Entry barını bul:
        - PullbackRebreak   → rebreak_time ile örtüşen bar
        - MorningMomentumBreakout / BreakoutOnly → breakout_time ile örtüşen bar

        LOOK-AHEAD BIAS DÜZELTMESİ:
        Entry fiyatı artık breakout/rebreak barının KAPAT fiyatı,
        önceki 10:30 kapanışı değil.
        """
        if setup.setup_type == "None":
            return None

        if setup.setup_type == "PullbackRebreak" and setup.rebreak_time:
            target_ts = setup.rebreak_time
        elif setup.breakout_time:
            target_ts = setup.breakout_time
        else:
            return None

        # Tam eşleşme veya en yakın bar
        for b in bars:
            if b.timestamp >= target_ts:
                return b

        return None

    # ── Pozisyon Açma ────────────────────────────────────────────────────────

    def _open_position(
        self,
        bar:         OHLCVBar,
        setup:       CoreSetupFeatures,
        portfolio:   PortfolioState,
        regime_mode: str,
    ) -> OpenPosition | None:
        """
        Breakout barının kapanış fiyatından long pozisyon aç.
        """
        raw_entry  = bar.close
        fill_entry = self._exec.apply_entry(raw_entry)   # komisyon + slippage

        # Stop ve target
        stop   = self._stop.initial_stop(fill_entry)
        target = self._stop.initial_target(fill_entry)

        # Pozisyon boyutu
        lots = self._size.position_size(
            capital=portfolio.available_capital,
            entry_price=fill_entry,
            stop_price=stop,
        )

        if lots <= 0:
            return None

        cost = fill_entry * lots
        if cost > portfolio.available_capital:
            lots = math.floor(portfolio.available_capital / fill_entry)
            if lots <= 0:
                return None
            cost = fill_entry * lots

        # Nakit düş
        portfolio.cash -= cost

        return OpenPosition(
            symbol=bar.symbol,
            entry_ts=bar.timestamp,
            entry_price=fill_entry,
            raw_entry=raw_entry,
            lots=lots,
            stop=stop,
            target=target,
            setup_type=setup.setup_type,
            regime_mode=regime_mode,
            setup_quality=setup.setup_quality,
        )

    # ── Pozisyon Yönetimi (her bar) ──────────────────────────────────────────

    def _manage_position(
        self,
        pos:       OpenPosition,
        bar:       OHLCVBar,
        portfolio: PortfolioState,
    ) -> TradeLog | None:
        """
        Barın high/low/close'una göre:
        1) Target hit → kapat
        2) Stop hit   → kapat
        3) Trailing stop → kapat (eğer aktif ve tetiklendi)
        Değilse → trailing stop güncelle, devam et.

        NOT: Gerçekçilik için önce stop, sonra target kontrol edilir
        (worst-case fill varsayımı).
        """
        # Trailing güncelle
        pos.update_trailing(bar.high, self._stop)

        # 1) Stop hit mi? (barın low'u stop'un altına indi mi)
        if bar.low <= pos.current_stop:
            reason = (ExitReason.TRAILING_STOP
                      if pos.trailing_stop_active
                      else ExitReason.STOP_LOSS)
            # Fill fiyatı: mümkün olursa stop, değilse barın open'ı
            # (gap-down durumunda open'da fill)
            fill_price = max(pos.current_stop, bar.open)
            return self._close_position(pos, bar, portfolio, reason,
                                         override_exit_price=fill_price)

        # 2) Target hit mi?
        if bar.high >= pos.target:
            return self._close_position(pos, bar, portfolio, ExitReason.TARGET,
                                         override_exit_price=pos.target)

        return None   # pozisyon açık, devam

    # ── Pozisyon Kapatma ─────────────────────────────────────────────────────

    def _close_position(
        self,
        pos:        OpenPosition,
        bar:        OHLCVBar,
        portfolio:  PortfolioState,
        reason:     ExitReason,
        override_exit_price: float | None = None,
    ) -> TradeLog:
        """
        Pozisyonu kapatır, gerçekçi fill hesaplar, TradeLog döndürür.
        """
        raw_exit  = override_exit_price if override_exit_price else bar.close
        fill_exit = self._exec.apply_exit(raw_exit)

        # Nakit geri ekle
        portfolio.cash += fill_exit * pos.lots

        # Kâr/Zarar hesabı
        gross_pnl_tl = (raw_exit - pos.raw_entry) * pos.lots

        comm_entry   = pos.entry_price * pos.lots * self._exec.commission_entry
        comm_exit    = fill_exit       * pos.lots * self._exec.commission_exit
        slip_entry   = pos.raw_entry   * pos.lots * self._exec.slippage_entry
        slip_exit    = raw_exit        * pos.lots * self._exec.slippage_exit
        commission_tl = comm_entry + comm_exit
        slippage_tl   = slip_entry + slip_exit
        net_pnl_tl    = gross_pnl_tl - commission_tl - slippage_tl

        pnl_pct = net_pnl_tl / (pos.entry_price * pos.lots) * 100

        log = TradeLog(
            trade_id      = portfolio.next_trade_id(),
            symbol        = pos.symbol,
            date          = bar.date,
            setup_type    = pos.setup_type,
            regime_mode   = pos.regime_mode,
            setup_quality = pos.setup_quality,
            raw_entry     = pos.raw_entry,
            raw_exit      = raw_exit,
            fill_entry    = pos.entry_price,
            fill_exit     = fill_exit,
            entry_ts      = pos.entry_ts,
            exit_ts       = bar.timestamp,
            lots          = pos.lots,
            stop_at_entry = pos.stop,
            target        = pos.target,
            initial_risk  = (pos.entry_price - pos.stop) * pos.lots,
            exit_reason   = reason,
            gross_pnl_tl  = round(gross_pnl_tl,  2),
            commission_tl = round(commission_tl,  2),
            slippage_tl   = round(slippage_tl,    2),
            net_pnl_tl    = round(net_pnl_tl,     2),
            pnl_pct       = round(pnl_pct,        4),
            highest_price  = pos.highest_price,
            trailing_triggered = pos.trailing_stop_active,
        )

        portfolio.closed_trades.append(log)
        return log

    # ── Yardımcı ─────────────────────────────────────────────────────────────

    def _parse_eod(self) -> time:
        s = self._stop.eod_exit_time_str
        h, m = map(int, s.split(":"))
        return time(h, m)
