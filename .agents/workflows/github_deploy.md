---
description: BIST Terminal'i GitHub Pages Üzerinden Yayına Alma
---

Bu workflow, yerel bilgisayarındaki projeyi GitHub'a yükleyip web sitesi olarak yayına almanı sağlar.

### 1. Adım: Git Deposu Başlatma
Eğer projen daha önce git ile takip edilmiyorsa terminalde şu komutları sırasıyla çalıştır:
```powershell
git init
git add .
git commit -m "Initial commit for BIST Website"
```

### 2. Adım: GitHub'da Yeni Repository Oluşturma
- [github.com/new](https://github.com/new) adresine git.
- Repository ismini `bist_terminal` (veya istediğiniz başka bir şey) yap.
- **Public** (Açık) seçeneğinin seçili olduğundan emin ol.
- "Create repository" butonuna bas.

### 3. Adım: Kodları GitHub'a Gönderme
Aşağıdaki komutları terminale sırasıyla yapıştır (Kullanıcı adını kontrol etmeyi unutma):
```powershell
git remote add origin https://github.com/yiqilly/bist-ai-terminal.git
git branch -M main
git push -u origin main
```

### 4. Adım: GitHub Pages'i Aktif Etme
1. GitHub'daki repository sayfanda **Settings** (Ayarlar) sekmesine tıkla.
2. Sol menüden **Pages** seçeneğini seç.
3. "Build and deployment" kısmındaki **Branch** ayarını `main` yap ve yanındaki menüden `/(root)` seçiliyken **Save** butonuna bas.
4. Birkaç dakika sonra sayfanın üstünde sitenin linki belirecektir: `https://kullaniciadin.github.io/bist_terminal`

### 🔥 İpucu
Hazırladığım `index.html` dosyası otomatik olarak ana sayfan olacaktır. Artık siten tüm dünyaya açık!
