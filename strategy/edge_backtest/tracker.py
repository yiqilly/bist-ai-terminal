# ============================================================
# strategy/edge_backtest/tracker.py
# Continuous Signal Tracker Engine
# ============================================================
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
import os
from typing import Optional

import pandas as pd

# ── State Definitions ────────────────────────────────────────

class TrackState:
    RADAR = "RADAR"
    IZLENIYOR = "İZLENİYOR"
    HAZIRLANIYOR = "HAZIRLANIYOR"
    AL = "AL"

@dataclass
class TrackerState:
    symbol: str
    state: str = TrackState.RADAR
    first_seen: str = ""
    state_since: str = ""
    days_in_state: int = 0
    
    # History queues (keep last N days)
    rs_history: list[float] = field(default_factory=list)
    vol_history: list[float] = field(default_factory=list)
    
    # Current metrics
    breakout_distance_pct: float = 0.0
    sector_score: float = 0.0
    edge_score: int = 0
    note: str = ""

    def update_metrics(self, rs: float, vol: float, dist: float, sec_score: float, edge: int):
        self.rs_history.append(round(rs, 3))
        self.vol_history.append(round(vol, 3))
        # Keep only last 5 days
        if len(self.rs_history) > 5: self.rs_history.pop(0)
        if len(self.vol_history) > 5: self.vol_history.pop(0)
        
        self.breakout_distance_pct = round(dist, 2)
        self.sector_score = round(sec_score, 1)
        self.edge_score = edge

    def change_state(self, new_state: str, today_str: str, note: str = ""):
        if self.state != new_state:
            self.state = new_state
            self.state_since = today_str
            self.days_in_state = 1
            self.note = note
        else:
            self.days_in_state += 1
            if note: self.note = note


# ── Tracker Engine ───────────────────────────────────────────

class EdgeTracker:
    def __init__(self, state_file: str = "strategy/edge_backtest/tracker_state.json"):
        self.state_file = state_file
        self.states: dict[str, TrackerState] = {}
        self.load_state()
        self.logger = logging.getLogger("EdgeTracker")
        
    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for sym, sd in data.items():
                        self.states[sym] = TrackerState(**sd)
            except Exception as e:
                print(f"Error loading state: {e}")

    def save_state(self):
        os.makedirs(os.path.dirname(self.state_file) or ".", exist_ok=True)
        data = {sym: asdict(st) for sym, st in self.states.items()}
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def process_day(self, signals_df: pd.DataFrame, sectors_dict: dict[str, float], today: date):
        """
        Process EOD signals for a single day and update all states.
        sectors_dict: dict mapping symbol -> sector strength score (0-100)
        """
        today_str = str(today)
        seen_symbols = set()
        
        # We only look at today's signals
        if signals_df.empty:
            return
            
        today_signals = signals_df[signals_df.index.date == today]
        
        for idx, row in today_signals.iterrows():
            sym = row["symbol"]
            seen_symbols.add(sym)
            
            rs = row.get("rs_ratio", 0)
            vol = row.get("vol_ratio", 0)
            consol = row.get("consolidation", 999)
            dist = row.get("breakout_distance", 999)
            breakout = row.get("breakout", False)
            edge = row.get("edge_score", 0)
            sec_score = sectors_dict.get(sym, 50.0)  # Default neutral
            
            # --- Condition Checkers ---
            # RADAR: Mild interest
            is_radar = (rs > 1.1) or (vol > 1.5) or (0 < dist < 5.0) or (sec_score > 55.0)
            
            # HAZIRLANIYOR: Strong setup forming
            is_hazirlaniyor = (rs > 1.3) and (vol > 2.5) and (consol < 0.05) and (sec_score > 60.0)
            
            # AL: Breakout trigger
            is_al = breakout and (rs > 1.3) and (vol > 3.0)
            
            # 1. Get or Create State
            st = self.states.get(sym)
            if not st:
                if is_radar or is_hazirlaniyor or is_al:
                    st = TrackerState(symbol=sym, first_seen=today_str, state_since=today_str)
                    self.states[sym] = st
                else:
                    continue  # Ignore weak symbols not in state
            
            # 2. Update Metrics
            st.update_metrics(rs, vol, dist, sec_score, edge)
            
            # 3. State Transitions
            current = st.state
            
            if is_al:
                st.change_state(TrackState.AL, today_str, "Breakout teyit edildi! (Hacimli ve RS guclu)")
            elif is_hazirlaniyor:
                st.change_state(TrackState.HAZIRLANIYOR, today_str, "Setup sartlari saglandi, kirilim bekleniyor.")
            else:
                # Handle RADAR and IZLENIYOR
                if current == TrackState.AL or current == TrackState.HAZIRLANIYOR:
                    # Downgrade if it lost AL/HAZIRLANIYOR status
                    st.change_state(TrackState.IZLENIYOR, today_str, "Guc kaybetti, izlemeye alindi.")
                elif current == TrackState.IZLENIYOR:
                    # Check if it should be downgraded to RADAR
                    if (rs < 1.0) and (sec_score < 50):
                        st.change_state(TrackState.RADAR, today_str, "Trend zayifladi.")
                    else:
                        st.change_state(TrackState.IZLENIYOR, today_str) # Just increment days
                elif current == TrackState.RADAR:
                    # Upgrade to IZLENIYOR if consistently on RADAR for 3 days and sector is positive
                    if st.days_in_state >= 3 and (rs > 1.2 or vol > 2.0 or sec_score > 55):
                        st.change_state(TrackState.IZLENIYOR, today_str, "Sinyaller sureklilik gosteriyor.")
                    else:
                        st.change_state(TrackState.RADAR, today_str)
                        
        # 4. Cleanup dead symbols
        # If a symbol in our state wasn't seen in today's data (or data is missing), 
        # we increment its days or downgrade it if it's been dead too long.
        symbols_to_remove = []
        for sym, st in self.states.items():
            if sym not in seen_symbols:
                st.days_in_state += 1
                if st.days_in_state > 10 and st.state == TrackState.RADAR:
                    symbols_to_remove.append(sym)
                elif st.state in [TrackState.AL, TrackState.HAZIRLANIYOR]:
                    st.change_state(TrackState.IZLENIYOR, today_str, "Sinyaller kayboldu.")
                    
        for sym in symbols_to_remove:
            self.states.pop(sym, None)
            
        self.save_state()

    def get_symbols_by_state(self, state: str) -> list[TrackerState]:
        return [st for st in self.states.values() if st.state == state]
