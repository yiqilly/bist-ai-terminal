from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import uvicorn
import time

app = FastAPI(title="BIST Real-Time Cloud API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"],
)

@app.get("/")
async def root():
    return {"message": "BIST Terminal API is running. Data is at /api/status"}

@app.get("/api/status")
async def get_status():
    """
    Bu endpoint çağrıldığında canlı BIST verilerini çeker.
    Bilgisayarın kapalı olsa bile bu bulut sunucusu çalışmaya devam eder.
    """
    symbols = ["THYAO.IS", "EREGL.IS", "ASELS.IS", "TUPRS.IS", "KCHOL.IS"]
    results = {
        "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
        "signals": [],
        "market_score": 0
    }
    
    total_change = 0
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            # 2 günlük veri alıyoruz (bugün ve dün) hızı artırmak için
            df = ticker.history(period="2d")
            if len(df) >= 2:
                last_price = df['Close'].iloc[-1]
                prev_close = df['Close'].iloc[-2]
                change = ((last_price - prev_close) / prev_close) * 100
                
                results["signals"].append({
                    "symbol": sym.replace(".IS", ""),
                    "price": round(last_price, 2),
                    "change": round(change, 2),
                    "action": "AL" if change > 0.5 else "IZLE" if change > -0.5 else "SAT"
                })
                total_change += change
            elif not df.empty:
                # Sadece bugün varsa
                last_price = df['Close'].iloc[-1]
                results["signals"].append({
                    "symbol": sym.replace(".IS", ""),
                    "price": round(last_price, 2),
                    "change": 0.0,
                    "action": "IZLE"
                })
        except Exception as e:
            print(f"Hata {sym}: {e}")
            continue
            
    results["market_score"] = round(50 + (total_change * 3), 1)
    return results

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
