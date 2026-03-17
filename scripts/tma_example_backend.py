from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# Mini App'in backend'e erişebilmesi için CORS ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Gerçek projede bunu sınırlamalısınız
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/signals")
async def get_signals():
    # Bu veriler normalde senin BIST terminal motorundan gelecek
    return [
        {"symbol": "THYAO", "action": "BUY", "price": 285.50, "confidence": 85},
        {"symbol": "EREGL", "action": "SELL", "price": 42.10, "confidence": 70},
        {"symbol": "ASELS", "action": "BUY", "price": 55.30, "confidence": 92},
    ]

if __name__ == "__main__":
    print("BIST Mini App Backend Çalışıyor: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
