import yfinance as yf
import json
import time

def fetch_cloud_data():
    # Takip edilecek hisseler
    symbols = ["THYAO.IS", "EREGL.IS", "ASELS.IS", "TUPRS.IS", "KCHOL.IS"]
    
    results = {
        "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
        "active_signals": [],
        "market_score": 0
    }
    
    total_change = 0
    
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            data = ticker.history(period="1d")
            if not data.empty:
                current_price = data['Close'].iloc[-1]
                open_price = data['Open'].iloc[0]
                change_pct = ((current_price - open_price) / open_price) * 100
                
                # Basit bir sinyal mantığı (Örn: %1 üstü artış AL)
                action = "IZLE"
                if change_pct > 1.5: action = "AL"
                elif change_pct < -1.5: action = "SAT"
                
                results["active_signals"].append({
                    "symbol": sym.replace(".IS", ""),
                    "price": round(current_price, 2),
                    "change": round(change_pct, 2),
                    "action": action
                })
                total_change += change_pct
        except Exception as e:
            print(f"Hata {sym}: {e}")

    results["market_score"] = round(50 + (total_change * 5), 1)
    
    with open("live_data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    
    print("Cloud verisi başarıyla güncellendi.")

if __name__ == "__main__":
    fetch_cloud_data()
