# ============================================================
# config.py — BIST v2 Konfigürasyonu
# ============================================================

# ── Evren ────────────────────────────────────────────────────
UNIVERSE = "BIST100"  # BIST30, BIST50, BIST100

# ── Sermaye & Pozisyon ───────────────────────────────────────
CAPITAL_TL          = 50_000     # Toplam sermaye
MAX_POSITIONS       = 5          # Maks açık pozisyon
RISK_PER_TRADE_PCT  = 1.5        # Pozisyon başına risk %

# ── CORE_EDGE Kriterleri ─────────────────────────────────────
CORE_RS_THRESHOLD            = 1.03   # RS endeksi bu kadar geçmeli
CORE_CONSOLIDATION_THRESHOLD = 0.05   # ATR/Kapanış < %5 (dar bant)
CORE_VOL_THRESHOLD           = 1.5    # Hacim ortalamanın 1.5x üstünde
CORE_STOP_ATR                = 2.0    # 2×ATR
CORE_TARGET_ATR              = 5.0    # 5×ATR
CORE_SECTOR_THRESHOLD        = 50.0   # Sektör gücü >= 50 (nötr veya yükselen sektör)
CORE_PULLBACK_BARS           = 2      # Daha iyi giriş için max beklenen bar sayısı
CORE_PULLBACK_ATR            = 0.3    # Beklenen geri çekilme (ATR katsayısı)

# ── Telegram ─────────────────────────────────────────────────
# .env dosyasından okunur — buraya token yazmayın!
# TELEGRAM_TOKEN=...
# TELEGRAM_CHAT_ID=...
