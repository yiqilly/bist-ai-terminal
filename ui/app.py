# ============================================================
# ui/app.py — BIST Trading Cockpit v6
# Scanner → Trade Decision Cockpit
#
# Mimari:
#   Realtime Data → Market Context → Sector Strength
#   → Relative Strength → Opportunity Engine
#   → Trade Signal Engine → Position Manager → Risk Dashboard
# ============================================================
import tkinter as tk
from tkinter import ttk
import datetime

from config import APP_TITLE, APP_VERSION, UPDATE_INTERVAL_SEC
from ui.theme import *

# ── Panel Import'ları ─────────────────────────────────────────
from ui.panels.heatmap_panel             import HeatmapPanel
from ui.panels.market_context_panel      import MarketContextPanel
from ui.panels.sector_panel              import SectorPanel
from ui.panels.rs_panel                  import RSPanel
from ui.panels.opportunity_panel_v2      import OpportunityPanelV2
from ui.panels.trade_signals_panel       import (
    BuySignalsPanel, SetupPanel, WatchlistSignalPanel
)
from ui.panels.position_panel            import PositionPanel
from ui.panels.risk_dashboard_panel      import RiskDashboardPanel
from ui.panels.notification_center       import NotificationPanel
from ui.panels.buy_signal_popup          import BuySignalPopup, SellSignalPopup
from ui.panels.selected_symbol_panel     import SelectedSymbolPanel
# from ui.panels.chart_panel               import ChartPanel  # Kaldırıldı (Performance)
from ui.panels.news_detail_panel         import NewsDetailPanel
from ui.panels.broker_recommendations_panel import BrokerRecommendationsPanel
from ui.panels.market_status_panel       import MarketStatusBar
from ui.panels.news_panel                import NewsPanel
from ui.panels.alert_panel               import AlertPanel
from ui.panels.signal_history_panel      import SignalHistoryPanel
from alerts.telegram_notifier            import TelegramNotifier

# ── Engine Import'ları ────────────────────────────────────────
from data.market_bus              import MarketBus
from data.models                  import (RankedSignal, SignalCandidate,
                                           SymbolDetailViewModel)
from data.sector_map              import get_sector
from strategy.scanner             import MarketScanner
from strategy.unified_regime     import UnifiedRegimeEngine
from strategy.relative_strength_engine import RelativeStrengthEngine
from strategy.summary_builder    import TechnicalSummaryBuilder
from strategy.smart_money        import SmartMoneyAnalyzer
from strategy.liquidity          import LiquidityAnalyzer
from strategy.sector_strength    import SectorStrengthEngine
from strategy.liquidity_sweep    import LiquiditySweepDetector
from strategy.core.setup_detector  import SetupDetector
from strategy.core.edge_score      import EdgeScoreCalculator
from strategy.core.performance_summary import get_historical_stats
from signals.ranking             import SignalRanker
from signals.history             import SignalHistory
from signals.opportunity_engine  import OpportunityEngine
from signals.trade_signal_engine import TradeSignalEngine, BuyCriteria
from strategy.strategy_router    import StrategyRouter, RouterSignal
from strategy.router_adapter     import (
    filter_router_buys, filter_router_setups, filter_router_watchlist,
)
from strategy.session_manager    import SessionManager, SessionPhase
from strategy.position_sizer     import PositionSizer
from signals.ai_ranking          import AIRankingEngine
from signals.notification_store  import NotificationCenter
from risk.risk_engine            import RiskEngine
from risk.risk_dashboard         import RiskDashboard
from portfolio.position_manager  import PositionManager
from portfolio.portfolio_engine  import PortfolioEngine
from portfolio.trade_journal     import TradeJournal
from news.news_engine            import NewsEngine
from news.sentiment              import SentimentScorer
from recommendations.broker_engine import BrokerEngine
from recommendations.consensus   import ConsensusEngine
from alerts.alert_engine         import AlertEngine
from watchlist.watchlist_engine  import WatchlistEngine
from charts.history_provider     import HistoryProvider
from config                      import TRADE_CRITERIA


class TradingCockpit(tk.Tk):
    """
    BIST Trading Cockpit — v6
    Scanner değil: trade lifecycle yöneten karar merkezi.
    """

    def __init__(
        self,
        market_bus,
        scanner,
        ranker,
        signal_history,
        portfolio,
        news_engine,
        broker_engine,
        regime_engine,
        summary_builder,
        alert_engine,
        watchlist,
        history_provider,
        consensus_engine,
        sector_engine=None,
        snapshot_cache=None,
        source_label="mock",
    ):
        super().__init__()
        # Koyu TTK teması — pencere açılır açılmaz uygula
        from ui.theme import apply_global_ttk_theme
        apply_global_ttk_theme()
        # ── Temel engine'ler ─────────────────────────────────
        self._bus        = market_bus
        self._scanner    = scanner
        self._ranker     = ranker
        self._history    = signal_history
        self._portfolio  = portfolio
        self._news       = news_engine
        self._broker     = broker_engine
        self._regime_eng = regime_engine     # ← eksikti
        self._summary    = summary_builder   # ← eksikti
        self._alert_eng  = alert_engine
        self._watchlist  = watchlist
        self._hist_prov  = history_provider
        self._consensus  = consensus_engine
        self._sent       = SentimentScorer()
        self._smart      = SmartMoneyAnalyzer()
        self._liq_eng    = LiquidityAnalyzer()
        self._risk_eng   = RiskEngine()
        self._setup_det  = SetupDetector()
        self._edge_calc  = EdgeScoreCalculator()

        # ── v6 engine'ler ─────────────────────────────────────
        self._sector_eng  = sector_engine or SectorStrengthEngine()
        self._regime_eng  = UnifiedRegimeEngine()        # Unified Regime (v2)
        self._rs_eng      = RelativeStrengthEngine()     # FAZ 4
        self._opp_eng     = OpportunityEngine()          # FAZ 5
        self._pos_mgr     = PositionManager()            # FAZ 8
        self._journal     = TradeJournal()               # FAZ 8
        self._risk_dash   = RiskDashboard()              # FAZ 9
        self._sweep_det   = LiquiditySweepDetector()

        # Trade Signal Engine — config'den kriterler
        criteria = BuyCriteria(**{
            k: v for k, v in TRADE_CRITERIA.items()
            if k in BuyCriteria.__dataclass_fields__
        })
        self._trade_eng   = TradeSignalEngine(criteria)
        # self._trade_eng.on_buy_signal(self._on_buy_generated)  # Silindi: Yeni v6 akışı kullanılıyor
        # self._trade_eng.on_sell_signal(self._on_sell_generated) # Silindi

        # ── Strategy Router (Regime-Switching) ───────────────
        self._strategy_router = StrategyRouter()

        # ── Session Manager (pencere takibi) ──────────────────
        self._session_mgr = SessionManager()
        self._session_mgr.on_callbacks(
            on_reset        = self._on_day_reset,
            on_signal_open  = self._on_signal_window_open,
            on_signal_close = self._on_signal_window_close,
            on_eod          = self._on_eod_warning,
        )

        # ── Position Sizer (risk bazlı lot) ───────────────────
        from config import POSITION_SIZING
        self._sizer = PositionSizer(
            capital = POSITION_SIZING.get('total_capital', 100_000.0),
            config  = POSITION_SIZING,
        )

        self._nc          = NotificationCenter.get()
        self._cache       = snapshot_cache
        self._source_label = source_label

        # ── Telegram Notifier ─────────────────────────────────
        self._telegram = TelegramNotifier(
            token="8757469495:AAHiKLb6nZTeJBfaajFqvFybT7hNFjaY44k",
            chat_id="8785152206"
        )
        self._telegram.bind(self._nc)
        self._telegram.send_message("🚀 <b>BIST Terminal Canlı!</b>\nSinyaller bu kanala akmaya başlayacaktır.")

        # ── State ────────────────────────────────────────────
        self._selected_symbol: str | None = None
        self._selected_signal: RankedSignal | None = None
        self._all_candidates: list[SignalCandidate] = []
        self._market_ctx  = None
        self._sectors:    dict = {}
        self._rs_results: dict = {}
        self._tick_count  = 0
        self._sent_notifications: set[str] = set()       # Gönderilen sinyallerin ID'leri
        self._pending_buy_popups:  list = []
        self._pending_sell_popups: list = []
        
        self._heatmap_win: Optional[tk.Toplevel] = None
        self._heatmap_panel: Optional[HeatmapPanel] = None

        self._configure_window()
        self._build_layout()
        self._schedule_update()

    # ── Pencere ───────────────────────────────────────────────

    def _configure_window(self):
        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.configure(bg=BG_DARK)
        self.geometry("1600x980")
        self.minsize(1280, 800)

    # ── Layout ────────────────────────────────────────────────

    def _build_layout(self):
        # ── Top bar ──────────────────────────────────────────
        tb = tk.Frame(self, bg=BG_HEADER, pady=5); tb.pack(fill="x")
        tk.Label(tb, text="◉  BIST TRADING COCKPIT",
                 font=("Consolas", 13, "bold"),
                 bg=BG_HEADER, fg=COLOR_ACCENT).pack(side="left", padx=14)

        self._clock_lbl = tk.Label(tb, text="", font=FONT_MEDIUM,
                                    bg=BG_HEADER, fg=TEXT_SECONDARY)
        self._clock_lbl.pack(side="right", padx=14)

        self._regime_lbl = tk.Label(tb, text="", font=FONT_HEADER,
                                     bg=BG_HEADER, fg=COLOR_WARNING)
        self._regime_lbl.pack(side="right", padx=10)

        self._buy_cnt_lbl = tk.Label(tb, text="", font=FONT_HEADER,
                                      bg=BG_HEADER, fg=COLOR_POSITIVE)
        self._buy_cnt_lbl.pack(side="right", padx=10)

        self._status_bar = MarketStatusBar(tb, market_bus=self._bus)
        self._status_bar.pack(side="right", padx=6)
        
        tk.Button(tb, text="♨️ Heatmap", command=self._toggle_heatmap,
                  font=("Consolas", 9, "bold"), bg=BG_DARK, fg=COLOR_ACCENT,
                  relief="flat", padx=10, cursor="hand2").pack(side="right", padx=10)

        # ── Scrollable Ana Gövde ──────────────────────────────
        outer_container = tk.Frame(self, bg=BG_DARK)
        outer_container.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(outer_container, bg=BG_DARK, highlightthickness=0)
        self._canvas.pack(side="left", fill="both", expand=True)

        self._scrollbar = ttk.Scrollbar(outer_container, orient="vertical", command=self._canvas.yview)
        self._scrollbar.pack(side="right", fill="y")

        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        
        # İç container
        main = tk.Frame(self._canvas, bg=BG_DARK)
        self._canvas_window = self._canvas.create_window((0, 0), window=main, anchor="nw")

        def _on_frame_configure(event):
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        
        main.bind("<Configure>", _on_frame_configure)

        def _on_canvas_configure(event):
            # Canvas genişleyince frame'i de genişlet
            self._canvas.itemconfig(self._canvas_window, width=event.width)

        self._canvas.bind("<Configure>", _on_canvas_configure)

        # Mouse wheel desteği
        def _on_mousewheel(event):
            self._canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.bind_all("<MouseWheel>", _on_mousewheel)

        # ── Ana gövde (3 kolon) ───────────────────────────────
        # Not: Artık 'main' değişkeni canvas içindeki frame.
        main.columnconfigure(0, weight=1) # Heatmap & Notebook kolonu

        # SOL — heatmap + notebook
        left = tk.Frame(main, bg=BG_DARK)
        left.pack(side="left", fill="both", expand=True, padx=(0, 3))

        top_row = tk.Frame(left, bg=BG_DARK)
        top_row.pack(fill="x", pady=(0, 3))

        # self._heatmap = HeatmapPanel(top_row, on_symbol_click=self._on_symbol_click) # Kaldırıldı
        # self._heatmap.pack(side="left", fill="both", expand=True, padx=(0, 3))

        # Sağ üst — Market Context + Sector
        right_top = tk.Frame(top_row, bg=BG_DARK, width=210)
        right_top.pack(side="right", fill="y")
        right_top.pack_propagate(False)

        self._ctx_panel = MarketContextPanel(right_top)
        self._ctx_panel.pack(fill="both", expand=True)

        # Orta notebook — 5 ana sekme
        nb_f = tk.Frame(left, bg=BG_DARK)
        nb_f.pack(fill="both", expand=True)
        nb = self._make_nb(nb_f)
        nb.pack(fill="both", expand=True)

        # ── TAB 1: BUY SIGNALS (ana karar tablosu) ───────────
        self._trade_panel = BuySignalsPanel(
            nb,
            on_buy    = self._on_trade_buy_click,
            on_select = self._on_symbol_click,
        )
        nb.add(self._trade_panel, text="  🚀 BUY SİNYALİ  ")

        # ── TAB 2: SETUP (teyit bekleyen) ────────────────────
        self._setup_nb = SetupPanel(nb, on_select=self._on_symbol_click)
        nb.add(self._setup_nb, text="  ⏳ SETUP  ")

        # ── TAB 3: WATCHLIST (izleme) ─────────────────────────
        self._wl_signal_panel = WatchlistSignalPanel(
            nb, on_select=self._on_symbol_click
        )
        nb.add(self._wl_signal_panel, text="  👁 WATCHLIST  ")

        # ── TAB 4: POSITIONS (açık pozisyonlar) ───────────────
        self._pos_panel = PositionPanel(
            nb,
            signal_engine = self._trade_eng,
            on_sell       = self._on_position_sell,
        )
        nb.add(self._pos_panel, text="  💼 POZİSYONLAR  ")

        # TAB 5: NOTIFICATIONS (Silindi)

        # ── Alt notebook (analitik) ───────────────────────────
        nb2_f = tk.Frame(left, bg=BG_DARK, height=0)
        # Analitik sekmeler — varsayılan gizli, tab bar ile açılabilir
        nb2 = self._make_nb(nb_f)
        # İkinci notebook yerine ana notebook'a devam ekle

        # ── Ek sekmeler (analiz araçları) ─────────────────────
        self._opp_panel = OpportunityPanelV2(
            nb,
            on_select = self._on_symbol_click,
            on_buy    = self._on_opp_buy_click,
        )
        nb.add(self._opp_panel, text="  🎯 Fırsatlar  ")

        self._rs_panel = RSPanel(nb, on_select=self._on_symbol_click)
        nb.add(self._rs_panel, text="  ↗ RS  ")

        self._sector_panel = SectorPanel(nb)
        nb.add(self._sector_panel, text="  📊 Sektörler  ")

        self._risk_panel = RiskDashboardPanel(nb)
        nb.add(self._risk_panel, text="  🔴 Risk  ")

        self._news_panel = NewsPanel(nb)
        nb.add(self._news_panel, text="  📰 Haberler  ")

        self._history_panel = SignalHistoryPanel(nb)
        nb.add(self._history_panel, text="  📋 Geçmiş  ")

        self._alert_panel = AlertPanel(nb)
        nb.add(self._alert_panel, text="  ⚡ Alertler  ")

        # SAĞ — sembol detay
        right = tk.Frame(main, bg=BG_DARK, width=360)
        right.pack(side="right", fill="y", padx=(3, 0))
        right.pack_propagate(False)

        rnb = self._make_nb(right)
        rnb.pack(fill="both", expand=True)

        self._sym_panel   = SelectedSymbolPanel(rnb)
        rnb.add(self._sym_panel, text=" Detay ")

        # self._chart_panel = ChartPanel(rnb)  # Kaldırıldı (Performance)
        # rnb.add(self._chart_panel, text=" Grafik ")

        self._news_detail = NewsDetailPanel(rnb)
        rnb.add(self._news_detail, text=" Haberler ")

        self._broker_panel = BrokerRecommendationsPanel(rnb, on_symbol_click=self._on_symbol_click)
        rnb.add(self._broker_panel, text=" Kurum (Favori) ")

        # Arka planda broker verilerini periyodik tara
        self._start_broker_background_fetch()

    def _make_nb(self, parent):
        style = ttk.Style()
        style.configure("T6.TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("T6.TNotebook.Tab",
                         background=BG_CARD, foreground=TEXT_SECONDARY,
                         font=FONT_HEADER, padding=[7, 3])
        style.map("T6.TNotebook.Tab",
                  background=[("selected", PANEL_TITLE_BG)],
                  foreground=[("selected", COLOR_ACCENT)])
        return ttk.Notebook(parent, style="T6.TNotebook")

    # ── Güncelleme Döngüsü ────────────────────────────────────

    def _schedule_update(self):
        self._update()
        self.after(UPDATE_INTERVAL_SEC * 1000, self._schedule_update)

    def _update(self):
        self._tick_count += 1
        snap = self._bus.get_snapshot()
        if not snap.ticks:
            return

        self._clock_lbl.config(
            text=datetime.datetime.now().strftime("%H:%M:%S  %d.%m.%Y")
        )

        # ── Session Manager tick ──────────────────────────────
        session_phase = self._session_mgr.tick()
        in_signal_window = self._session_mgr.in_signal_window

        # ── 1. Scanner — tüm candidates (aday üretici) ─────────
        self._all_candidates = self._scanner.scan(snap)
        best_raw = self._scanner.get_best_signals(snap)

        # ── 2. Unified Regime (tek rejim motoru — v2) ─────────
        self._unified_regime = self._regime_eng.compute(snap, self._all_candidates)

        # Eski API uyumluluğu (scoring, summary, alerts için)
        self._current_regime = self._unified_regime.to_regime_result()
        self._core_regime_result = self._unified_regime.to_core_regime()
        # MarketContext uyumluluğu (panel ve opp engine için)
        self._market_ctx = self._unified_regime

        # ── 3. Sector Strength ─────────────────────────────────
        self._sectors = self._sector_eng.compute(self._all_candidates, snap)

        # ── 4. Relative Strength ──────────────────────────────
        self._rs_results = self._rs_eng.compute(self._all_candidates, snap)

        # ── 5. Ranking (analitik amaçlı — UI detay paneli için) ──
        ranked = self._ranker.rank(best_raw, self._current_regime, self._all_candidates)

        # ── 6. Opportunity Engine ─────────────────────────────
        opps = self._opp_eng.scan(
            ranked, snap, self._sectors, self._rs_results, self._market_ctx
        )

        # ── 7. UNIFIED PIPELINE — StrategyRouter (tek sinyal kaynağı) ──
        regime_str = self._unified_regime.regime
        if self._tick_count % 96 == 1:
            self._strategy_router.reset_day()

        # Router sinyal penceresinde çalışır + seans içi takip
        if in_signal_window or self._session_mgr.in_trading_hours:
            for cand in self._all_candidates:
                sym  = cand.symbol
                tick = snap.ticks.get(sym)
                if not tick: continue

                sec_name = get_sector(sym)
                sec_ss = self._sectors.get(sec_name, None)
                rs_obj = self._rs_results.get(sym)
                from strategy.opening_strategy import Bar as RBar
                router_bar = RBar(
                    timestamp=datetime.datetime.now(),
                    open=tick.price, high=tick.price,
                    low=tick.price,  close=tick.price,
                    volume=tick.volume,
                )
                router_ctx = dict(
                    sector_strength = sec_ss.strength if sec_ss else cand.score*10,
                    rs_vs_index     = rs_obj.rs_vs_index if rs_obj else 0.0,
                    ema9_daily      = cand.ema9,
                    ema21_daily     = cand.ema21,
                    rsi_daily       = cand.rsi,
                    daily_atr       = cand.atr * 12,
                    vol_ma          = cand.volume * 0.7,
                    intraday_vol    = tick.volume,
                    intraday_bars   = self._cache.get_bars(sym, '5m', n=50)
                                      if self._cache else [],
                    vwap_value      = tick.price * 0.995,
                    rsi_intraday    = cand.rsi,
                    intraday_atr    = cand.atr,
                )
                self._strategy_router.on_bar(
                    sym, router_bar, regime_str, router_ctx)

        # StrategyRouter → TradeSignal dönüşümü (tek pipeline)
        all_router_signals = self._strategy_router.get_all_signals()
        buy_signals  = filter_router_buys(all_router_signals, self._sizer)
        setups       = filter_router_setups(all_router_signals, self._sizer)
        watchlist    = filter_router_watchlist(all_router_signals)

        # TradeSignalEngine — callback mekanizması için hâlâ çalışır
        # ama artık sinyal kaynağı değil, sadece pozisyon durumu takibi
        self._trade_eng.update(ranked, snap, self._sectors, self._sector_eng)

        # ── 8. Position Manager fiyat güncelle ───────────────
        prices = {s: t.price for s, t in snap.ticks.items()}
        triggered = self._pos_mgr.update_prices(prices)
        for sym in triggered:
            pos = self._pos_mgr.get(sym)
            if pos:
                self._nc.add("SELL", sym, f"{sym} stop tetiklendi — ₺{pos.exit_price:.2f}")

        # ── 9. Risk Dashboard ─────────────────────────────────
        risk_metrics = self._risk_dash.compute(
            self._pos_mgr.get_all(), self._sectors
        )

        # ── 10. Periyodik bakım ───────────────────────────────
        if self._tick_count % 30 == 1:
            self._setup_det.invalidate_cache()

        # Sinyal geçmişi (analitik amaçlı)
        for s in ranked[:3]:
            self._history.add(s)
        signal_symbols = {s.candidate.symbol for s in ranked}

        # Alertler
        new_alerts = self._alert_eng.process(ranked, self._current_regime)
        all_alerts = self._alert_eng.get_recent(15)

        # ── Top bar güncelle ──────────────────────────────────
        regime_color = self._unified_regime.color
        regime_label = self._unified_regime.label
        active_strat = self._strategy_router.get_active_strategy_type(regime_str)
        strat_icons = {
            'BULL_BREAKOUT': '📈', 'RANGE_SECTOR_ROTATION': '🔄',
            'VOLATILE_BREAKOUT': '⚡', 'EDGE_MULTI': '🦈',
        }
        if active_strat:
            regime_label = f"{regime_label} {strat_icons.get(active_strat, '')}"
        elif not self._unified_regime.trade_allowed:
            regime_label = f"{regime_label} ⏸"

        self._regime_lbl.config(text=regime_label, fg=regime_color)
        n_buy = len(buy_signals)
        if n_buy > 0:
            self._buy_cnt_lbl.config(text=f"🚀 {n_buy} AL", fg=COLOR_POSITIVE)
            # ── Yeni Sinyal Bildirimleri (v6 Akışı) ───────────
            for sig in buy_signals:
                notif_id = f"{sig.symbol}_{sig.buy_issued_at}"
                if notif_id not in self._sent_notifications:
                    self._sent_notifications.add(notif_id)
                    msg = f"🚀 <b>YENİ AL SİNYALİ: {sig.symbol}</b>\n" \
                          f"Fiyat: ₺{sig.entry:.2f} | R/R: {sig.rr_ratio:.1f} | Kalite: {sig.quality_label}\n" \
                          f"Neden: {sig.reason}"
                    self._telegram.send_message(msg)
                    self._nc.add("BUY", sig.symbol, f"AL: {sig.symbol} | R/R={sig.rr_ratio:.1f}")
                    # Popup ekle
                    self._pending_buy_popups.append(sig)
        else:
            self._buy_cnt_lbl.config(text="", fg=COLOR_POSITIVE)

        # ── UI Panel Güncellemeleri ───────────────────────────
        self._status_bar.refresh(snap)
        if self._heatmap_panel and self._heatmap_win and self._heatmap_win.winfo_exists():
            self._heatmap_panel.update(snap, self._all_candidates)
        self._ctx_panel.update(self._unified_regime)          # Unified Regime
        self._trade_panel.update(buy_signals)                 # BUY SİNYALLERİ
        self._setup_nb.update(setups)                         # SETUP
        self._wl_signal_panel.update(                         # WATCHLIST
            watchlist,
            rs_results=self._rs_results
        )
        self._opp_panel.update(opps)                          # Fırsatlar
        self._rs_panel.update(self._rs_results)               # RS
        self._sector_panel.update(self._sectors)              # Sektörler
        self._pos_panel.update()                              # Pozisyonlar
        self._risk_panel.update(risk_metrics)                 # Risk
        self._news_panel.update(self._news.get_news(), signal_symbols,
                                source_label=getattr(self._news, 'source_label', ''))
        self._history_panel.update(self._history.get_all())
        self._alert_panel.update(all_alerts)
        # ── 11. Broker Favoriler Güncelle (Her 100 tickte bir) ──
        if self._tick_count % 100 == 1:
            from data.symbols import ACTIVE_UNIVERSE
            prices = {s: t.price for s, t in snap.ticks.items()}
            picks = self._consensus.top_picks(ACTIVE_UNIVERSE, self._broker, prices, top_n=20)
            self._broker_panel.update_top_picks(picks)

        # Bekleyen popup'ları göster
        self._flush_popups()

    # ── Sembol Panel Yenileme ────────────────────────────────

    def _refresh_symbol_panels(self):
        symbol = self._selected_symbol
        if not symbol:
            self._sym_panel.update(None)
            # self._chart_panel.update("—", [], None)  # Kaldırıldı
            self._news_detail.update(None, [])
            self._broker_panel.update(None, [], None, lambda r: 0.0)
            return

        cand = next((c for c in self._all_candidates if c.symbol == symbol), None)
        sig  = (self._selected_signal
                if self._selected_signal and
                self._selected_signal.candidate.symbol == symbol
                else None)
        risk = sig.risk if sig else (self._risk_eng.calculate(cand) if cand else None)
        vm   = self._build_vm(symbol, cand, sig, risk)

        base_price = cand.price if cand else 100.0
        if self._cache:
            raw_bars = self._cache.get_bars(symbol, "1m", n=60)
            chart_pts = (self._hist_prov.from_bar_cache(raw_bars)
                         if len(raw_bars) >= 5
                         else self._hist_prov.get_history(symbol, bars=60,
                                                           base_price=base_price))
        else:
            chart_pts = self._hist_prov.get_history(symbol, bars=60, base_price=base_price)

        recs      = self._broker.get_for_symbol(symbol)
        consensus = self._consensus.compute(symbol, recs, cand.price if cand else 0.0)

        self._sym_panel.update(vm)
        # self._chart_panel.update(symbol, chart_pts, risk)  # Kaldırıldı
        # Sembol haberleri — Ticker.news dene
        symbol_news = self._news.get_recent(symbol, 5)
        self._news_detail.update(symbol, symbol_news)
        # self._broker_panel.update(...)  # Kaldırıldı (Favori listesi olarak değişti)

    def _build_vm(self, symbol, cand, sig, risk) -> SymbolDetailViewModel | None:
        if not cand:
            return None

        regime    = self._current_regime
        news_sent = self._sent.score_for_symbol(symbol, self._news.get_news())
        sm  = (sig.smart_money if sig and sig.smart_money
               else self._smart.analyze(cand))
        liq = (sig.liquidity if sig and sig.liquidity
               else self._liq_eng.analyze(cand))

        ai_res  = ({"ai_score": sig.ai_score, "quality_label": sig.quality_label}
                   if sig else
                   AIRankingEngine().score(cand, regime, news_sent, self._all_candidates))
        conf    = sig.confidence     if sig else 50.0
        comb    = sig.combined_score if sig else round(cand.score / 6 * 7, 2)
        alerts  = sig.alerts         if sig else []
        pos     = (sig.position_size if sig else None)

        core_setup  = (sig.core_setup if sig and sig.core_setup
                       else self._setup_det.detect_from_candidate(cand))
        core_regime = self._core_regime_result if hasattr(self, '_core_regime_result') else (
                      self._unified_regime.to_core_regime())
        core_edge   = (sig.core_edge if sig and sig.core_edge
                       else self._edge_calc.calculate(core_setup, core_regime))

        hist_stats  = get_historical_stats(core_setup.setup_type, core_regime.mode)
        # change_pct: prev_price makul aralıkta mı kontrol et
        if cand.prev_price > 0 and cand.price > 0:
            ratio = cand.price / cand.prev_price
            if 0.5 <= ratio <= 2.0:   # günlük ±50% gerçekçi sınır
                change_pct = round((cand.price - cand.prev_price) / cand.prev_price * 100, 2)
            else:
                change_pct = 0.0   # şüpheli prev_price
        else:
            change_pct = 0.0
        tech_sum    = self._summary.build(cand, regime, sm, liq, news_sent,
                                          core_setup, core_edge)

        sec_name = get_sector(symbol)
        sec_ss   = self._sectors.get(sec_name)
        rs_res   = self._rs_results.get(symbol)

        return SymbolDetailViewModel(
            symbol=symbol, price=cand.price, change_pct=round(change_pct, 2),
            volume=cand.volume, score=cand.score,
            rsi=cand.rsi, ema9=cand.ema9, ema21=cand.ema21, atr=cand.atr,
            trend=cand.trend, breakout=cand.breakout,
            volume_confirm=cand.volume_confirm,
            entry  = risk.entry    if risk else cand.price,
            stop   = risk.stop     if risk else cand.price * 0.97,
            target = risk.target   if risk else cand.price * 1.05,
            risk_pct = risk.risk_pct   if risk else 0.0,
            rr_ratio = risk.rr_ratio   if risk else 0.0,
            quality  = risk.quality    if risk else "C",
            rank     = sig.rank if sig else 0,
            last_signal_time   = cand.timestamp.strftime("%H:%M:%S"),
            technical_summary  = tech_sum,
            regime_effect      = regime.label if regime else "—",
            ai_score     = ai_res.get("ai_score", 0.0)        if isinstance(ai_res, dict) else ai_res,
            news_score   = round(news_sent, 2),
            combined_score = comb,
            quality_label  = ai_res.get("quality_label", "Watchlist") if isinstance(ai_res, dict) else "Watchlist",
            confidence     = conf,
            flow_score     = sm.flow_score         if sm  else 0.0,
            liquidity_score= liq.liquidity_score   if liq else 0.0,
            core_edge_score   = core_edge.edge_score,
            core_setup_type   = core_setup.setup_type,
            core_win_rate     = hist_stats.win_rate     if hist_stats else 0.0,
            core_expectancy   = hist_stats.expectancy   if hist_stats else 0.0,
            core_note         = core_edge.note,
            morning_momentum_pct = core_setup.morning_momentum_pct,
            core_breakout     = core_setup.breakout_detected,
            core_pullback     = core_setup.pullback_detected,
            core_rebreak      = core_setup.rebreak_detected,
            core_regime_label = core_regime.label,
            core_edge_label   = core_edge.edge_label,
            position_size     = pos,
            smart_money=sm, liquidity=liq, alerts=alerts,
            sector_name        = sec_name,
            sector_strength    = sec_ss.strength        if sec_ss else 0.0,
            sector_avg_change  = sec_ss.avg_change_pct  if sec_ss else 0.0,
            sector_vol_activity= sec_ss.volume_activity if sec_ss else 0.0,
            sector_trend       = sec_ss.trend_label     if sec_ss else "—",
            sector_trend_color = sec_ss.trend_color     if sec_ss else "#94a3b8",
        )

    # ── Event Handler'lar ────────────────────────────────────

    def _on_symbol_click(self, symbol: str):
        self._selected_symbol = symbol
        self._selected_signal = None
        if self._heatmap_panel and self._heatmap_win and self._heatmap_win.winfo_exists():
            self._heatmap_panel.set_selected(symbol)
        self._refresh_symbol_panels()

    def _on_signal_select(self, signal: RankedSignal):
        self._selected_signal = signal
        self._selected_symbol = signal.candidate.symbol
        if self._heatmap_panel and self._heatmap_win and self._heatmap_win.winfo_exists():
            self._heatmap_panel.set_selected(self._selected_symbol)
        self._refresh_symbol_panels()

    # ── Trade Signal Callback'leri ────────────────────────────

    def _on_day_reset(self) -> None:
        """09:59'da gün başı reset — strategy router ve pending temizle."""
        try:
            self._strategy_router.reset_day()
            self._nc.add("SİSTEM", "—",
                         "🔄 Yeni seans — strateji motorları sıfırlandı")
        except Exception:
            pass

    def _on_signal_window_open(self) -> None:
        """10:10'da sinyal penceresi açıldı."""
        try:
            self._nc.add("SİSTEM", "—",
                         "🎯 Sinyal penceresi açıldı (10:10-10:30)")
        except Exception:
            pass

    def _on_signal_window_close(self) -> None:
        """10:30'da sinyal penceresi kapandı."""
        try:
            self._nc.add("SİSTEM", "—",
                         "⏹ Sinyal penceresi kapandı — pozisyon yönetimi devam ediyor")
        except Exception:
            pass

    def _on_eod_warning(self) -> None:
        """17:20'de EOD uyarısı."""
        try:
            open_syms = list(self._pos_mgr.get_all().keys()) if self._pos_mgr else []
            if open_syms:
                self._nc.add("UYARI", "—",
                             f"⚠ Gün sonu yaklaşıyor! "
                             f"Açık pozisyonlar: {', '.join(open_syms)}")
            else:
                self._nc.add("SİSTEM", "—", "⏰ Gün sonu — açık pozisyon yok")
        except Exception:
            pass

    def _on_buy_generated(self, sig) -> None:
        """BUY sinyali üretildi — thread-safe queue."""
        self._nc.add("BUY", sig.symbol,
                     f"AL: {sig.symbol} | {sig.quality_label} | R/R={sig.rr_ratio:.1f}",
                     detail=sig.reason)
        self._pending_buy_popups.append(sig)

    def _on_sell_generated(self, sig) -> None:
        """SELL sinyali üretildi."""
        self._nc.add("SELL", sig.symbol,
                     f"SAT: {sig.symbol} | PnL={sig.pnl_pct:+.2f}%",
                     detail=sig.reason)
        self._pending_sell_popups.append(sig)

    def _flush_popups(self) -> None:
        """UI thread'de popup'ları göster."""
        while self._pending_buy_popups:
            sig = self._pending_buy_popups.pop(0)
            try:
                BuySignalPopup(
                    self, signal=sig,
                    on_buy   = self._handle_buy_action,
                    on_watch = lambda sym: self._nc.add("INFO", sym, f"{sym} izlemeye alındı"),
                    on_close = lambda: None,
                )
            except Exception:
                pass

        while self._pending_sell_popups:
            sig = self._pending_sell_popups.pop(0)
            try:
                SellSignalPopup(
                    self, signal=sig,
                    on_sell  = self._handle_sell_action,
                    on_wait  = lambda sym: None,
                    on_close = lambda: None,
                )
            except Exception:
                pass

    def _handle_buy_action(self, symbol: str, entry_price: float, lots: int) -> None:
        """Kullanıcı 'Aldım' dedi."""
        self._trade_eng.mark_position_entered(symbol, entry_price, lots)
        # PositionManager'a da yaz
        sig = self._trade_eng.get_signal(symbol)
        if sig:
            self._pos_mgr.open_position(
                symbol=symbol,
                entry_price=entry_price,
                lots=lots,
                stop=sig.stop,
                target=sig.target,
            )
        self._nc.add("INFO", symbol,
                     f"Pozisyon: {symbol} {lots} lot @ ₺{entry_price:.2f}")

    def _handle_sell_action(self, symbol: str) -> None:
        """Kullanıcı 'Sattım' dedi."""
        pos = self._pos_mgr.get(symbol)
        if pos:
            price = pos.current_price or pos.entry_price
            self._pos_mgr.close_position(symbol, price, reason="manual")
            self._journal.record_from_position(pos)
        self._trade_eng.mark_position_closed(symbol)
        self._nc.add("INFO", symbol, f"Pozisyon kapatıldı: {symbol}")

    def _on_position_sell(self, symbol: str) -> None:
        """Position panel'den 'Sat' butonu."""
        self._handle_sell_action(symbol)

    def _on_trade_buy_click(self, sig) -> None:
        """Sinyal tablosunda çift tıklama."""
        try:
            BuySignalPopup(
                self, signal=sig,
                on_buy   = self._handle_buy_action,
                on_watch = lambda sym: self._nc.add("INFO", sym, f"{sym} izlemeye alındı"),
                on_close = lambda: None,
            )
        except Exception:
            pass

    def _on_opp_buy_click(self, opp) -> None:
        """Fırsat tablosunda çift tıklama — BUY popup'ı."""
        # Opportunity → sahte TradeSignal oluştur
        from signals.trade_signal_engine import TradeSignal, SignalState
        from data.models import RiskProfile
        fake_sig = TradeSignal(
            symbol        = opp.symbol,
            state         = SignalState.BUY_SIGNAL,
            entry         = opp.entry,
            stop          = opp.stop,
            target        = opp.target,
            rr_ratio      = opp.rr_ratio,
            confidence    = opp.confidence,
            quality_label = opp.quality_label,
            reason        = opp.reason,
            sector_name   = opp.sector_name,
            sector_strength = opp.sector_strength,
        )
        try:
            BuySignalPopup(
                self, signal=fake_sig,
                on_buy   = self._handle_buy_action,
                on_watch = lambda sym: self._nc.add("INFO", sym, f"{sym} izlemeye alındı"),
                on_close = lambda: None,
            )
        except Exception:
            pass


    # ── Broker Background Fetch ────────────────────────────
    def _start_broker_background_fetch(self):
        import threading
        import time
        def _fetch_loop():
            # İlk tura hızlı başla
            from data.symbols import ACTIVE_UNIVERSE
            for sym in ACTIVE_UNIVERSE:
                self._broker.get_for_symbol(sym) # İçeride zaten thread başlatıyor
                time.sleep(1.0) # Rate limit koruması
            
            # Periyodik (Her 30 dk)
            while True:
                time.sleep(1800)
                for sym in ACTIVE_UNIVERSE:
                    self._broker._fetched.discard(sym) # Cache temizle ki tekrar çeksin
                    self._broker.get_for_symbol(sym)
                    time.sleep(1.0)

        threading.Thread(target=_fetch_loop, daemon=True).start()

    def _toggle_heatmap(self):
        """Heatmap penceresini aç/kapat."""
        if self._heatmap_win is None or not self._heatmap_win.winfo_exists():
            self._heatmap_win = tk.Toplevel(self)
            self._heatmap_win.title("BIST100 Heatmap")
            self._heatmap_win.geometry("900x650")
            self._heatmap_win.configure(bg=BG_DARK)
            
            self._heatmap_panel = HeatmapPanel(self._heatmap_win, on_symbol_click=self._on_symbol_click)
            self._heatmap_panel.pack(fill="both", expand=True)
            
            # Seçili sembolü senkronize et
            if self._selected_symbol:
                self._heatmap_panel.set_selected(self._selected_symbol)
        else:
            self._heatmap_win.lift()
            self._heatmap_win.focus_force()

# ── Geriye dönük uyumluluk aliası ────────────────────────────
TradingTerminalApp = TradingCockpit
