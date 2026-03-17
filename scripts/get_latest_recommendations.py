
import sys, os
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from recommendations.broker_engine import BrokerEngine
from recommendations.consensus import ConsensusEngine
from data.symbols import get_universe

def main():
    print(f"--- BIST Terminal Analiz (EOD): {datetime.now().strftime('%Y-%m-%d %H:%M')} ---")
    
    broker = BrokerEngine()
    consensus = ConsensusEngine()
    
    # BIST30 sembollerini al
    symbols = get_universe("BIST30")
    print(f"Sorgulanıyor: {len(symbols)} sembol...")
    
    all_recs = []
    for sym in symbols:
        # BrokerEngine internally uses threading for fetching, 
        # but since we're in a script, we might need a small delay or a synchronous call.
        # Actually, let's use the internal _fetch_recommendations directly for speed in this script.
        from recommendations.broker_engine import _fetch_recommendations
        recs = _fetch_recommendations(sym)
        if recs:
            # We don't have current prices easily available without a running bus,
            # so we'll use a dummy price of 1.0 just to get the consensus labels.
            res = consensus.compute(sym, recs, current_price=1.0)
            all_recs.append(res)
            print(f"[{sym}] {res.consensus} | Hedef: {res.avg_target} | Kurum Sayısı: {res.total_recs}")

    print("\n--- Öne Çıkan AL Önerileri (Konsensüs) ---")
    all_recs.sort(key=lambda x: (x.buy_count, x.potential_pct), reverse=True)
    for r in all_recs[:10]:
        print(f"{r.symbol:<10}: {r.consensus} (AL:{r.buy_count}, TUT:{r.hold_count}, SAT:{r.sell_count}) | Hedef: {r.avg_target}")

if __name__ == "__main__":
    main()
