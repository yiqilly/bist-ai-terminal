import requests
import time

TOKEN = "8757469495:AAHiKLb6nZTeJBfaajFqvFybT7hNFjaY44k"

def get_chat_id():
    print("Telefonda botu baslattiysaniz (Start dediyseniz) Chat ID tespit ediliyor...")
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    
    try:
        resp = requests.get(url).json()
        if not resp["result"]:
            print("[!] Botla henuz bir konusma baslatilmamis. Lutfen Telegram'dan bota bir mesaj atin.")
            return None
            
        # Son mesaji gönderen kisinin Chat ID'sini al
        chat_id = resp["result"][-1]["message"]["chat"]["id"]
        print(f"[OK] Chat ID Tespit Edildi: {chat_id}")
        return chat_id
    except Exception as e:
        print(f"[ERROR] Hata: {str(e)}")
        return None

def test_send(chat_id):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "BIST Terminal Telegram Baglantisi Kuruldu!\nArtik sinyaller buraya gelecek.",
        "parse_mode": "HTML"
    }
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        print("[OK] Test mesaji basariyla gonderildi!")
    else:
        print(f"[ERROR] Mesaj gonderilemedi: {resp.text}")

if __name__ == "__main__":
    chat_id = get_chat_id()
    if chat_id:
        test_send(chat_id)
