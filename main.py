# ============================================================
# main.py — BIST Trading Cockpit v6
#
# Başlatma:
#   python main.py                  # borsapy (gerçek)
#   python main.py --source mock    # mock mod
#   python main.py --mock           # kısayol
# ============================================================
import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from utils.logger import setup_logging

logger = setup_logging()

# borsapy / websocket iç loglarını sustur
try:
    from utils.collector_logger import silence_borsapy_noise
    silence_borsapy_noise()
except Exception:
    pass


def load_config() -> dict:
    try:
        import yaml
        cfg_path = os.path.join(os.path.dirname(__file__), "config", "data_sources.yaml")
        if os.path.exists(cfg_path):
            with open(cfg_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}


def main():
    parser = argparse.ArgumentParser(description="BIST Trading Cockpit v6")
    parser.add_argument("--source", choices=["borsapy", "mock"], default=None)
    parser.add_argument("--mock",   action="store_true")
    parser.add_argument("--universe", choices=["BIST30", "BIST50", "BIST100"],
                        default=None)
    args = parser.parse_args()

    cfg    = load_config()
    source = "mock" if args.mock else (args.source or cfg.get("active_source", "borsapy"))

    # Universe seç
    from config import UNIVERSE as default_universe
    universe_name = args.universe or default_universe
    from data.symbols import get_universe
    symbols = get_universe(universe_name)

    logger.info(f"BIST Trading Cockpit v6 başlatılıyor — kaynak={source} evren={universe_name}({len(symbols)})")

    # ── Mock adapter (scanner uyumu için) ───────────────────
    from data.adapters.mock_adapter import MockMarketDataAdapter
    from data.market_bus import MarketBus

    adapter = MockMarketDataAdapter(update_interval=999)
    bus     = MarketBus(adapter=adapter, snapshot_interval=1.0)

    # ── Realtime collector ──────────────────────────────────
    from data.collector_bridge import make_realtime_bus
    bridge = make_realtime_bus(bus, source=source, config=cfg)
    ok = bridge.start(symbols=symbols)
    if ok:
        bus.attach_collector(bridge, bridge.cache)
        logger.info(f"Collector: {bridge.collector.__class__.__name__}")
    else:
        logger.warning("Collector başlatılamadı — mock adapter devreye alındı")
        adapter._update_interval = 2.0
        adapter.connect()
        adapter.subscribe(symbols)

    # ── Cache → Indicators + Scanner inject ─────────────────
    from strategy import indicators as ind
    ind.set_cache(bridge.cache)
    from strategy.scanner import set_scanner_cache
    set_scanner_cache(bridge.cache)

    # ── Engine'ler ───────────────────────────────────────────
    from strategy.scanner            import MarketScanner
    from strategy.market_context_engine import MarketContextEngine
    from strategy.summary_builder    import TechnicalSummaryBuilder
    from strategy.sector_strength    import SectorStrengthEngine
    from signals.ranking             import SignalRanker
    from signals.history             import SignalHistory
    from signals.combined_scoring    import CombinedScorer
    from risk.risk_engine            import RiskEngine
    from portfolio.portfolio_engine  import PortfolioEngine
    from news.news_engine            import NewsEngine
    from recommendations.broker_engine import BrokerEngine
    from recommendations.consensus   import ConsensusEngine
    from alerts.alert_engine         import AlertEngine
    from watchlist.watchlist_engine  import WatchlistEngine
    from charts.history_provider     import HistoryProvider

    scanner   = MarketScanner(adapter)
    regime    = MarketContextEngine()   # FAZ 2: eski RegimeEngine yerine
    summary   = TechnicalSummaryBuilder()
    sector_eng = SectorStrengthEngine()
    news      = NewsEngine()
    broker    = BrokerEngine()
    scorer    = CombinedScorer(news)
    ranker    = SignalRanker(RiskEngine(), scorer)
    history   = SignalHistory()
    portfolio = PortfolioEngine()
    alerts    = AlertEngine()
    watchlist = WatchlistEngine()
    hist_prov = HistoryProvider()
    consensus = ConsensusEngine()

    bus.start()
    logger.info("MarketBus başlatıldı.")

    from ui.app import TradingCockpit
    app = TradingCockpit(
        market_bus      = bus,
        scanner         = scanner,
        ranker          = ranker,
        signal_history  = history,
        portfolio       = portfolio,
        news_engine     = news,
        broker_engine   = broker,
        regime_engine   = regime,
        summary_builder = summary,
        alert_engine    = alerts,
        watchlist       = watchlist,
        history_provider= hist_prov,
        consensus_engine= consensus,
        sector_engine   = sector_eng,
        snapshot_cache  = bridge.cache,
        source_label    = source,
    )

    logger.info(f"Cockpit hazır — kaynak={source} evren={universe_name}")
    app.mainloop()

    bridge.stop()
    bus.stop()
    logger.info("Cockpit kapatıldı.")


if __name__ == "__main__":
    main()
