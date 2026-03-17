# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

BIST Terminal is a real-time algorithmic trading cockpit for the Istanbul Stock Exchange (BIST). It has two interfaces: a Tkinter desktop GUI (`main.py`) and a FastAPI web service (`web_api_cloud.py` + `index.html`).

## Running the Application

```bash
# Desktop cockpit (real data via borsapy/TradingView)
python main.py

# Desktop cockpit with mock data (no live connection needed)
python main.py --mock

# Specify universe
python main.py --universe BIST30   # BIST30, BIST50, BIST100

# Auto-start at market open (09:59:30)
python start_at_open.py

# Cloud/web API (port 8000, uses yfinance)
uvicorn web_api_cloud:app --reload
```

## Testing & Validation

```bash
# Test live borsapy connection
python scripts/test_live_connection.py
python scripts/test_live_connection.py --duration 60 --symbols AKBNK,GARAN,ISCTR

# Validate signal generation
python scripts/validate_signals.py

# Run backtests
python strategy/core/run_backtest.py
python strategy/edge_backtest/run_edge_backtest.py

# Test data collection standalone
python scripts/run_collector.py
```

## Build

```bash
python build_exe.py   # Creates dist/BIST_Terminal.exe via PyInstaller
```

## Architecture

The system is a pipeline: **Data Collection → Analysis Engines → Signal Generation → Risk/Portfolio → UI/Output**

### Data Layer (`data/`)
- `collector_bridge.py` — Normalizes ticks from borsapy or mock adapter and feeds the cache
- `snapshot_cache.py` — Central state store (`SnapshotCache`). Holds a `SymbolCache` per symbol containing price, volume, bars, and indicator values. This is the "source of truth" consumed by all analysis engines.
- `market_bus.py` — Event publisher. Publishes a `MarketSnapshot` (all symbol states) every ~1 second to registered listeners.
- `bar_builder.py` — Builds 1m/5m OHLCV candles from tick stream.

### Strategy Layer (`strategy/`)
- `scanner.py` — `MarketScanner` screens all symbols and produces `SignalCandidate` objects.
- `market_context_engine.py` — Detects market regime (trending/ranging/volatile) and breadth metrics.
- `indicators.py` / `indicator_engine.py` — RSI, EMA, ATR, etc. Injected into `SnapshotCache` to avoid circular imports.
- `sector_strength.py`, `relative_strength.py` — Sector rotation and RS scoring.

### Signal Layer (`signals/`)
- `trade_signal_engine.py` — Core buy criteria evaluation (RSI ranges, EMA alignment, sector strength, etc.)
- `opportunity_engine.py` — Produces `OpportunityCandidate` objects from scan results.
- `combined_scorer.py` — AI-weighted scoring across breakout, volume, RSI, momentum, EMA factors.
- `signal_ranker.py` — Final ranking and deduplication.

### Risk & Portfolio (`risk/`, `portfolio/`)
- `risk_engine.py` — ATR-based stop/target calculation, risk-reward filtering.
- `portfolio_engine.py` — Tracks open positions and P&L.
- `position_manager.py` — Trade lifecycle (entry → monitor → exit).
- `position_sizer.py` — Lot sizing based on 50k TL capital and 1.5% risk per trade (max 5 positions). These defaults are in `config.py`.

### Contextual Engines
- `news/` — KAP feed scraping and sentiment boost for signals.
- `recommendations/` — Broker consensus aggregation.
- `alerts/` — `AlertEngine` with Telegram notification support.

### UI Layer (`ui/`)
- `app.py` — `TradingCockpit` main window (Tkinter), hosts 20+ specialized panel classes.
- Panels include: `HeatmapPanel`, `MarketContextPanel`, `SectorPanel`, `RSPanel`, `BuySignalsPanel`, `PositionPanel`, `RiskDashboardPanel`, `NewsPanel`, etc.

### Web Interface
- `web_api_cloud.py` — FastAPI app serving REST endpoints backed by yfinance (not borsapy). Used for the hosted/cloud variant.
- `index.html` — HTML5 single-page web cockpit that consumes the FastAPI endpoints.

## Configuration

- `config.py` — Primary config: universe selection, signal criteria, risk parameters, AI scoring weights.
- `config/data_sources.yaml` — Active data source (`borsapy`/`mock`/`csv`), symbol list, timeframes, reconnect settings.

## Key Design Patterns

- **No circular imports**: `IndicatorEngine` is injected into `SnapshotCache` rather than imported directly, because `strategy/` would otherwise depend on `data/` which depends on `strategy/`.
- **Mock mode**: Pass `--mock` or set source to `mock` in YAML to run with synthetic data — essential for development without a live market connection.
- **Event-driven updates**: Analysis engines do not poll; they subscribe to `MarketBus` snapshots.
