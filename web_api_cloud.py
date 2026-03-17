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
            # 1 günlük veriyi ve son fiyatı al
            df = ticker.history(period="1d")
            if not df.empty:
                last_price = df['Close'].iloc[-1]
                prev_close = ticker.info.get('previousClose', last_price)
                change = ((last_price - prev_close) / prev_close) * 100
                
                results["signals"].append({
                    "symbol": sym.replace(".IS", ""),
                    "price": round(last_price, 2),
                    "change": round(change, 2),
                    "action": "AL" if change > 1 else "IZLE" if change > -1 else "SAT"
                })
                total_change += change
        except:
            continue
            
    results["market_score"] = round(50 + (total_change * 3), 1)
    return results

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
