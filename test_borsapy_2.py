import borsapy as bp
import sys

def test_fetch(symbol):
    print(f"--- {symbol} ---")
    ticker = bp.Ticker(symbol)
    
    print("1. News columns:")
    try:
        news = ticker.news
        if hasattr(news, 'columns'):
            print(list(news.columns))
            print(news.iloc[0].to_dict())
    except Exception as e:
        print(e)
        
    print("\n2. Recommendations dict keys:")
    try:
        recs = ticker.recommendations
        if isinstance(recs, dict):
            print(list(recs.keys())[:5])
            first_key = list(recs.keys())[0]
            print(f"First key ({first_key}) value type: {type(recs[first_key])}")
            print(recs[first_key])
    except Exception as e:
        print(e)

if __name__ == "__main__":
    test_fetch("GARAN")
