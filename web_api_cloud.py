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
    """ Optimized batch fetch for all symbols """
    symbols = [
        "THYAO.IS", "EREGL.IS", "ASELS.IS", "TUPRS.IS", "KCHOL.IS", "SAHOL.IS", "GARAN.IS", "SISE.IS", 
        "AKBNK.IS", "YKBNK.IS", "BIMAS.IS", "HEKTS.IS", "SASA.IS", "PGRUS.IS", "EKGYO.IS", "DOHOL.IS", 
        "HALKB.IS", "ISCTR.IS", "VAKBN.IS", "PETKM.IS", "ARCLK.IS", "TOASO.IS", "FROTO.IS", "TCELL.IS", 
        "TKFEN.IS", "KOZAL.IS", "KOZAA.IS", "PGSUS.IS", "OTKAR.IS", "ENKAI.IS", "XU100.IS"
    ]
    results = {
        "last_update": time.strftime("%H:%M:%S"),
        "market": {"index_val": 0, "change": 0, "regime": "NÖTR", "score": 50},
        "signals": [], "setups": [], "watchlist": [], 
        "positions": [], "opportunities": [], "sectors": [
            {"symbol": "BANKACILIK", "price": "ENDEKS", "change": 1.2, "quality": "A", "sector": "Mali", "strategy": "BULL", "setup": "Breakout", "trust": 85},
            {"symbol": "SANAYI", "price": "ENDEKS", "change": -0.5, "quality": "B", "sector": "Sanayi", "strategy": "RANGE", "setup": "Rotation", "trust": 60}
        ]
    }
    
    try:
        # Tüm sembolleri tek seferde indir (Maksimum hız)
        data = yf.download(symbols, period="2d", interval="1d", progress=False)
        
        # BIST 100 (Index)
        if "XU100.IS" in data['Close']:
            idx_close = data['Close']['XU100.IS']
            if len(idx_close) >= 2:
                last_b = idx_close.iloc[-1]
                prev_b = idx_close.iloc[-2]
                ch_b = ((last_b - prev_b) / prev_b) * 100
                results["market"] = {
                    "index_val": round(last_b, 2),
                    "change": round(ch_b, 4),
                    "regime": "🟢 BULL" if ch_b > 0.3 else "🔴 BEAR" if ch_b < -0.3 else "🟡 RANGE",
                    "score": round(50 + (ch_b * 10), 1)
                }

        # Diğer Hisseler
        for sym in symbols:
            if sym == "XU100.IS": continue
            if sym in data['Close']:
                prices = data['Close'][sym]
                if len(prices) >= 2:
                    last_p = prices.iloc[-1]
                    prev_p = prices.iloc[-2]
                    ch = ((last_p - prev_p) / prev_p) * 100
                    
                    sig_data = {
                        "symbol": sym.replace(".IS", ""),
                        "price": round(last_p, 2),
                        "change": round(ch, 2),
                        "action": "AL" if ch > 0.5 else "IZLE" if ch > -0.5 else "SAT",
                        "rsi": round(50 + (ch * 5), 0),
                        "ema9": round(last_p * 0.99, 2),
                        "ema21": round(last_p * 0.97, 2),
                        "trust": round(70 + (ch * 5), 1),
                        "quality": "A+" if ch > 1.5 else "A" if ch > 0 else "B",
                        "sector": "Bankacılık" if "GARAN" in sym or "SAHOL" in sym else "Sanayi",
                        "strategy": "BULL_BREAKOUT" if ch > 0 else "RANGE_ROTATION",
                        "setup": "Kırılım" if ch > 0 else "Dip Dönüşü",
                        "entry": round(last_p, 2),
                        "stop": round(last_p * 0.97, 2),
                        "target": round(last_p * 1.05, 2),
                        "rr": 2.4,
                        "reason": f"Trend { 'Güçlü' if ch > 0 else 'Zayıf' }",
                        "lot": 0
                    }

                    if sig_data["action"] == "AL": 
                        results["signals"].append(sig_data)
                        results["opportunities"].append(sig_data)
                    elif sig_data["action"] == "IZLE": 
                        results["watchlist"].append(sig_data)
                    else: 
                        results["setups"].append(sig_data)
                    
                    # Mock some positions for UI demonstration
                    if sym in ["THYAO.IS", "EREGL.IS"]:
                        pos_data = sig_data.copy()
                        pos_data["lot"] = 100
                        results["positions"].append(pos_data)
                    
    except Exception as e:
        print(f"Genel Hata: {e}")
        
    return results

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
