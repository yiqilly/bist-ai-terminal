---
description: BIST Terminal Always-On Bulut API Yayına Alma
---

Bu rehber, bilgisayarın kapalıyken bile çalışan profesyonel sistemi kurmanı sağlar.

### 1. Adım: Kodları GitHub'a Gönder
Aşağıdaki komutları terminaline kopyala-yapıştır:
```powershell
git add .
git commit -m "Faz 5: Cloud API Altyapısı Eklendi"
git push origin main
```

### 2. Adım: Render.com Üzerinde Sunucu Oluşturma
1. [Render.com](https://dashboard.render.com/) adresine git ve GitHub ile giriş yap.
2. **"New +"** butonuna tıkla ve **"Web Service"** seç.
3. **"Build and deploy from a Git repository"** seçiliyken Next de.
4. `bist-ai-terminal` deponu bul ve yanındaki **"Connect"** butonuna bas.

### 3. Adım: Sunucu Ayarları
Aşağıdaki kutucukları tam olarak şöyle doldur:
- **Name:** `bist-terminal-api`
- **Runtime:** `Python 3`
- **Region:** `Frankfurt (EU Central)` - (Sana en yakını)
- **Branch:** `main`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn web_api_cloud:app --host 0.0.0.0 --port $PORT`
- **Instance Type:** `Free` (Ücretsiz olanı seç)

### 4. Adım: Bağlantıyı Kurma
Render kurulumu bittiğinde sana bir adres verecek (Örn: `https://bist-terminal-api.onrender.com`).
1. `index.html` dosyasındaki `const api_url = "..."` kısmına bu yeni adresi yapıştır.
2. Tekrar `git add .`, `git commit` ve `git push` yap.

**Tebrikler!** Artık sistemin 7/24 internette kendi başına çalışıyor.
