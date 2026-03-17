# ============================================================
# config.py — Trading Cockpit v6
# ============================================================

APP_VERSION = "6.0.0"
APP_TITLE   = "BIST Trading Cockpit"
DATA_SOURCE = "borsapy"   # borsapy | mock
UPDATE_INTERVAL_SEC = 2

# ── Evren Konfigürasyonu (BIST12) ────────────────────────────
# Varsayılan: BIST30. İleride BIST50/100'e genişletilebilir.
UNIVERSE = "BIST100"   # BIST30 | BIST50 | BIST100

# BIST100'e geçince devreye girecek ek filtreler
UNIVERSE_FILTERS = {
    "BIST30": {
        "min_liquidity_score": 0,
        "min_daily_volume":    500_000,
        "min_price":           0.0,
        "max_spread_pct":      2.0,
        "rs_required":         False,    # BIST30'da zorunlu değil
    },
    "BIST50": {
        "min_liquidity_score": 4,
        "min_daily_volume":    1_000_000,
        "min_price":           1.0,
        "max_spread_pct":      1.5,
        "rs_required":         True,
    },
    "BIST100": {
        "min_liquidity_score": 5,
        "min_daily_volume":    2_000_000,
        "min_price":           2.0,
        "max_spread_pct":      1.0,
        "rs_required":         True,
        "sector_filter":       True,
    },
}

# ── Sinyal Filtresi ──────────────────────────────────────────
SIGNAL_FILTER = {
    "min_score":              4,
    "rsi_min":                55,
    "rsi_max":                72,
    "require_trend":          True,
    "require_breakout":       True,
    "require_volume_confirm": True,
}

# ── Trade Signal Kriterleri ──────────────────────────────────
# TradeSignalEngine'in BuyCriteria'sı buradan beslenir
TRADE_CRITERIA = {
    "rsi_min":           55.0,
    "rsi_max":           70.0,
    "sector_strength":   55.0,
    "market_strength":   50.0,
    "flow_score":        5.0,
    "rr_ratio":          1.8,
    "confirm_secs":      15.0,
    "min_hold_secs":     30.0,
    "combined_score":    5.5,
}

# ── Risk ─────────────────────────────────────────────────────
RISK = {
    "atr_stop_multiplier":   2.00,   # Backtest uyumlu: 2.00×günlük ATR
    "atr_target_multiplier": 5.00,   # Backtest uyumlu: 5.00×günlük ATR (Core)
    "default_risk_pct":      1.5,    # Backtest uyumlu %1.5
}

POSITION_SIZING = {
    "total_capital":          50_000.0,    # 50k TL TEST SERMAYESİ
    "risk_per_trade_pct":     1.5,         # %1.5 risk
    "max_open_positions":     5,           # 5 pozisyon
    "max_drawdown_pct":       15.0,
    "max_position_pct":       20.0,        # 50k / 5 = 10k per pos
    "max_sector_positions":   2,
    "min_rr":                 1.8,
    "commission_rate":        0.0015,
    "slippage_rate":          0.0005,
}

PORTFOLIO = {
    "initial_cash": 50_000.0,
}

# ── AI Ağırlıkları ───────────────────────────────────────────
AI_WEIGHTS = {
    "breakout_strength": 0.20,
    "volume_surge":      0.15,
    "rsi_zone":          0.15,
    "ema_structure":     0.10,
    "momentum":          0.10,
    "regime_fit":        0.10,
    "news_sentiment":    0.10,
    "relative_strength": 0.10,
}

MOMENTUM_TOP_N     = 10
SIGNAL_HISTORY_MAX = 200
LOG_LEVEL          = "INFO"
