import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import os

# BIST Terminal modüllerini import etmek için path ayarı (main.py ile aynı dizinde çalışacak)
app = FastAPI(title="BIST Terminal Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock veri veya gerçek cache'den veri okuma fonksiyonu
def get_live_data():
    # Bu basit bir örnek; normalde MarketBus veya bir JSON dosyasından okuyabilir
    # Şimdilik data/positions.json veya benzeri bir yerden sembolik veri çekelim
    try:
        # Gerçek bir sinyal motoru çıktısı simülasyonu
        return {
            "market_status": "OPEN",
            "bist100": 9145.20,
            "bist100_change": 1.2,
            "active_signals_count": 8,
            "ai_confidence": 88.4,
            "signals": [
                {"symbol": "THYAO", "price": 285.50, "action": "AL", "confidence": 92},
                {"symbol": "EREGL", "price": 42.10, "action": "SAT", "confidence": 65},
                {"symbol": "ASELS", "price": 55.30, "action": "IZLE", "confidence": 78},
            ]
        }
    except Exception:
        return {"error": "Veri okunamadı"}

@app.get("/api/status")
async def status():
    return get_live_data()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
