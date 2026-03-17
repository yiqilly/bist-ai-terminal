import time
import subprocess
import datetime
import sys
import os

def start_at_open():
    # Borsa açılış saati
    TARGET_TIME = datetime.time(9, 59, 30) # 30 saniye erken başlat (ısınma için)
    
    print("="*60)
    print(" BIST TRADING COCKPIT - OTOMATİK BAŞLATICI ")
    print("="*60)
    
    while True:
        now = datetime.datetime.now()
        current_time = now.time()
        
        if current_time >= TARGET_TIME and current_time < datetime.time(18, 0):
            print(f"[{now.strftime('%H:%M:%S')}] Pazar açıldı veya açılmak üzere. Başlatılıyor...")
            
            # Ana terminali başlat
            # Not: python main.py olarak başlatıyoruz
            try:
                subprocess.Popen([sys.executable, "main.py"], cwd=os.getcwd())
                print("Terminal başlatıldı. İyi seanslar!")
                break
            except Exception as e:
                print(f"Hata: {e}")
                break
        else:
            wait_seconds = 30
            # Eğer açılışa çok az kaldıysa daha sık kontrol et
            if current_time >= datetime.time(9, 58):
                wait_seconds = 5
            
            print(f"[{now.strftime('%H:%M:%S')}] Henüz erken. Saat 09:59:30 bekleniyor... ({wait_seconds}s sonra tekrar kontrol edilecek)", end='\r')
            time.sleep(wait_seconds)

if __name__ == "__main__":
    start_at_open()
