# ============================================================
# alerts/alert_engine.py — Alert Engine v4
# Core strateji alertleri dahil.
# ============================================================
from __future__ import annotations
from collections import deque
from data.models import AlertEvent, RankedSignal, RegimeResult
from datetime import datetime


class AlertEngine:
    THRESHOLDS = {
        "elite_signal_confidence": 75,
        "flow_spike": 7.5,
        "core_edge_strong": 7.0,
    }

    def __init__(self, max_alerts: int = 60):
        self._alerts: deque[AlertEvent] = deque(maxlen=max_alerts)
        self._last_regime: str | None = None
        self._last_core_regime: str | None = None
        self._seen: set[str] = set()

    def process(
        self,
        ranked: list[RankedSignal],
        regime: RegimeResult | None,
    ) -> list[AlertEvent]:
        new_alerts = []

        for s in ranked:
            sym = s.candidate.symbol

            # Elite sinyal
            key = f"elite_{sym}_{s.quality_label}_{s.candidate.score}"
            if s.quality_label == "Elite" and key not in self._seen:
                self._seen.add(key)
                evt = AlertEvent(
                    event_type="elite_signal", symbol=sym,
                    message=f"⚡ Elite sinyal: {sym} | AI={s.ai_score:.1f} | Conf={s.confidence:.0f}%",
                    severity="critical")
                new_alerts.append(evt); self._alerts.appendleft(evt)

            # Flow spike
            if s.flow_score and s.flow_score >= self.THRESHOLDS["flow_spike"]:
                key = f"flow_{sym}"
                if key not in self._seen:
                    self._seen.add(key)
                    evt = AlertEvent(
                        event_type="flow_spike", symbol=sym,
                        message=f"💰 Akış sinyali: {sym} | Flow={s.flow_score:.1f}",
                        severity="warning")
                    new_alerts.append(evt); self._alerts.appendleft(evt)

            # Teknik + haber confluence
            if s.news_score > 0.4 and s.candidate.score >= 5:
                key = f"conf_{sym}"
                if key not in self._seen:
                    self._seen.add(key)
                    evt = AlertEvent(
                        event_type="confluence", symbol=sym,
                        message=f"✨ Teknik+Haber çakışması: {sym}",
                        severity="warning")
                    new_alerts.append(evt); self._alerts.appendleft(evt)

            # ── Core Alertler (v4) ────────────────────────
            # Yeni core setup
            if s.core_setup_type != "None":
                key = f"core_setup_{sym}_{s.core_setup_type}"
                if key not in self._seen:
                    self._seen.add(key)
                    evt = AlertEvent(
                        event_type="core_setup", symbol=sym,
                        message=f"🎯 Yeni core setup: {sym} — {s.core_setup_type}",
                        severity="warning")
                    new_alerts.append(evt); self._alerts.appendleft(evt)

            # Breakout + Rebreak confirmed
            if (s.core_setup and
                hasattr(s.core_setup, "has_full_confirmation") and
                s.core_setup.has_full_confirmation):
                key = f"rb_{sym}"
                if key not in self._seen:
                    self._seen.add(key)
                    evt = AlertEvent(
                        event_type="rebreak_confirmed", symbol=sym,
                        message=f"✅ Breakout+Rebreak teyidi: {sym} | Edge={s.core_edge_score:.1f}",
                        severity="critical")
                    new_alerts.append(evt); self._alerts.appendleft(evt)

            # Yüksek Core Edge + Pozitif haber
            if s.core_edge_score >= self.THRESHOLDS["core_edge_strong"] and s.news_score > 0.3:
                key = f"edge_news_{sym}"
                if key not in self._seen:
                    self._seen.add(key)
                    evt = AlertEvent(
                        event_type="edge_news_confluence", symbol=sym,
                        message=f"🌟 Core Edge+Haber: {sym} | Edge={s.core_edge_score:.1f}",
                        severity="critical")
                    new_alerts.append(evt); self._alerts.appendleft(evt)

        # Regime shift
        cur_reg = regime.regime if regime else None
        if cur_reg and cur_reg != self._last_regime:
            if self._last_regime is not None:
                evt = AlertEvent(
                    event_type="regime_shift", symbol="PİYASA",
                    message=f"🔄 Rejim: {self._last_regime} → {cur_reg} ({regime.label})",
                    severity="info")
                new_alerts.append(evt); self._alerts.appendleft(evt)
            self._last_regime = cur_reg

        return new_alerts

    def get_all(self) -> list[AlertEvent]:    return list(self._alerts)
    def get_recent(self, n: int = 10) -> list[AlertEvent]: return list(self._alerts)[:n]
