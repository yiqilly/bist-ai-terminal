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
    "signals": [],      # BUY sinyalleri (CORE + SWING)
    "core_signals": [], # sadece CORE_EDGE
    "swing_signals": [],# sadece SWING_EDGE
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
        "symbol":    sig.symbol,
        "setup":     sig.setup_type.value if hasattr(sig.setup_type, "value") else str(sig.setup_type),
        "entry":     _f(sig.entry),
        "stop":      _f(sig.stop),
        "target":    _f(sig.target),
        "rr":        _f(sig.rr_ratio, 1),
        "atr":       _f(sig.daily_atr, 3),
        "rs":        _f(sig.rs_score, 3),
        "rsi3":      _f(sig.rsi3, 1),
        "sector_str":_f(sig.sector_str, 1),
        "weight_pct":int(sig.weight * 100),
        "detail":    sig.detail,
        "action":    "AL",
    }


# ── Pipeline Loop ─────────────────────────────────────────────
def _pipeline_loop(bus, strategy, sector_eng, telegram, source_label):
    logger.info("Pipeline loop başlatıldı.")

    while True:
        try:
            snap = bus.get_snapshot()
            if snap is None:
                time.sleep(1)
                continue

            # Sektörler
            try:
                from data.sector_map import SYMBOL_SECTOR
                sector_counts: dict[str, list] = {}
                for sym, tick in snap.ticks.items():
                    sec = SYMBOL_SECTOR.get(sym, "Diğer")
                    sector_counts.setdefault(sec, []).append(
                        (tick.price - tick.prev_close) / tick.prev_close * 100
                        if getattr(tick, "prev_close", 0) > 0 else 0
                    )
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
            all_signals_out  = []
            core_signals_out = []
            swing_signals_out = []

            for sym, tick in snap.ticks.items():
                # Bar nesnesini tick'ten oluştur
                bar = _tick_to_bar(tick)
                if bar is None:
                    continue

                # Context oluştur
                from data.sector_map import SYMBOL_SECTOR
                sec_name = SYMBOL_SECTOR.get(sym, "Diğer")
                ctx = _build_ctx(tick, snap, sector_strength_map.get(sec_name, 50.0))

                sig = strategy.on_bar(sym, bar, ctx)

                if sig.is_signal:
                    s = _serialize_signal(sig)
                    all_signals_out.append(s)
                    if "CORE" in sig.setup_type.value:
                        core_signals_out.append(s)
                    else:
                        swing_signals_out.append(s)

                    # Telegram bildirimi (sadece yeni sinyaller)
                    key = f"{sym}_{sig._date}"
                    if key not in _notified:
                        _notified.add(key)
                        try:
                            telegram.send_buy(sig)
                        except Exception:
                            pass

            # Piyasa özeti
            ticks = list(snap.ticks.values())
            advancing  = sum(1 for t in ticks if getattr(t, "change_pct", 0) > 0)
            declining  = sum(1 for t in ticks if getattr(t, "change_pct", 0) < 0)
            unchanged  = len(ticks) - advancing - declining
            market_out = {
                "index_val":  _index_cache["val"],
                "change":     _index_cache["change"],
                "advancing":  advancing,
                "declining":  declining,
                "unchanged":  unchanged,
            }

            with _state_lock:
                _state["last_update"]   = time.strftime("%H:%M:%S")
                _state["source"]        = source_label
                _state["market"]        = market_out
                _state["signals"]       = all_signals_out
                _state["core_signals"]  = core_signals_out
                _state["swing_signals"] = swing_signals_out
                _state["sectors"]       = sectors_out

        except Exception as e:
            logger.error(f"Pipeline hatası: {e}", exc_info=True)

        time.sleep(2)


def _tick_to_bar(tick):
    """Tick nesnesini basit bar nesnesine çevirir."""
    price = getattr(tick, "price", 0)
    if not price:
        return None

    class _Bar:
        def __init__(self, t):
            import datetime
            self.timestamp = datetime.datetime.now()
            self.open  = getattr(t, "open",  price)
            self.high  = getattr(t, "high",  price)
            self.low   = getattr(t, "low",   price)
            self.close = price
            self.volume = getattr(t, "volume", 0)

    return _Bar(tick)


def _build_ctx(tick, snap, sector_strength: float) -> dict:
    """Tick + snapshot'tan EdgeMultiStrategy context'i oluşturur."""
    price  = getattr(tick, "price", 1) or 1
    prev   = getattr(tick, "prev_close", None)
    prev   = prev if (prev and prev > 0) else price  # None guard
    volume = getattr(tick, "volume", 0) or 0
    vol_ma = getattr(tick, "vol_ma", None)
    vol_ma = vol_ma if (vol_ma and vol_ma > 0) else (volume * 0.8 or 1)

    # RS: hissenin gün değişimi / endeks değişimi
    stock_ret   = (price - prev) / prev if prev > 0 else 0
    index_ret   = (_index_cache["change"] or 0) / 100
    rs_vs_index = 1 + stock_ret - index_ret

    # ATR — snapshot'ta varsa al, yoksa %3 tahmin
    atr = getattr(tick, "atr", None)
    atr = atr if (atr and atr > 0) else price * 0.03

    # RSI3, EMA9/21
    rsi3  = getattr(tick, "rsi",  None) or 50.0
    ema9  = getattr(tick, "ema9",  None) or 0.0
    ema21 = getattr(tick, "ema21", None) or 0.0

    # Gap-Up: açılış bir önceki kapanışın %1.5+ üstündeyse
    open_price = getattr(tick, "open", None) or price
    gap_up = ((open_price - prev) / prev > 0.015) if prev > 0 else False

    # Hacim spike: anlık hacim ortalamanın 2x üstü
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
        args=(bus, strategy, None, telegram, source),
        daemon=True,
        name="pipeline-loop",
    ).start()

    logger.info("Hazır.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
