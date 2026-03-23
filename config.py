# ============================================================
# config.py — BIST v2 Konfigürasyonu
# ============================================================

# ── Evren ────────────────────────────────────────────────────
UNIVERSE = "BIST30"   # BIST30, BIST50, BIST100

# ── Sermaye & Pozisyon ───────────────────────────────────────
CAPITAL_TL          = 50_000     # Toplam sermaye
MAX_POSITIONS       = 5          # Maks açık pozisyon
RISK_PER_TRADE_PCT  = 1.5        # Pozisyon başına risk %

# ── 80/20 Portföy Ağırlığı ───────────────────────────────────
CORE_WEIGHT  = 0.80   # CORE_EDGE (1-30 gün tutma) → sermayenin %80'i
SWING_WEIGHT = 0.20   # SWING_EDGE (gün içi vur-kaç) → sermayenin %20'si

# ── CORE_EDGE Kriterleri ─────────────────────────────────────
CORE_RS_THRESHOLD            = 1.15   # RS endeksi bu kadar geçmeli
CORE_CONSOLIDATION_THRESHOLD = 0.05   # ATR/Kapanış < %5 (dar bant)
CORE_VOL_THRESHOLD           = 1.5    # Hacim ortalamanın 1.5x üstünde
CORE_STOP_ATR                = 2.0    # 2×ATR
CORE_TARGET_ATR              = 5.0    # 5×ATR

# ── SWING_EDGE Kriterleri ─────────────────────────────────────
SWING_RSI3_THRESHOLD         = 15.0   # RSI3 < 15 = aşırı satım zıplaması
SWING_GAP_RS_THRESHOLD       = 1.05   # Gap-Up için min RS
SWING_STOP_ATR               = 1.0    # 1×ATR
SWING_TARGET_ATR             = 1.5    # 1.5×ATR

# ── Telegram ─────────────────────────────────────────────────
# .env dosyasından okunur — buraya token yazmayın!
# TELEGRAM_TOKEN=...
# TELEGRAM_CHAT_ID=...
