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
    """ Enriched status with BIST 100 index and detailed signals """
    symbols = ["THYAO.IS", "EREGL.IS", "ASELS.IS", "TUPRS.IS", "KCHOL.IS", "SAHOL.IS", "GARAN.IS"]
    results = {
        "last_update": time.strftime("%H:%M:%S"),
        "market": {"index_val": 0, "change": 0, "regime": "NÖTR", "score": 50},
        "signals": [],
        "setups": [],
        "watchlist": []
    }
    
    # ── BIST 100 Verisi ──
    try:
        bist = yf.Ticker("XU100.IS").history(period="2d")
        if len(bist) >= 2:
            last_b = bist['Close'].iloc[-1]
            prev_b = bist['Close'].iloc[-2]
            ch_b = ((last_b - prev_b) / prev_b) * 100
            results["market"] = {
                "index_val": round(last_b, 2),
                "change": round(ch_b, 2),
                "regime": "🟢 BULL" if ch_b > 0.5 else "🔴 BEAR" if ch_b < -0.5 else "🟡 RANGE",
                "score": round(50 + (ch_b * 10), 1)
            }
    except: pass

    # ── Sinyaller (Gerçek Veri) ──
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(period="30d") # EMA ve RSI için daha çok veri
            if len(df) >= 2:
                last_p = df['Close'].iloc[-1]
                prev_p = df['Close'].iloc[-2]
                ch = ((last_p - prev_p) / prev_p) * 100
                
                # Basit Teknikler
                ema9 = df['Close'].tail(9).mean()
                ema21 = df['Close'].tail(21).mean()
                
                sig_data = {
                    "symbol": sym.replace(".IS", ""),
                    "price": round(last_p, 2),
                    "change": round(ch, 2),
                    "action": "AL" if ch > 0.6 else "IZLE" if ch > -0.6 else "SAT",
                    "rsi": 55 if ch > 0 else 45, # Mock RSI
                    "ema9": round(ema9, 2),
                    "ema21": round(ema21, 2),
                    "trust": round(70 + (ch * 5), 1),
                    "quality": "A+" if ch > 2 else "A" if ch > 0 else "B",
                    "sector": "Bankacılık" if "GARAN" in sym else "Sanayi"
                }

                if sig_data["action"] == "AL":
                    results["signals"].append(sig_data)
                elif sig_data["action"] == "IZLE":
                    results["watchlist"].append(sig_data)
                else:
                    results["setups"].append(sig_data) # Setup olarak gösterelim
        except: continue
        
    return results

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
