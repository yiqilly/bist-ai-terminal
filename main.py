# ============================================================
# main.py — BIST v2 Web Server
#
# Başlatma:
#   python main.py                    # borsapy (gerçek)
#   python main.py --mock             # mock mod
#   uvicorn main:app --host 0.0.0.0 --port 8000
# ============================================================
import argparse
import asyncio
import logging
import math
import os
import sys
import threading
import time

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Global State ─────────────────────────────────────────────
_state: dict = {
    "last_update": None,
    "source": "boot",
    "market": {
        "index_val": 0, "change": 0,
        "advancing": 0, "declining": 0, "unchanged": 0,
    },
    "signals": [],       # BUY sinyalleri (CORE + SWING)
    "core_signals": [],  # sadece CORE_EDGE
    "swing_signals": [], # sadece SWING_EDGE
    "watching": [],      # WATCHING + CONFIRMING (yaklaşan sinyaller)
    "heatmap": [],       # tüm hisseler (ısı haritası)
    "sectors": [],
}
_state_lock  = threading.Lock()
_ws_clients: list[WebSocket] = []

# Daha önce bildirim gönderilen sinyaller (duplicate önlemi)
_notified: set[str] = set()


# ── Helpers ───────────────────────────────────────────────────
def _f(v, decimals=2):
    try:
        x = float(v)
        return 0 if (math.isnan(x) or math.isinf(x)) else round(x, decimals)
    except Exception:
        return 0


# ── Endeks Fetch (yfinance, 5dk cache) ───────────────────────
_index_cache = {"val": 0, "change": 0}

def _index_fetch_loop():
    while True:
        try:
            import yfinance as yf
            hist = yf.Ticker("XU100.IS").history(period="2d", interval="1d")
            if len(hist) >= 2:
                last, prev = hist["Close"].iloc[-1], hist["Close"].iloc[-2]
                _index_cache["val"]    = round(float(last), 0)
                _index_cache["change"] = round((last - prev) / prev * 100, 2)
        except Exception:
            pass
        time.sleep(300)


# ── Sinyal Serialize ──────────────────────────────────────────
def _serialize_signal(sig) -> dict:
    return {
        "symbol":     sig.symbol,
        "setup":      sig.setup_type.value if hasattr(sig.setup_type, "value") else str(sig.setup_type),
        "state":      sig.state.value if hasattr(sig.state, "value") else str(sig.state),
        "state_label":getattr(sig, "state_label", ""),
        "entry":      _f(sig.entry),
        "stop":       _f(sig.stop),
        "target":     _f(sig.target),
        "rr":         _f(sig.rr_ratio, 1),
        "atr":        _f(sig.daily_atr, 3),
        "rs":         _f(sig.rs_score, 3),
        "rsi3":       _f(sig.rsi3, 1),
        "sector_str": _f(sig.sector_str, 1),
        "weight_pct": int(sig.weight * 100),
        "detail":     sig.detail,
        "action":     "AL",
        "met":        getattr(sig, "conditions_met",  []),
        "miss":       getattr(sig, "conditions_miss", []),
    }


# ── Pipeline Loop ─────────────────────────────────────────────
def _pipeline_loop(bus, strategy, portfolio, telegram, source_label, cache=None, news_engine=None):
    logger.info("Pipeline loop başlatıldı.")

    while True:
        try:
            snap = bus.get_snapshot()
            if snap is None:
                time.sleep(1)
                continue

            if portfolio:
                portfolio.update_prices(snap)

            # Sektörler
            try:
                from data.sector_map import SYMBOL_SECTOR
                sector_counts: dict[str, list] = {}
                for sym, tick in snap.ticks.items():
                    sec = SYMBOL_SECTOR.get(sym, "Diğer")
                    # change_pct: cache'ten al (güvenilir), yoksa tick fiyatından hesapla
                    chg = 0.0
                    if cache:
                        sc = cache._data.get(sym)
                        if sc and sc.change_pct_reliable:
                            chg = sc.change_pct
                    sector_counts.setdefault(sec, []).append(chg)
                sectors_out = []
                for sec, changes in sorted(sector_counts.items()):
                    avg = sum(changes) / len(changes) if changes else 0
                    sectors_out.append({
                        "name":   sec,
                        "change": _f(avg),
                        "count":  len(changes),
                    })
            except Exception:
                sectors_out = []

            # Sektör gücü (0-100 scale)
            sector_strength_map: dict[str, float] = {}
            for s in sectors_out:
                # Basit lineer dönüşüm: -5%..+5% → 0..100
                strength = max(0.0, min(100.0, 50.0 + s["change"] * 10))
                sector_strength_map[s["name"]] = strength

            # EdgeMultiStrategy'ye bar ver
            all_signals_out   = []
            core_signals_out  = []
            swing_signals_out = []
            watching_out      = []

            from data.sector_map import SYMBOL_SECTOR
            for sym, tick in snap.ticks.items():
                bar = _tick_to_bar(tick)
                if bar is None:
                    continue

                sec_name = SYMBOL_SECTOR.get(sym, "Diğer")
                ctx = _build_ctx(tick, snap, sector_strength_map.get(sec_name, 50.0), cache, sym)

                sig = strategy.on_bar(sym, bar, ctx)

                # Çok İyi Haber (AL) Tetikleyicisi
                state_val = getattr(sig.state, "value", str(sig.state))
                if not getattr(sig, "is_signal", False) and state_val in ("WATCHING", "CONFIRMING"):
                    if news_engine and news_engine.has_positive_news(sym):
                        from strategy.edge_multi import EdgeState, SetupType
                        sig.set_state(EdgeState.SIGNAL)
                        sig.is_signal = True
                        sig.setup_type = SetupType.NEWS_EDGE
                        
                        atr = float(ctx.get("daily_atr", getattr(bar, "close", 1.0) * 0.03))
                        price = getattr(bar, "close", 1.0)
                        sig.entry    = price
                        sig.stop     = price - (atr * 1.5)
                        sig.target   = price + (atr * 3.0)
                        sig.rr_ratio = 2.0
                        sig.daily_atr = atr
                        sig.weight   = 20.0  # SWING ağırlığı varsayılan
                        
                        sig.detail = "🚀 ACİL ALIM: Sentiment Skoru Yüksek (Haber Tetiklemesi)"

                if getattr(sig, "is_signal", False):
                    s = _serialize_signal(sig)
                    all_signals_out.append(s)
                    setup_val = getattr(sig.setup_type, "value", str(sig.setup_type))
                    if "CORE" in setup_val:
                        core_signals_out.append(s)
                    else:
                        swing_signals_out.append(s)

                    # Telegram bildirimi (sadece yeni sinyaller)
                    key = f"{sym}_{sig._date}"
                    if key not in _notified:
                        _notified.add(key)
                        try:
                            telegram.send_buy(sig)
                            if portfolio:
                                portfolio.open_position(sig)
                        except Exception:
                            pass

                elif sig.state.value in ("WATCHING", "CONFIRMING"):
                    watching_out.append(_serialize_signal(sig))
                    
                    key = f"WATCH_{sym}_{sig.state.value}_{sig._date}"
                    if key not in _notified:
                        _notified.add(key)
                        try:
                            telegram.send_watch(sig)
                        except Exception:
                            pass

            # Piyasa özeti — cache'ten güvenilir change_pct al
            advancing = declining = unchanged = 0
            for sym in snap.ticks:
                chg = 0.0
                if cache:
                    sc = cache._data.get(sym)
                    if sc and sc.change_pct_reliable:
                        chg = sc.change_pct
                if chg > 0:   advancing += 1
                elif chg < 0: declining += 1
                else:         unchanged += 1
            market_out = {
                "index_val":  _index_cache["val"],
                "change":     _index_cache["change"],
                "advancing":  advancing,
                "declining":  declining,
                "unchanged":  unchanged,
            }

            # Bull vs Bear hesapla
            total = advancing + declining + unchanged or 1
            bull_pct = round(advancing / total * 100, 1)
            bear_pct = round(declining / total * 100, 1)
            if bull_pct >= 60:    regime = "BULL"
            elif bull_pct >= 50:  regime = "WEAK BULL"
            elif bear_pct >= 60:  regime = "BEAR"
            elif bear_pct >= 50:  regime = "WEAK BEAR"
            else:                 regime = "NÖTR"
            market_out["bull_pct"]  = bull_pct
            market_out["bear_pct"]  = bear_pct
            market_out["regime"]    = regime

            with _state_lock:
                _state["last_update"]   = time.strftime("%H:%M:%S")
                _state["source"]        = source_label
                _state["market"]        = market_out
                # Heatmap: tüm hisseler
                heatmap_out = []
                for sym, tick in snap.ticks.items():
                    price = getattr(tick, "price", 0) or 0
                    chg   = 0.0
                    if cache:
                        sc2 = cache._data.get(sym)
                        if sc2 and sc2.change_pct_reliable:
                            chg = sc2.change_pct
                    from data.sector_map import SYMBOL_SECTOR
                    sig = strategy._signals.get(sym) if strategy else None
                    heatmap_out.append({
                        "symbol": sym,
                        "price":  _f(price),
                        "change": _f(chg),
                        "sector": SYMBOL_SECTOR.get(sym, "Diğer"),
                        "met": getattr(sig, "conditions_met", []) if sig else [],
                        "miss": getattr(sig, "conditions_miss", []) if sig else []
                    })
                heatmap_out.sort(key=lambda x: x["change"], reverse=True)

                _state["signals"]       = all_signals_out
                _state["core_signals"]  = core_signals_out
                _state["swing_signals"] = swing_signals_out
                _state["watching"]      = watching_out
                _state["heatmap"]       = heatmap_out
                _state["sectors"]       = sectors_out
                
                news_out = []
                if getattr(sys.modules[__name__], "news_engine", None):
                    # modül seviyesinde news_engine var mi?
                    ne = getattr(sys.modules[__name__], "news_engine")
                    for n in getattr(ne, "get_news", lambda: [])()[:40]:
                        news_out.append({
                            "symbol": getattr(n, "symbol", ""),
                            "headline": getattr(n, "headline", ""),
                            "time": n.timestamp.strftime("%H:%M:%S") if hasattr(n, "timestamp") and n.timestamp else "",
                            "score": getattr(n, "sentiment", 0.0),
                        })
                elif news_engine:
                    # Arguman olarak gelen objeden cek
                    for n in news_engine.get_news()[:40]:
                        news_out.append({
                            "symbol": getattr(n, "symbol", ""),
                            "headline": getattr(n, "headline", ""),
                            "time": n.timestamp.strftime("%H:%M:%S") if hasattr(n, "timestamp") and n.timestamp else "",
                            "score": getattr(n, "sentiment", 0.0),
                        })
                _state["news"] = news_out

            if portfolio:
                for sell_sym, reason in portfolio.check_exits(news_engine=news_engine):
                    try:
                        telegram.send_sell(sell_sym, reason)
                    except Exception as e:
                        logger.error(f"SAT bildirimi hatasi ({sell_sym}): {e}")

        except Exception as e:
            logger.error(f"Pipeline hatası: {e}", exc_info=True)

        time.sleep(2)


def _tick_to_bar(tick):
    """Tick nesnesini basit bar nesnesine çevirir."""
    price = getattr(tick, "price", 0)
    if not price:
        return None

    class _Bar:
        def __init__(self, t, p):
            import datetime
            self.timestamp = datetime.datetime.now()
            self.open   = getattr(t, "open",  p)  or p
            self.high   = getattr(t, "high",  p)  or p
            self.low    = getattr(t, "low",   p)  or p
            self.close  = p
            self.volume = getattr(t, "volume", 0) or 0

    return _Bar(tick, price)


def _build_ctx(tick, snap, sector_strength: float, cache=None, sym: str = "") -> dict:
    """
    Tick + SnapshotCache'ten EdgeMultiStrategy context'i oluşturur.
    Cache varsa bar geçmişinden RSI3, EMA9/21, ATR hesaplar.
    """
    from strategy.indicator_engine import IndicatorEngine

    price  = getattr(tick, "price", 1) or 1
    volume = getattr(tick, "volume", 0) or 0

    # ── SnapshotCache'ten sembol verisi al ────────────────────
    sc = None
    if cache and sym:
        sc = cache._data.get(sym)

    # prev_close
    prev = (sc.prev_close if sc and sc.prev_close > 0 else None) or price

    # Gün değişimi
    stock_chg_pct = (sc.change_pct if sc and sc.change_pct_reliable else
                     (price - prev) / prev * 100 if prev > 0 else 0)

    # RS vs endeks: 1 + (hisse%) - (endeks%) → normalize
    index_chg_pct = _index_cache.get("change") or 0
    rs_vs_index   = 1 + (stock_chg_pct - index_chg_pct) / 100

    # ── Bar geçmişinden indikatörler ─────────────────────────
    atr   = price * 0.03   # fallback
    rsi3  = 50.0
    ema9  = 0.0
    ema21 = 0.0
    vol_ma = volume * 0.8 or 1
    gap_up = False

    if sc:
        bars_1m = list(sc.bars.get("1m", []))
        bars_5m = list(sc.bars.get("5m", []))
        bars = bars_5m if len(bars_5m) >= 5 else bars_1m

        if len(bars) >= 4:
            closes  = [b.close for b in bars]
            highs   = [b.high  for b in bars]
            lows    = [b.low   for b in bars]
            volumes = [b.volume for b in bars]

            # RSI(3) — son 4 kapanış yeterli
            rsi3 = IndicatorEngine.rsi(closes, period=min(3, len(closes)-1))

            # EMA9 / EMA21
            if len(closes) >= 9:
                ema9  = IndicatorEngine.ema(closes, 9)
            if len(closes) >= 21:
                ema21 = IndicatorEngine.ema(closes, 21)

            # ATR(14)
            if len(closes) >= 2:
                _calc = IndicatorEngine.atr(highs, lows, closes, period=min(14, len(closes)-1))
                if _calc and _calc > 0.01:
                    atr = _calc

            # Vol MA (20 bar ort)
            if len(volumes) >= 5:
                vol_ma = sum(volumes[-20:]) / min(20, len(volumes))

            # Gap-Up: ilk bar'ın open'ı prev_close'tan %1.5+ yüksek mi?
            if bars and prev > 0:
                gap_up = (bars[0].open - prev) / prev > 0.015

    # Hacim spike
    vol_spike = (volume > vol_ma * 2) if vol_ma > 0 else False

    return {
        "rs_vs_index":     rs_vs_index,
        "sector_strength": sector_strength,
        "daily_atr":       atr,
        "rsi_3":           rsi3,
        "ema9_daily":      ema9,
        "ema21_daily":     ema21,
        "vol_ma":          vol_ma,
        "intraday_vol":    volume,
        "vol_spike":       vol_spike,
        "gap_up":          gap_up,
    }


# ── FastAPI ───────────────────────────────────────────────────
app = FastAPI(title="BIST v2 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"],
)


@app.get("/")
async def root():
    path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(path) if os.path.exists(path) else {"status": "BIST v2 çalışıyor"}


@app.get("/api/status")
async def get_status():
    with _state_lock:
        return dict(_state)


@app.get("/api/health")
async def health():
    return {"status": "ok", "last_update": _state.get("last_update")}


def _fmt_large_num(val):
    try:
        f = float(val)
        if abs(f) >= 1_000_000_000: return f"{f/1_000_000_000:.2f} Milyar"
        if abs(f) >= 1_000_000:     return f"{f/1_000_000:.2f} Milyon"
        if abs(f) >= 1_000:         return f"{f/1_000:.2f} Bin"
        return str(round(f, 2))
    except (ValueError, TypeError):
        return str(val)

@app.get("/api/fundamentals/{symbol}")
async def api_fundamentals(symbol: str):
    import borsapy
    try:
        t = borsapy.Ticker(symbol)
        
        info_dict = dict(t.info) if hasattr(t.info, "keys") else {}
            
        bs_list = []
        bs = t.balance_sheet
        if bs is not None and not bs.empty:
            col = bs.columns[0]
            for idx, val in bs.head(10)[col].items():
                bs_list.append({"item": str(idx).strip(), "value": _fmt_large_num(val)})
                
        inc_list = []
        inc = t.income_stmt
        if inc is not None and not inc.empty:
            col = inc.columns[0]
            for idx, val in inc.head(10)[col].items():
                inc_list.append({"item": str(idx).strip(), "value": _fmt_large_num(val)})

        holders = []
        hm = t.major_holders
        if hm is not None and not hm.empty:
            for idx, row in hm.head(10).iterrows():
                # NaN degerleri bos dizeye cevir
                clean_row = {str(k): (str(v) if str(v) != 'nan' else '') for k, v in row.items()}
                holders.append(clean_row)
        
        return {
            "symbol": symbol,
            "info": info_dict,
            "balance_sheet": bs_list,
            "income_stmt": inc_list,
            "major_holders": holders
        }
    except Exception as e:
        logger.error(f"Fundamentals error for {symbol}: {e}")
        return {"error": str(e)}



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            with _state_lock:
                data = dict(_state)
            await websocket.send_json(data)
            await asyncio.sleep(2)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


# ── Startup ───────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mock",     action="store_true")
    parser.add_argument("--universe", default=None)
    args, _ = parser.parse_known_args()

    force_mock  = os.environ.get("FORCE_MOCK", "").lower() in ("1", "true", "yes")
    use_mock    = args.mock or force_mock
    source      = "mock" if use_mock else "borsapy"

    from config import UNIVERSE as default_universe
    from data.symbols import get_universe
    universe_name = args.universe or os.environ.get("UNIVERSE", default_universe)
    symbols       = get_universe(universe_name)

    logger.info(f"BIST v2 başlatılıyor — kaynak={source} evren={universe_name}({len(symbols)})")

    # Data katmanı
    from data.adapters.mock_adapter import MockMarketDataAdapter
    from data.market_bus import MarketBus

    adapter = MockMarketDataAdapter(update_interval=999)
    bus     = MarketBus(adapter=adapter, snapshot_interval=1.0)

    snap_cache = None
    try:
        cfg = {}
        try:
            import yaml
            cfg_path = os.path.join(os.path.dirname(__file__), "config", "data_sources.yaml")
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            pass

        from data.collector_bridge import make_realtime_bus
        bridge = make_realtime_bus(bus, source=source, config=cfg)
        ok = bridge.start(symbols=symbols)
        if ok:
            bus.attach_collector(bridge, bridge.cache)
            snap_cache = bridge.cache
            logger.info(f"Collector: {bridge.collector.__class__.__name__}")
        else:
            raise RuntimeError("borsapy bağlanamadı")
    except Exception as e:
        logger.warning(f"{e} — mock moda geçildi")
        source = "mock"
        adapter._update_interval = 2.0
        adapter.connect()
        adapter.subscribe(symbols)

    # Strateji
    from strategy.edge_multi import EdgeMultiStrategy
    strategy = EdgeMultiStrategy()

    # Haber Motoru
    try:
        from news.news_engine import NewsEngine
        news_engine = NewsEngine()
    except ImportError:
        news_engine = None
        logger.warning("NewsEngine yüklenemedi.")

    # Portföy Tracker
    try:
        from portfolio.engine import PortfolioEngine
        portfolio = PortfolioEngine()
    except ImportError:
        portfolio = None
        logger.warning("PortfolioEngine yüklenemedi.")

    # Telegram
    from alerts.telegram import TelegramNotifier
    telegram = TelegramNotifier(
        token=os.environ.get("TELEGRAM_TOKEN", ""),
        chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
    )

    bus.start()

    # Endeks fetch
    threading.Thread(target=_index_fetch_loop, daemon=True, name="index-fetch").start()

    # Pipeline
    threading.Thread(
        target=_pipeline_loop,
        args=(bus, strategy, portfolio, telegram, source, snap_cache, news_engine),
        daemon=True,
        name="pipeline-loop",
    ).start()

    logger.info("Hazır.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
