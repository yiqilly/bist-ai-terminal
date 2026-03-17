import time
import json
import subprocess
import os

# Verinin kaydedileceği dosya yolu
DATA_FILE = "live_data.json"

def get_bist_data():
    """
    Bu fonksiyon senin mevcut sinyal motorundan veri alacak.
    Şimdilik örnek veriler oluşturuyoruz.
    """
    return {
        "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
        "active_signals": [
            {"symbol": "THYAO", "status": "AL", "confidence": 92},
            {"symbol": "EREGL", "status": "SAT", "confidence": 65},
            {"symbol": "ASELS", "status": "AL", "confidence": 88}
        ],
        "market_score": 78
    }

def sync_to_github():
    print("Veriler güncelleniyor ve GitHub'a yükleniyor...")
    
    # 1. Veriyi JSON dosyasına yaz
    data = get_bist_data()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    # 2. Git komutlarını çalıştır
    try:
        subprocess.run(["git", "add", DATA_FILE], check=True)
        subprocess.run(["git", "commit", "-m", f"Auto-update: {data['last_update']}"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("GitHub başarıyla güncellendi!")
    except Exception as e:
        print(f"Hata oluştu: {e}")

if __name__ == "__main__":
    # Her 15 dakikada bir güncelle (GitHub limitleri için güvenli süre)
    while True:
        sync_to_github()
        print("15 dakika bekleniyor...")
        time.sleep(900) 
