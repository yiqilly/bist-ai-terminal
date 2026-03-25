"""
backtester.py — BIST Terminal Geriye Donuk Test (Backtest) Motoru
Bu modul, EdgeMultiStrategy algoritmasini kullanarak BIST100 uzerinde gegmise donuk
karlılık analizi (Win Rate, Drawdown vb.) yapar.

Degisiklikler (v2):
 - Portfolyo yonetimi artik portfolio/engine.py'deki PortfolioEngine uzerinden yuruyor
 - Trailing Stop (Izleyen Stop) aktif: her gun High guncellemesi stop'u yukari tasir
 - Dinamik Alokasyon: sabit %10 yok, toplam portfoy degeri / 5 seklinde hesaplanir
"""
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
from strategy.edge_multi import EdgeMultiStrategy, EdgeState, SetupType
from portfolio.engine import PortfolioEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Backtester")

CACHE_FILE = ".cache_bist100_2y.pkl"


class MockBar:
    def __init__(self, timestamp, open_, high, low, close, volume):
        self.timestamp = timestamp
        self.open = float(open_)
        self.high = float(high)
        self.low = float(low)
        self.close = float(close)
        self.volume = float(volume)



def prepare_data():
    logger.info("BIST100 + XU100 gecmis verileri hazirlaniyor...")

    if os.path.exists(CACHE_FILE):
        logger.info("Onbellekten (Cache) yukleniyor...")
        return pd.read_pickle(CACHE_FILE)

    symbols = [f"{s}.IS" for s in ACTIVE_UNIVERSE]
    symbols.append("XU100.IS")

    logger.info("Yahoo Finance uzerinden 2 yillik veri indiriliyor (Bu biraz surebilir)...")
    df = yf.download(symbols, period="2y", interval="1d", group_by="ticker", auto_adjust=True)
    df.ffill(inplace=True)
    df.to_pickle(CACHE_FILE)
    return df


def build_indicators(df, sym):
    """Her bir sembol icin DataFrame seviyesinde indiktorleri onceden hesaplar."""
    try:
        data = df[sym].copy()
    except KeyError:
        return None

    if data.empty or len(data) < 50:
        return None

    data['EMA_9']  = data['Close'].ewm(span=9, adjust=False).mean()
    data['EMA_21'] = data['Close'].ewm(span=21, adjust=False).mean()
    data['EMA_50'] = data['Close'].ewm(span=50, adjust=False).mean()

    # ATR 14
    high_low    = data['High'] - data['Low']
    high_close  = np.abs(data['High'] - data['Close'].shift())
    low_close   = np.abs(data['Low'] - data['Close'].shift())
    ranges      = pd.concat([high_low, high_close, low_close], axis=1)
    true_range  = np.max(ranges, axis=1)
    data['ATR_14']    = true_range.rolling(14).mean()
    data['VOL_MA_20'] = data['Volume'].rolling(20).mean()
    data['GAP_UP']    = data['Open'] > data['High'].shift(1)

    return data


def run_backtest():
    raw_df = prepare_data()

    logger.info("Indikatorler onceden hesaplaniyor (Vektorize)...")
    sym_data_map = {}

    if "XU100.IS" in raw_df.columns.levels[0]:
        xu100 = raw_df["XU100.IS"]
        xu100_mom = xu100['Close'].pct_change(14).fillna(0)
    else:
        logger.error("XU100 bulunamadi; RS devre disi.")
        xu100_mom = pd.Series(0, index=raw_df.index)

    for sym in ACTIVE_UNIVERSE:
        sym_is = f"{sym}.IS"
        processed = build_indicators(raw_df, sym_is)
        if processed is not None:
            sym_mom = processed['Close'].pct_change(14).fillna(0)
            processed['RS_Index'] = (1 + sym_mom) / (1 + xu100_mom)
            sym_data_map[sym] = processed

    logger.info("Zaman makinesi baslatildi (Gun Gun Taranacak)...")
    dates = raw_df.index.sort_values().unique()

    strategy  = EdgeMultiStrategy()
    portfolio = PortfolioEngine()   # Trailing Stop + dinamik alokasyon

    fake_time = datetime(2020, 1, 1, 9, 0)

    for current_date in dates:
        fake_time += timedelta(minutes=1)

        # ── 1. Mevcut Pozisyonlari Yonet (Trailing Stop / TP / SL / Time-Stop) ──
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

        # ── 2. Yeni Sinyalleri Yakala ──────────────────────────────────────────
        day_signals = []
        for sym, dframe in sym_data_map.items():
            row = dframe.loc[current_date:current_date]
            if row.empty:
                continue
            r = row.iloc[0]
            if pd.isna(r['EMA_9']) or pd.isna(r['Close']):
                continue

            bar = MockBar(
                timestamp=fake_time,
                open_=r['Open'], high=r['High'], low=r['Low'],
                close=r['Close'], volume=r['Volume']
            )
            ctx = {
                "ema9_daily":  float(r['EMA_9']),
                "ema21_daily": float(r['EMA_21']),
                "ema_50":      float(r['EMA_50']),
                "daily_atr":   float(r['ATR_14']),
                "vol_ma":      float(r['VOL_MA_20']),
                "gap_up":      bool(r['GAP_UP']),
                "rs_vs_index": float(r['RS_Index']),
                "xu100_mom":   float(xu100_mom.loc[current_date]) if current_date in xu100_mom.index else 0.0
            }

            sig = strategy.on_bar(sym, bar, ctx)

            # Intraday confirmation simulasyonu (gunluk mum icin)
            if sig.state == EdgeState.CONFIRMING and not getattr(sig, "is_signal", False):
                bar.timestamp += timedelta(seconds=1)
                sig = strategy.on_bar(sym, bar, ctx)

            if getattr(sig, "is_signal", False):
                # Portfolio'da zaten yoksa sinyal listesine ekle
                if sym not in portfolio.positions:
                    day_signals.append(sig)
                sig.is_signal = False
                sig.set_state(EdgeState.COOLDOWN)

        # ── 3. Portfoye Alis Gir ──────────────────────────────────────────────
        if day_signals and portfolio.free_slots > 0:
            for sig in day_signals[:portfolio.free_slots]:
                entry = getattr(sig, "entry", 0.0)
                target = getattr(sig, "target", 0.0)
                if entry > 0 and target > entry:
                    opened = portfolio.open_position(sig)
                    if opened and sig.symbol in portfolio.positions:
                        # entry_time'i gercek simulasyon tarihiyle guncelle
                        portfolio.positions[sig.symbol].entry_time = \
                            pd.Timestamp(current_date).to_pydatetime()

    # ── Raporlama ─────────────────────────────────────────────────────────────
    logger.info("==== BACKTEST SONUCLARI ====")
    closed_trades = portfolio.closed_trades
    total_trades  = len(closed_trades)
    print(f"Toplam Tamamlanan Islem: {total_trades}")
    print(f"Baslangic Sermayesi: {CAPITAL_TL:,.2f} TL")

    # Acik kalan pozisyonlari son fiyatla degerlendirme
    current_value = portfolio.cash
    open_profit   = 0.0
    for sym, pos in list(portfolio.positions.items()):
        try:
            last_price = sym_data_map[sym]['Close'].iloc[-1]
            pnl = (pos.quantity * last_price) - (pos.quantity * pos.entry_price)
            open_profit   += pnl
            current_value += (pos.quantity * pos.entry_price) + pnl
        except Exception:
            current_value += pos.quantity * pos.entry_price

    net_profit = current_value - CAPITAL_TL
    print(f"Bitis Portfoy Degeri: {current_value:,.2f} TL (Acik Poz. PnL: {open_profit:,.2f} TL)")
    print(f"Net Kar/Zarar: {net_profit:,.2f} TL (%{(net_profit / CAPITAL_TL) * 100:.2f})")

    if total_trades > 0:
        winners = [t for t in closed_trades if t['pnl'] > 0]
        losers  = [t for t in closed_trades if t['pnl'] <= 0]
        win_rate = len(winners) / total_trades * 100

        trailing_exits = [t for t in closed_trades if "STOP LOSS" in str(t.get('reason',''))]

        print("\n--- ISTATISTIKLER ---")
        print(f"Kazanma Orani (Win Rate): %{win_rate:.2f}")
        print(f"Kazandiran Islem: {len(winners)}")
        print(f"Kaybettiren Islem: {len(losers)}")

        avg_win  = sum(t['pnl'] for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t['pnl'] for t in losers)  / len(losers)  if losers  else 0
        print(f"Ortalama Kazanc: {avg_win:,.2f} TL")
        print(f"Ortalama Kayip: {avg_loss:,.2f} TL")
        print(f"Trailing Stop ile Kapanan Islem: {len(trailing_exits)}")

        # Max Drawdown (trade-by-trade)
        peak = running_pnl = 0
        drawdowns = []
        for tr in closed_trades:
            running_pnl += tr['pnl']
            if running_pnl > peak:
                peak = running_pnl
            drawdowns.append(peak - running_pnl)
        print(f"Maksimum Drawdown (Bakiye Bazli): {max(drawdowns) if drawdowns else 0:,.2f} TL")


if __name__ == "__main__":
    run_backtest()
