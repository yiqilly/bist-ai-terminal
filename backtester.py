"""
backtester.py — BIST Terminal Geriye Donuk Test (Backtest) Motoru

Kullanim:
  python backtester.py --period 1y
  python backtester.py --period 5y
  python backtester.py --period 2y   (varsayilan)

Degisiklikler (v3):
 - --period argumani ile 1y / 2y / 5y destegi
 - Sektor rotasyonu: ctx'e sector_strength eklendi
 - ENTRY_WAIT state destegi (pullback entry simülasyonu)
 - XU100 benchmark karsilastirmasi eklendi
"""
import argparse
import os
import sys
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CAPITAL_TL
from data.symbols import ACTIVE_UNIVERSE
from data.sector_map import SYMBOL_SECTOR
from strategy.edge_multi import EdgeMultiStrategy, EdgeState, SetupType
from portfolio.engine import PortfolioEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Backtester")


class MockBar:
    def __init__(self, timestamp, open_, high, low, close, volume):
        self.timestamp = timestamp
        self.open  = float(open_)
        self.high  = float(high)
        self.low   = float(low)
        self.close = float(close)
        self.volume = float(volume)


def prepare_data(period: str) -> pd.DataFrame:
    cache_file = f".cache_bist100_{period}.pkl"
    logger.info(f"BIST100 + XU100 gecmis verileri hazirlaniyor (period={period})...")

    if os.path.exists(cache_file):
        logger.info("Onbellekten (Cache) yukleniyor...")
        return pd.read_pickle(cache_file)

    symbols = [f"{s}.IS" for s in ACTIVE_UNIVERSE]
    symbols.append("XU100.IS")

    logger.info(f"Yahoo Finance uzerinden {period} veri indiriliyor (Bu biraz surebilir)...")
    df = yf.download(symbols, period=period, interval="1d",
                     group_by="ticker", auto_adjust=True, progress=False)
    df.ffill(inplace=True)
    df.to_pickle(cache_file)
    return df


def build_indicators(df, sym):
    """Her bir sembol icin DataFrame seviyesinde indiktorleri onceden hesaplar."""
    try:
        data = df[sym].copy()
    except KeyError:
        return None

    if data.empty or len(data) < 50:
        return None

    data['EMA_9']  = data['Close'].ewm(span=9,  adjust=False).mean()
    data['EMA_21'] = data['Close'].ewm(span=21, adjust=False).mean()
    data['EMA_50'] = data['Close'].ewm(span=50, adjust=False).mean()

    high_low   = data['High'] - data['Low']
    high_close = np.abs(data['High'] - data['Close'].shift())
    low_close  = np.abs(data['Low']  - data['Close'].shift())
    true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
    data['ATR_14']    = true_range.rolling(14).mean()
    data['VOL_MA_20'] = data['Volume'].rolling(20).mean()
    data['GAP_UP']    = data['Open'] > data['High'].shift(1)
    data['Daily_Chg'] = data['Close'].pct_change() * 100

    return data


def build_sector_strength(sym_data_map: dict, dates) -> pd.DataFrame:
    """
    Her tarih icin sektör gücü (0-100 scale) hesaplar.
    50 = nötr, >50 = yukseliyor, <50 = dusuyor
    """
    logger.info("Sektor gucu onceden hesaplaniyor...")

    # Gunluk degisim matrisini olustur
    chg_dict = {}
    for sym, dframe in sym_data_map.items():
        if 'Daily_Chg' in dframe.columns:
            chg_dict[sym] = dframe['Daily_Chg']
    chg_df = pd.DataFrame(chg_dict)

    # Sektore gore grupla
    sector_syms: dict[str, list] = {}
    for sym in chg_df.columns:
        sec = SYMBOL_SECTOR.get(sym, 'Diger')
        sector_syms.setdefault(sec, []).append(sym)

    # Her sektörün gunluk ortalama degisimini hesapla
    sector_avg = {}
    for sec, syms in sector_syms.items():
        valid = [s for s in syms if s in chg_df.columns]
        if valid:
            sector_avg[sec] = chg_df[valid].mean(axis=1)

    sector_df = pd.DataFrame(sector_avg)
    # 0-100 scale: 50 + avg_chg * 10  (±5% → 0-100)
    sector_strength_df = (50 + sector_df * 10).clip(0, 100)
    return sector_strength_df


def run_backtest(period: str = "2y"):
    raw_df = prepare_data(period)

    logger.info("Indikatorler onceden hesaplaniyor (Vektorize)...")
    sym_data_map = {}

    if "XU100.IS" in raw_df.columns.levels[0]:
        xu100      = raw_df["XU100.IS"]
        xu100_mom  = xu100['Close'].pct_change(14).fillna(0)
        xu100_ret  = xu100['Close'].iloc[-1] / xu100['Close'].iloc[0] - 1  # benchmark getirisi
    else:
        logger.error("XU100 bulunamadi; RS devre disi.")
        xu100_mom = pd.Series(0, index=raw_df.index)
        xu100_ret = 0.0

    for sym in ACTIVE_UNIVERSE:
        sym_is    = f"{sym}.IS"
        processed = build_indicators(raw_df, sym_is)
        if processed is not None:
            sym_mom = processed['Close'].pct_change(14).fillna(0)
            processed['RS_Index'] = (1 + sym_mom) / (1 + xu100_mom)
            sym_data_map[sym] = processed

    # Sektör gücü matrisi
    dates = raw_df.index.sort_values().unique()
    sector_strength_df = build_sector_strength(sym_data_map, dates)

    logger.info(f"Zaman makinesi baslatildi — {len(dates)} gun taranacak...")

    strategy  = EdgeMultiStrategy()
    portfolio = PortfolioEngine()

    fake_time = datetime(2015, 1, 1, 9, 0)

    for current_date in dates:
        fake_time += timedelta(minutes=1)

        # ── 1. Mevcut Pozisyonlari Yonet ────────────────────────────────────
        for sym in list(portfolio.positions.keys()):
            if sym not in sym_data_map:
                continue
            row = sym_data_map[sym].loc[current_date:current_date]
            if row.empty:
                continue
            rd = row.iloc[0]
            reasons = portfolio.update_from_bar(
                sym,
                high=float(rd['High']),
                low=float(rd['Low']),
                close=float(rd['Close'])
            )
            if reasons:
                portfolio._close(sym, exit_time=current_date, reason=reasons[0])

        # ── 2. Sektor Gucunu Al ──────────────────────────────────────────────
        date_sector_str: dict[str, float] = {}
        if current_date in sector_strength_df.index:
            for sec in sector_strength_df.columns:
                v = sector_strength_df.loc[current_date, sec]
                date_sector_str[sec] = float(v) if not pd.isna(v) else 50.0

        # ── 3. Yeni Sinyalleri Yakala ────────────────────────────────────────
        day_signals = []
        for sym, dframe in sym_data_map.items():
            row = dframe.loc[current_date:current_date]
            if row.empty:
                continue
            r = row.iloc[0]
            if pd.isna(r['EMA_9']) or pd.isna(r['Close']):
                continue

            sec_name = SYMBOL_SECTOR.get(sym, 'Diger')
            sec_str  = date_sector_str.get(sec_name, 50.0)

            bar = MockBar(
                timestamp=fake_time,
                open_=r['Open'], high=r['High'], low=r['Low'],
                close=r['Close'], volume=r['Volume']
            )
            ctx = {
                "ema9_daily":      float(r['EMA_9']),
                "ema21_daily":     float(r['EMA_21']),
                "ema_50":          float(r['EMA_50']),
                "daily_atr":       float(r['ATR_14']),
                "vol_ma":          float(r['VOL_MA_20']),
                "gap_up":          bool(r['GAP_UP']),
                "rs_vs_index":     float(r['RS_Index']),
                "sector_strength": sec_str,
                "xu100_mom":       float(xu100_mom.loc[current_date]) if current_date in xu100_mom.index else 0.0,
            }

            sig = strategy.on_bar(sym, bar, ctx)

            # CONFIRMING teyidini ayni gun simule et
            if sig.state == EdgeState.CONFIRMING and not getattr(sig, "is_signal", False):
                bar.timestamp += timedelta(seconds=1)
                sig = strategy.on_bar(sym, bar, ctx)

            if getattr(sig, "is_signal", False):
                if sym not in portfolio.positions:
                    day_signals.append(sig)
                sig.is_signal = False
                sig.set_state(EdgeState.COOLDOWN)

        # ── 4. Portfoye Alis Gir ─────────────────────────────────────────────
        if day_signals and portfolio.free_slots > 0:
            for sig in day_signals[:portfolio.free_slots]:
                entry  = getattr(sig, "entry",  0.0)
                target = getattr(sig, "target", 0.0)
                if entry > 0 and target > entry:
                    opened = portfolio.open_position(sig)
                    if opened and sig.symbol in portfolio.positions:
                        portfolio.positions[sig.symbol].entry_time = \
                            pd.Timestamp(current_date).to_pydatetime()

    # ── Raporlama ────────────────────────────────────────────────────────────
    print("\n" + "="*50)
    print(f"  BACKTEST SONUCLARI  |  Period: {period.upper()}")
    print("="*50)

    closed_trades = portfolio.closed_trades
    total_trades  = len(closed_trades)

    current_value = portfolio.cash
    open_profit   = 0.0
    for sym, pos in list(portfolio.positions.items()):
        try:
            last_price     = sym_data_map[sym]['Close'].iloc[-1]
            pnl            = (pos.quantity * last_price) - (pos.quantity * pos.entry_price)
            open_profit   += pnl
            current_value += (pos.quantity * pos.entry_price) + pnl
        except Exception:
            current_value += pos.quantity * pos.entry_price

    net_profit  = current_value - CAPITAL_TL
    net_pct     = (net_profit / CAPITAL_TL) * 100
    xu100_pct   = xu100_ret * 100

    print(f"Baslangic Sermayesi    : {CAPITAL_TL:>12,.0f} TL")
    print(f"Bitis Portfoy Degeri   : {current_value:>12,.0f} TL")
    print(f"Net Kar/Zarar          : {net_profit:>+12,.0f} TL  (%{net_pct:+.1f})")
    print(f"XU100 Getirisi (bench) :                   %{xu100_pct:+.1f}")
    print(f"Alpha                  :                   %{net_pct - xu100_pct:+.1f}")
    print(f"Toplam Islem           : {total_trades}")
    print(f"Acik Pozisyon PnL      : {open_profit:>+12,.0f} TL")

    if total_trades > 0:
        winners  = [t for t in closed_trades if t['pnl'] > 0]
        losers   = [t for t in closed_trades if t['pnl'] <= 0]
        win_rate = len(winners) / total_trades * 100
        avg_win  = sum(t['pnl'] for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t['pnl'] for t in losers)  / len(losers)  if losers  else 0
        rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        trailing_exits = [t for t in closed_trades if "STOP LOSS" in str(t.get('reason', ''))]

        print("\n--- ISTATISTIKLER ---")
        print(f"Kazanma Orani (Win Rate): %{win_rate:.1f}")
        print(f"Kazandiran Islem        : {len(winners)}")
        print(f"Kaybettiren Islem       : {len(losers)}")
        print(f"Ortalama Kazanc         : {avg_win:>+10,.0f} TL")
        print(f"Ortalama Kayip          : {avg_loss:>+10,.0f} TL")
        print(f"Kazanc/Kayip Orani      : {rr_ratio:.2f}x")
        print(f"Trailing Stop Cikis     : {len(trailing_exits)}")

        # Max Drawdown
        peak = running_pnl = 0
        drawdowns = []
        for tr in closed_trades:
            running_pnl += tr['pnl']
            if running_pnl > peak:
                peak = running_pnl
            drawdowns.append(peak - running_pnl)
        max_dd = max(drawdowns) if drawdowns else 0
        max_dd_pct = (max_dd / CAPITAL_TL) * 100
        print(f"Maksimum Drawdown       : {max_dd:>10,.0f} TL  (%{max_dd_pct:.1f})")

        # En iyi / en kotu islemler
        if closed_trades:
            best  = max(closed_trades, key=lambda t: t['pnl'])
            worst = min(closed_trades, key=lambda t: t['pnl'])
            print(f"\nEn Iyi Islem  : {best['symbol']:8s} {best['pnl']:>+10,.0f} TL")
            print(f"En Kotu Islem : {worst['symbol']:8s} {worst['pnl']:>+10,.0f} TL")

    print("="*50 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BIST Edge Backtester")
    parser.add_argument("--period", default="2y",
                        choices=["1y", "2y", "3y", "5y"],
                        help="Test donemi (varsayilan: 2y)")
    args = parser.parse_args()
    run_backtest(period=args.period)
