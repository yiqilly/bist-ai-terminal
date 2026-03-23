# ============================================================
# data/models.py — Veri Modelleri v4
# ============================================================
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any


@dataclass
class MarketTick:
    symbol: str; price: float; bid: float; ask: float; volume: float
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class BarData:
    symbol: str; open: float; high: float; low: float; close: float; volume: float
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class ChartPoint:
    index: int; open: float; high: float; low: float; close: float
    volume: float; ema9: float; ema21: float
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class SignalCandidate:
    symbol: str; price: float; volume: float
    rsi: float; ema9: float; ema21: float; atr: float; momentum: float
    trend: bool; breakout: bool; volume_confirm: bool; score: int
    prev_price: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class RiskProfile:
    entry: float; stop: float; target: float
    risk_pct: float; reward_pct: float; rr_ratio: float; quality: str

@dataclass
class PositionSize:
    symbol: str; entry: float; stop: float
    suggested_lots: int; risk_per_share: float
    total_risk_tl: float; total_cost_tl: float
    portfolio_risk_pct: float
    sizing_note: str = ""

@dataclass
class SmartMoneyAnalysis:
    symbol: str; flow_score: float
    volume_surge_ratio: float; bar_range_expansion: float
    close_quality: float; breakout_follow: float; atr_norm_move: float
    label: str = ""

@dataclass
class LiquidityAnalysis:
    symbol: str; liquidity_score: float; volume_level: str
    spread_quality: float; execution_quality: str; lot_feasibility: int

@dataclass
class ConfidenceScore:
    symbol: str; confidence: float
    tech_contrib: float; news_contrib: float; regime_contrib: float
    breakout_contrib: float; volume_contrib: float
    liquidity_contrib: float; flow_contrib: float

@dataclass
class OpportunityCandidate:
    symbol: str; opp_score: float; quality_label: str
    reason: str; action: str
    trend: bool; breakout: bool; has_news_support: bool
    combined_score: float; ai_score: float; confidence: float
    core_edge_score: float = 0.0        # v4 eklenti
    core_setup_type: str = "None"       # v4 eklenti
    core_compatible: bool = False       # v4 eklenti

@dataclass
class AlertEvent:
    event_type: str; symbol: str; message: str; severity: str
    timestamp: datetime = field(default_factory=datetime.now)
    triggered: bool = False

@dataclass
class WatchlistItem:
    symbol: str
    added_at: datetime = field(default_factory=datetime.now)
    note: str = ""

@dataclass
class BrokerRecommendation:
    symbol: str; broker: str; recommendation: str
    target_price: float; report_date: datetime
    analyst: str = ""; note: str = ""

@dataclass
class BrokerConsensus:
    symbol: str; total_recs: int
    buy_count: int; hold_count: int; sell_count: int
    avg_target: float; current_price: float; potential_pct: float
    consensus: str
    latest_report: datetime = field(default_factory=datetime.now)

@dataclass
class RegimeResult:
    regime: str; label: str; strength: float
    advancing_pct: float; avg_momentum: float; avg_score: float
    volatility: float; description: str = ""

@dataclass
class MarketSnapshot:
    ticks: dict[str, MarketTick] = field(default_factory=dict)
    bars:  dict[str, BarData]    = field(default_factory=dict)
    timestamp: datetime          = field(default_factory=datetime.now)
    advancing: int = 0; declining: int = 0; unchanged: int = 0

    @property
    def market_strength(self) -> float:
        total = self.advancing + self.declining + self.unchanged
        return (self.advancing / total * 100) if total else 50.0

@dataclass
class RankedSignal:
    candidate: SignalCandidate; risk: RiskProfile
    rank: int = 0
    ai_score: float = 0.0; news_score: float = 0.0
    combined_score: float = 0.0; quality_label: str = "Watchlist"
    confidence: float = 0.0
    flow_score: float = 0.0; liquidity_score: float = 0.0
    position_size: Optional[PositionSize]        = None
    smart_money:   Optional[SmartMoneyAnalysis]  = None
    liquidity:     Optional[LiquidityAnalysis]   = None
    alerts:        list[str] = field(default_factory=list)
    # v4 — Core Strateji Alanları
    core_edge_score:  float = 0.0
    core_setup_type:  str   = "None"
    core_compatible:  bool  = False   # core setup aktif ve edge >= 4
    core_setup:       Any   = None    # CoreSetupFeatures (circular import önlemi)
    core_edge:        Any   = None    # CoreEdgeScore

@dataclass
class PortfolioPosition:
    symbol: str; quantity: float; avg_cost: float; current_price: float = 0.0
    @property
    def pnl(self) -> float: return (self.current_price - self.avg_cost) * self.quantity
    @property
    def pnl_pct(self) -> float:
        return ((self.current_price / self.avg_cost) - 1) * 100 if self.avg_cost else 0.0

@dataclass
class NewsItem:
    symbol: str; headline: str; source: str; sentiment: float
    timestamp: datetime = field(default_factory=datetime.now); url: str = ""
    @property
    def sentiment_label(self) -> str:
        return "POZİTİF" if self.sentiment > 0.3 else ("NEGATİF" if self.sentiment < -0.3 else "NÖTR")
    @property
    def age_minutes(self) -> float:
        return (datetime.now() - self.timestamp).total_seconds() / 60

@dataclass
class UnifiedSignalScore:
    """Şeffaf skor dökümü — tüm bileşenler ayrı görünür."""
    symbol: str
    technical: float = 0.0; ai: float = 0.0
    news: float = 0.0;      flow: float = 0.0
    liquidity: float = 0.0; core_edge: float = 0.0
    combined: float = 0.0;  confidence: float = 0.0
    quality_label: str = "Watchlist"
    setup_type: str = "None"; regime_mode: str = "—"

@dataclass
class HistoricalSetupProfile:
    setup_type: str; regime_mode: str
    win_rate: float; avg_pnl_pct: float
    total_return_pct: float; max_dd_pct: float
    profit_factor: float; trades: int; edge_label: str

@dataclass
class SymbolDetailViewModel:
    symbol: str; price: float; change_pct: float; volume: float
    score: int; rsi: float; ema9: float; ema21: float; atr: float
    trend: bool; breakout: bool; volume_confirm: bool
    entry: float; stop: float; target: float
    risk_pct: float; rr_ratio: float; quality: str; rank: int
    last_signal_time: str; technical_summary: str; regime_effect: str
    ai_score: float; news_score: float; combined_score: float
    quality_label: str; confidence: float
    flow_score: float = 0.0; liquidity_score: float = 0.0
    # v4
    core_edge_score: float = 0.0
    core_setup_type: str   = "None"
    core_win_rate:   float = 0.0
    core_expectancy: float = 0.0
    core_note:       str   = ""
    morning_momentum_pct: float = 0.0
    core_breakout:   bool  = False
    core_pullback:   bool  = False
    core_rebreak:    bool  = False
    core_regime_label: str = "—"
    core_edge_label: str   = "—"
    position_size:   Optional[PositionSize]       = None
    smart_money:     Optional[SmartMoneyAnalysis] = None
    liquidity:       Optional[LiquidityAnalysis]  = None
    alerts:          list[str] = field(default_factory=list)
    chart_data:      list[ChartPoint] = field(default_factory=list)
    broker_consensus: Optional[BrokerConsensus]   = None
    # v5: Sektör alanları
    sector_name:         str   = "—"
    sector_strength:     float = 0.0
    sector_avg_change:   float = 0.0
    sector_vol_activity: float = 0.0
    sector_trend:        str   = "—"
    sector_trend_color:  str   = "#94a3b8"
