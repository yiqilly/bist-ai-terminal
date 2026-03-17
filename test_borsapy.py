import borsapy as bp
import sys

def test_fetch(symbol):
    print(f"--- {symbol} ---")
    ticker = bp.Ticker(symbol)
    
    print("1. News:")
    try:
        news = ticker.news
        if news is None:
            print("News is None")
        elif hasattr(news, 'empty') and news.empty:
            print("News is empty DataFrame")
        else:
            print(f"News type: {type(news)}")
            if hasattr(news, 'head'):
                print(news.head(2))
            else:
                print(news[:2])
    except Exception as e:
        print(f"News Error: {e}")
        
    print("\n2. Recommendations:")
    try:
        recs = ticker.recommendations
        if recs is None:
            print("Recommendations is None")
        elif hasattr(recs, 'empty') and recs.empty:
            print("Recommendations is empty DataFrame")
        else:
            print(f"Recommendations type: {type(recs)}")
            if hasattr(recs, 'head'):
                print(recs.head(2))
            else:
                print(recs[:2])
    except Exception as e:
        print(f"Recommendations Error: {e}")

if __name__ == "__main__":
    symbols = ["GARAN", "THYAO", "TCELL"]
    for sym in symbols:
        test_fetch(sym)
