# ============================================================
# web_server.py — BIST Terminal Headless Web Server
#
# Tkinter olmadan tam pipeline'ı çalıştırır.
# FastAPI + WebSocket üzerinden gerçek sinyal verisi sunar.
#
# Başlatma:
#   python web_server.py                 # borsapy (gerçek)
#   python web_server.py --mock          # mock mod
#   uvicorn web_server:app --host 0.0.0.0 --port 8000
# ============================================================
import argparse
import asyncio
import logging
import math
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

from utils.logger import setup_logging
logger = setup_logging()

try:
    from utils.collector_logger import silence_borsapy_noise
    silence_borsapy_noise()
except Exception:
    pass

# ── Global state ─────────────────────────────────────────────
_state: dict = {
    "last_update": None,
    "source": "boot",
    "market": {"index_val": 0, "change": 0, "regime": "NÖTR", "score": 50,
               "advancing": 0, "declining": 0, "unchanged": 0},
    "signals": [],
    "opportunities": [],
    "setups": [],
    "watchlist": [],
    "positions": [],
    "sectors": [],
}
_state_lock = threading.Lock()
_ws_clients: list[WebSocket] = []


# ── Helpers ───────────────────────────────────────────────────
def _f(v, decimals=2):
    """Float'u güvenli yuvarlar; NaN/Inf → 0."""
    try:
        x = float(v)
        return 0 if (math.isnan(x) or math.isinf(x)) else round(x, decimals)
    except Exception:
        return 0


# ── Serializers ───────────────────────────────────────────────
def _serialize_signal(rs) -> dict:
    c = rs.candidate
    r = rs.risk
    change_pct = _f((c.price - c.prev_price) / c.prev_price * 100) if c.prev_price else 0
    return {
        "symbol":   c.symbol,
        "price":    _f(c.price),
        "change":   change_pct,
        "rsi":      _f(c.rsi, 1),
        "ema9":     _f(c.ema9),
        "ema21":    _f(c.ema21),
        "atr":      _f(c.atr, 3),
        "momentum": _f(c.momentum),
        "score":    _f(rs.combined_score, 1),
        "ai_score": _f(rs.ai_score, 1),
        "quality":  rs.quality_label,
        "trust":    _f(rs.confidence * 100, 1),
        "entry":    _f(r.entry),
        "stop":     _f(r.stop),
        "target":   _f(r.target),
        "rr":       _f(r.rr_ratio),
        "action":   "AL",
        "setup":    rs.core_setup_type if rs.core_setup_type != "None" else "Sinyal",
        "strategy": "BULL_BREAKOUT" if c.breakout else "TREND",
        "lot":      rs.position_size.lots if rs.position_size else 0,
        "alerts":   rs.alerts,
        "sector":   "",
    }


def _serialize_candidate(c) -> dict:
    change_pct = _f((c.price - c.prev_price) / c.prev_price * 100) if c.prev_price else 0
    return {
        "symbol":   c.symbol,
        "price":    _f(c.price),
        "change":   change_pct,
        "rsi":      _f(c.rsi, 1),
        "ema9":     _f(c.ema9),
        "ema21":    _f(c.ema21),
        "score":    c.score,
        "action":   "IZLE",
        "quality":  "B",
        "trust":    60,
        "setup":    "İzle",
        "strategy": "RANGE",
        "entry":    _f(c.price),
        "stop":     _f(c.price * 0.97),
        "target":   _f(c.price * 1.04),
        "rr":       1.5,
        "lot":      0,
        "alerts":   [],
        "sector":   "",
    }


# ── Pipeline loop (background thread) ────────────────────────
def _pipeline_loop(bus, scanner, ranker, context_eng, sector_eng, portfolio, source_label):
    logger.info("Pipeline loop başlatıldı.")
    while True:
        try:
            snap = bus.get_snapshot()
            if snap is None:
                time.sleep(1)
                continue

            # Tarama + bağlam
            candidates = scanner.scan(snap)
            context    = context_eng.compute(snap, candidates)  # MarketContext
            ranked     = ranker.rank(candidates, context, candidates)

            # Sektörler
            try:
                sectors_dict = sector_eng.compute(candidates, snap)
                sectors_out = [
                    {
                        "name":     ss.name,
                        "change":   _f(ss.avg_change_pct),
                        "strength": _f(ss.strength, 1),
                        "count":    len(ss.symbols),
                    }
                    for ss in sectors_dict.values()
                ]
            except Exception:
                sectors_out = []

            # Pozisyonlar
            try:
                pos_out = []
                for pos in portfolio.positions:
                    tick = snap.ticks.get(pos.symbol)
                    price = _f(tick.last if tick else pos.avg_cost)
                    pos_out.append({
                        "symbol": pos.symbol,
                        "price":  price,
                        "entry":  _f(pos.avg_cost),
                        "qty":    _f(pos.quantity),
                        "pnl":    _f(pos.pnl_pct, 2),
                    })
            except Exception:
                pos_out = []

            # Sinyal listelerini ayır
            signals_out      = []
            setups_out       = []
            watchlist_out    = []
            opportunities_out = []

            for rs in ranked[:20]:
                s = _serialize_signal(rs)
                if rs.quality_label in ("A+", "A"):
                    signals_out.append(s)
                    opportunities_out.append(s)
                else:
                    setups_out.append(s)

            for c in candidates:
                if c.score < 3:
                    watchlist_out.append(_serialize_candidate(c))

            # Piyasa bağlamı
            market_out = {
                "index_val":  0,
                "change":     0,
                "regime":     context.regime,
                "label":      context.label,
                "score":      _f(context.market_strength, 1),
                "advancing":  context.advancing,
                "declining":  context.declining,
                "unchanged":  context.unchanged,
                "breadth":    _f(context.breadth_pct, 1),
            }

            with _state_lock:
                _state["last_update"]    = time.strftime("%H:%M:%S")
                _state["source"]         = source_label
                _state["market"]         = market_out
                _state["signals"]        = signals_out
                _state["setups"]         = setups_out
                _state["watchlist"]      = watchlist_out
                _state["opportunities"]  = opportunities_out
                _state["positions"]      = pos_out
                _state["sectors"]        = sectors_out

        except Exception as e:
            logger.error(f"Pipeline loop hatası: {e}", exc_info=True)

        time.sleep(2)


# ── FastAPI ───────────────────────────────────────────────────
app = FastAPI(title="BIST Terminal Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"],
)


@app.get("/")
async def root():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "BIST Terminal API çalışıyor"}


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
    logger.info(f"WebSocket bağlandı. Toplam: {len(_ws_clients)}")
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
    import yaml

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mock",     action="store_true")
    parser.add_argument("--source",   default=None)
    parser.add_argument("--universe", default=None)
    args, _ = parser.parse_known_args()

    force_mock = os.environ.get("FORCE_MOCK", "").lower() in ("1", "true", "yes")
    source = "mock" if (args.mock or force_mock) else (args.source or "borsapy")

    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "config", "data_sources.yaml")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        cfg = {}

    if not (args.mock or force_mock):
        source = cfg.get("active_source", "borsapy")

    from config import UNIVERSE as default_universe
    from data.symbols import get_universe
    universe_name = args.universe or os.environ.get("UNIVERSE", default_universe)
    symbols = get_universe(universe_name)

    logger.info(f"Web Server başlatılıyor — kaynak={source} evren={universe_name}({len(symbols)})")

    from data.adapters.mock_adapter import MockMarketDataAdapter
    from data.market_bus import MarketBus

    adapter = MockMarketDataAdapter(update_interval=999)
    bus = MarketBus(adapter=adapter, snapshot_interval=1.0)

    from data.collector_bridge import make_realtime_bus
    bridge = make_realtime_bus(bus, source=source, config=cfg)
    ok = bridge.start(symbols=symbols)
    if ok:
        bus.attach_collector(bridge, bridge.cache)
        logger.info(f"Collector başladı: {bridge.collector.__class__.__name__}")
    else:
        logger.warning("borsapy bağlanamadı — mock moda geçildi")
        source = "mock"
        adapter._update_interval = 2.0
        adapter.connect()
        adapter.subscribe(symbols)

    from strategy import indicators as ind
    ind.set_cache(bridge.cache)
    from strategy.scanner import set_scanner_cache
    set_scanner_cache(bridge.cache)

    from strategy.scanner               import MarketScanner
    from strategy.market_context_engine import MarketContextEngine
    from strategy.sector_strength       import SectorStrengthEngine
    from signals.ranking                import SignalRanker
    from signals.combined_scoring       import CombinedScorer
    from risk.risk_engine               import RiskEngine
    from portfolio.portfolio_engine     import PortfolioEngine
    from news.news_engine               import NewsEngine

    scanner     = MarketScanner(adapter)
    context_eng = MarketContextEngine()
    sector_eng  = SectorStrengthEngine()
    news        = NewsEngine()
    scorer      = CombinedScorer(news)
    ranker      = SignalRanker(RiskEngine(), scorer)
    portfolio   = PortfolioEngine()

    bus.start()
    logger.info("MarketBus başladı.")

    t = threading.Thread(
        target=_pipeline_loop,
        args=(bus, scanner, ranker, context_eng, sector_eng, portfolio, source),
        daemon=True,
        name="pipeline-loop",
    )
    t.start()
    logger.info("Pipeline loop thread başlatıldı.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("web_server:app", host="0.0.0.0", port=port, reload=False)
