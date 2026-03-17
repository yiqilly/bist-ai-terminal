# ============================================================
# strategy/edge_backtest/tracker_runner.py
# CLI Runner for Continuous Edge Tracker
# ============================================================
import argparse
from datetime import date, timedelta
import os
import sys

import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from data.sector_map import get_sector, SECTORS
from strategy.edge_backtest.daily_data import load_index_and_universe
from strategy.edge_backtest.edge_signals import scan_universe
from strategy.edge_backtest.tracker import EdgeTracker, TrackState

def generate_mock_sector_data() -> dict[str, float]:
    """
    Since sector scoring runs intraday via snapshot, we mock a daily sector
    score dictionary here for demonstration. In production, this would load 
    the EOD sector scores.
    """
    import random
    from data.sector_map import SYMBOL_SECTOR
    # Assign random strong/weak scores to sectors for the day
    sector_scores = {sec: random.uniform(40, 75) for sec in SECTORS}
    
    symbol_scores = {}
    for sym, sec in SYMBOL_SECTOR.items():
        symbol_scores[sym] = sector_scores.get(sec, 50.0)
    return symbol_scores

def run_tracker(days_back: int = 1, force_download: bool = False):
    print(f"[*] Running Edge Tracker for last {days_back} days...")
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back + 90) # Need history for signals
    
    # 1. Load Data
    index_df, stock_data = load_index_and_universe(
        start=start_date,
        end=end_date,
        cache=not force_download
    )
    
    if index_df.empty or not stock_data:
        print("[!] Data loading failed.")
        return
        
    print(f"[*] Loaded {len(stock_data)} symbols. Computing signals...")
    
    # 2. Compute Signals
    all_signals_df = scan_universe(stock_data, index_df)
    
    if all_signals_df.empty:
        print("[!] No signals could be computed.")
        return
        
    # 3. Get simulated sector data (in prod, load form EOD sector db)
    # We will just use the hardcoded mapping for now
    sector_scores = generate_mock_sector_data()
    
    # 4. Initialize Tracker
    tracker = EdgeTracker()
    
    # Process day by day to build state history if running multiple days
    # (Usually run on cron daily, so days_back=1)
    dates_to_run = sorted(list(set(all_signals_df.index.date)))[-days_back:]
    
    for run_date in dates_to_run:
        print(f"  -> Processing date: {run_date}")
        tracker.process_day(all_signals_df, sector_scores, run_date)
        
    # 5. Report 
    _print_report(tracker)

def _print_report(tracker: EdgeTracker):
    print("\n" + "="*80)
    print(" " * 25 + "BIST EDGE TRACKER REPORT")
    print("="*80)
    
    def print_state_section(title, state_name, color_code=""):
        items = tracker.get_symbols_by_state(state_name)
        # Sort by edge score logic implicitly or alphabet
        items = sorted(items, key=lambda x: x.sector_score + x.rs_history[-1]*10 if x.rs_history else 0, reverse=True)
        
        print(f"\n{color_code}>>> {title} ({len(items)}) <<<\033[0m")
        if not items:
            print("  Bosta.")
            return
            
        print(f"  {'Symbol':<10} | {'Days':<4} | {'Sector':<6} | {'RS':<5} | {'Vol':<5} | {'Dist%':<6} | {'Note'}")
        print("  " + "-"*76)
        for st in items:
            rs = st.rs_history[-1] if st.rs_history else 0
            vol = st.vol_history[-1] if st.vol_history else 0
            
            rs_str = f"{rs:.2f}"
            vol_str = f"{vol:.1f}x"
            dist_str = f"{st.breakout_distance_pct:+.1f}%"
            
            print(f"  {st.symbol:<10} | {st.days_in_state:<4} | {st.sector_score:<6.1f} | {rs_str:<5} | {vol_str:<5} | {dist_str:<6} | {st.note[:30]}")

    
    # ANSI Colors
    C_GREEN = "\033[92m"
    C_GOLD = "\033[93m"
    C_BLUE = "\033[96m"
    C_GRAY = "\033[90m"

    print_state_section("AL SİNYALLERİ (Teyitli Kırılım)", TrackState.AL, C_GREEN)
    print_state_section("HAZIRLANANLAR (Setup Bekleniyor)", TrackState.HAZIRLANIYOR, C_GOLD)
    print_state_section("İZLENENLER (Takip Listesi)", TrackState.IZLENIYOR, C_BLUE)
    print_state_section("RADARDAKİLER (Erken Sinyal)", TrackState.RADAR, C_GRAY)
    
    print("\n" + "="*80)
    print(f"[*] State saved to: {tracker.state_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Continuous Edge Tracker")
    parser.add_argument("--days", type=int, default=1, help="Number of days to process (simulating history)")
    parser.add_argument("--no-cache", action="store_true", help="Force redownload data")
    
    args = parser.parse_args()
    run_tracker(days_back=args.days, force_download=args.no_cache)
