# ============================================================
# web_server.py — BIST Terminal Headless Web Server
#
# Tkinter olmadan tam pipeline'ı çalıştırır.
# FastAPI + WebSocket üzerinden gerçek sinyal verisi sunar.
#
# Başlatma:
#   python web_server.py                 # borsapy (gerçek)
#   python web_server.py --mock          # mock mod (Render/test)
#   uvicorn web_server:app --host 0.0.0.0 --port 8000
# ============================================================
import argparse
import asyncio
import logging
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

# ── Global pipeline state ────────────────────────────────────
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
    "rs": [],
}
_state_lock = threading.Lock()
_ws_clients: list[WebSocket] = []


# ── Serializers ──────────────────────────────────────────────
def _serialize_signal(rs) -> dict:
    c = rs.candidate
    r = rs.risk
    change_pct = round((c.price - c.prev_price) / c.prev_price * 100, 2) if c.prev_price else 0
    return {
        "symbol":    c.symbol,
        "price":     round(c.price, 2),
        "change":    change_pct,
        "rsi":       round(c.rsi, 1),
        "ema9":      round(c.ema9, 2),
        "ema21":     round(c.ema21, 2),
        "atr":       round(c.atr, 3),
        "momentum":  round(c.momentum, 2),
        "score":     rs.combined_score,
        "ai_score":  round(rs.ai_score, 1),
        "quality":   rs.quality_label,
        "trust":     round(rs.confidence * 100, 1),
        "entry":     round(r.entry, 2),
        "stop":      round(r.stop, 2),
        "target":    round(r.target, 2),
        "rr":        round(r.rr_ratio, 2),
        "action":    "AL",
        "setup":     rs.core_setup_type if rs.core_setup_type != "None" else "Sinyal",
        "strategy":  "BULL_BREAKOUT" if c.breakout else "TREND",
        "lot":       rs.position_size.lots if rs.position_size else 0,
        "alerts":    rs.alerts,
    }


def _serialize_candidate(c) -> dict:
    change_pct = round((c.price - c.prev_price) / c.prev_price * 100, 2) if c.prev_price else 0
    return {
        "symbol":   c.symbol,
        "price":    round(c.price, 2),
        "change":   change_pct,
        "rsi":      round(c.rsi, 1),
        "ema9":     round(c.ema9, 2),
        "ema21":    round(c.ema21, 2),
        "score":    c.score,
        "action":   "IZLE",
        "quality":  "B",
        "trust":    60,
        "setup":    "İzle",
        "strategy": "RANGE",
        "entry":    round(c.price, 2),
        "stop":     round(c.price * 0.97, 2),
        "target":   round(c.price * 1.04, 2),
        "rr":       1.5,
        "lot":      0,
        "alerts":   [],
    }


# ── Pipeline loop (background thread) ───────────────────────
def _pipeline_loop(bus, scanner, ranker, regime_eng, sector_eng, rs_eng,
                   portfolio, source_label):
    """Gerçek pipeline'ı her 2 saniyede çalıştırır, _state'i günceller."""
    logger.info("Pipeline loop başlatıldı.")
    while True:
        try:
            snap = bus.latest_snapshot()
            if snap is None:
                time.sleep(1)
                continue

            # Analiz
            candidates  = scanner.scan(snap)
            ranked      = ranker.rank(candidates, snap)
            regime      = regime_eng.analyze(snap)

            # Sector
            try:
                sector_eng.update(snap)
                sectors_raw = sector_eng.get_summary()
                sectors = [{"name": s.sector, "change": round(s.avg_change, 2),
                            "strength": round(s.strength, 1), "count": s.count}
                           for s in sectors_raw] if sectors_raw else []
            except Exception:
                sectors = []

            # RS
            try:
                rs_eng.update(snap)
                rs_data = rs_eng.get_top(10)
                rs_list = [{"symbol": r.symbol, "rs": round(r.rs_score, 2),
                            "rank": r.rank} for r in rs_data] if rs_data else []
            except Exception:
                rs_list = []

            # Positions
            try:
                pos_list = []
                for pos in portfolio.get_open_positions():
                    cur_price = snap.ticks.get(pos.symbol)
                    price = cur_price.last if cur_price else pos.entry_price
                    pnl = round((price - pos.entry_price) / pos.entry_price * 100, 2)
                    pos_list.append({
                        "symbol": pos.symbol, "price": round(price, 2),
                        "entry": round(pos.entry_price, 2), "lot": pos.lots,
                        "pnl": pnl, "stop": round(pos.stop_price, 2),
                        "target": round(pos.target_price, 2),
                    })
            except Exception:
                pos_list = []

            # Signals / Setups / Watchlist / Opportunities
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

            # Market context
            market_out = {
                "index_val":  round(regime.index_price, 2) if hasattr(regime, "index_price") else 0,
                "change":     round(regime.index_change, 2) if hasattr(regime, "index_change") else 0,
                "regime":     str(regime.regime) if hasattr(regime, "regime") else "NÖTR",
                "score":      round(regime.score, 1) if hasattr(regime, "score") else 50,
                "advancing":  snap.advancing if hasattr(snap, "advancing") else 0,
                "declining":  snap.declining if hasattr(snap, "declining") else 0,
                "unchanged":  snap.unchanged if hasattr(snap, "unchanged") else 0,
            }

            with _state_lock:
                _state["last_update"]   = time.strftime("%H:%M:%S")
                _state["source"]        = source_label
                _state["market"]        = market_out
                _state["signals"]       = signals_out
                _state["setups"]        = setups_out
                _state["watchlist"]     = watchlist_out
                _state["opportunities"] = opportunities_out
                _state["positions"]     = pos_list
                _state["sectors"]       = sectors
                _state["rs"]            = rs_list

        except Exception as e:
            logger.error(f"Pipeline loop hatası: {e}", exc_info=True)

        time.sleep(2)


# ── FastAPI app ──────────────────────────────────────────────
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
    return {"status": "BIST Terminal API çalışıyor", "endpoints": ["/api/status", "/ws"]}


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
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket hatası: {e}")
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
        logger.info(f"WebSocket ayrıldı. Toplam: {len(_ws_clients)}")


# ── Startup: pipeline'ı başlat ───────────────────────────────
@app.on_event("startup")
async def startup_event():
    import yaml

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mock",    action="store_true")
    parser.add_argument("--source",  default=None)
    parser.add_argument("--universe", default=None)
    args, _ = parser.parse_known_args()

    # Render ortamında mock mod (borsapy bağlantısı test edilmeden önce)
    force_mock = os.environ.get("FORCE_MOCK", "").lower() in ("1", "true", "yes")
    source = "mock" if (args.mock or force_mock) else (args.source or "borsapy")

    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "config", "data_sources.yaml")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        cfg = {}

    if source == "borsapy" and not args.mock:
        env_source = cfg.get("active_source", "borsapy")
        source = env_source

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
    from recommendations.broker_engine  import BrokerEngine

    try:
        from strategy.relative_strength import RelativeStrengthEngine
        rs_eng = RelativeStrengthEngine()
    except Exception:
        rs_eng = None

    scanner    = MarketScanner(adapter)
    regime_eng = MarketContextEngine()
    sector_eng = SectorStrengthEngine()
    news       = NewsEngine()
    scorer     = CombinedScorer(news)
    ranker     = SignalRanker(RiskEngine(), scorer)
    portfolio  = PortfolioEngine()

    bus.start()
    logger.info("MarketBus başladı.")

    # Pipeline'ı arka planda başlat
    t = threading.Thread(
        target=_pipeline_loop,
        args=(bus, scanner, ranker, regime_eng, sector_eng, rs_eng, portfolio, source),
        daemon=True,
        name="pipeline-loop",
    )
    t.start()
    logger.info("Pipeline loop thread başlatıldı.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("web_server:app", host="0.0.0.0", port=port, reload=False)
