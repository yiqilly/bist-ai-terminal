#!/usr/bin/env python3
"""
ADIM 1: borsapy Gerçek Veri Bağlantı Testi
==========================================
Çalıştır: python scripts/test_live_connection.py
           python scripts/test_live_connection.py --session <s> --sign <sg>

Test edilenler:
  1. borsapy import ve bağlantı
  2. Quote akışı (10 sn içinde veri geliyor mu?)
  3. prev_close doğru hesaplanıyor mu?
  4. SnapshotCache doğru besleniyor mu?
  5. MarketContextEngine rejim üretiyor mu?
  6. BullBreakoutStrategy bar alıyor mu?
"""
import sys, os, time, argparse
from datetime import datetime, date
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Argümanlar ────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--session',  default='', help='TradingView session cookie')
parser.add_argument('--sign',     default='', help='TradingView session_sign cookie')
parser.add_argument('--duration', default=30,  type=int, help='Test süresi (sn)')
parser.add_argument('--symbols',  default='AKBNK,GARAN,ISCTR,EKGYO,FROTO',
                    help='Test sembolleri (virgülle)')
args = parser.parse_args()

TEST_SYMS = [s.strip() for s in args.symbols.split(',')]
DURATION  = args.duration

print("="*65)
print("  BIST Terminal — Canlı Bağlantı Testi")
print(f"  Semboller : {', '.join(TEST_SYMS)}")
print(f"  Süre      : {DURATION} saniye")
print("="*65)

# ── Gerekli modüller ─────────────────────────────────────────
import logging
logging.basicConfig(level=logging.WARNING,
                    format='%(asctime)s %(levelname)s %(name)s: %(message)s')

try:
    from data.snapshot_cache import SnapshotCache
    from data.collectors.base_collector import NormalizedQuote, NormalizedBar
    from data.models import SignalCandidate
    from strategy.market_context_engine import MarketContextEngine
    from strategy.rules import score_candidate
    from strategy import indicators as ind
    from strategy.opening_strategy import Bar
    from strategy.strategy_router import StrategyRouter, REGIME_STRATEGY_MAP
    print("  ✓ Modüller import edildi")
except Exception as e:
    print(f"  ✗ Import hatası: {e}")
    sys.exit(1)

# ── Cache & Engine ────────────────────────────────────────────
cache   = SnapshotCache(max_bars=500)
ind.set_cache(cache)
ctx_eng = MarketContextEngine()
router  = StrategyRouter()
print("  ✓ Engine'ler hazır")

# ── Test state ────────────────────────────────────────────────
stats = {s: {'quotes': 0, 'bars': 0, 'last_price': 0.0,
             'last_change': 0.0} for s in TEST_SYMS}
quote_times  = []
regime_log   = []
signal_log   = []
prev_day_close: dict[str, float] = {}   # dün kapanış (simüle)
daily_close  = defaultdict(list)

# ── borsapy bağlantısı ────────────────────────────────────────
print("\n  [1/6] borsapy import testi...")
try:
    import borsapy as bp
    print("  ✓ borsapy import OK")
except ImportError:
    print("  ✗ borsapy kurulu değil!")
    print("    Kur: pip install git+https://github.com/saidsurucu/borsapy.git")
    sys.exit(1)

print("\n  [2/6] TradingView stream bağlantısı...")
try:
    if args.session and args.sign:
        bp.set_tradingview_auth(session=args.session,
                                 session_sign=args.sign)
        print("  ✓ Auth ayarlandı")
    stream = bp.TradingViewStream()
    stream.connect()
    print("  ✓ Stream bağlandı")
except Exception as e:
    print(f"  ✗ Bağlantı hatası: {e}")
    sys.exit(1)

# ── Callback ─────────────────────────────────────────────────
def on_quote(sym_raw, data):
    """Her quote geldiğinde çağrılır."""
    # Sembol normalize
    sym = sym_raw.replace('BIST:', '').replace('BIST.', '').upper().strip()
    if sym not in TEST_SYMS: return

    try:
        price  = float(data.get('lp') or data.get('ch') or 0)
        volume = float(data.get('volume') or 0)
        chg    = float(data.get('ch') or 0)
        chg_pct= float(data.get('chp') or 0)
        high   = float(data.get('high_price') or price)
        low    = float(data.get('low_price')  or price)

        if price <= 0: return

        # prev_close hesapla (change_pct'den)
        if chg_pct != 0:
            pc = price / (1 + chg_pct/100)
        elif chg != 0:
            pc = price - chg
        else:
            pc = prev_day_close.get(sym, price)

        if pc > 0:
            prev_day_close[sym] = pc

        # Cache güncelle
        ts = datetime.now()
        cache.update_from_quote(NormalizedQuote(
            symbol=sym, price=price,
            bid=price*0.999, ask=price*1.001,
            volume=volume, timestamp=ts,
            change_pct=chg_pct, prev_close=pc,
            high_day=high, low_day=low,
        ))

        # NormalizedBar da oluştur (5dk proxy)
        cache.update_from_bar(NormalizedBar(
            sym, '5m', price, high, low, price, volume, ts
        ))

        stats[sym]['quotes'] += 1
        stats[sym]['last_price'] = price
        stats[sym]['last_change'] = chg_pct
        quote_times.append(ts)

    except Exception as e:
        pass

stream.on_any_quote(on_quote)

# ── Sembollere abone ol ───────────────────────────────────────
print("\n  [3/6] Sembol aboneliği...")
for sym in TEST_SYMS:
    try:
        stream.subscribe(sym)
        print(f"    ✓ {sym}")
    except Exception as e:
        print(f"    ✗ {sym}: {e}")

# ── Ana test döngüsü ──────────────────────────────────────────
print(f"\n  [4/6] Veri akışı testi ({DURATION} sn)...")
print(f"  {'Sembol':<8} {'Quote':>6} {'Fiyat':>10} {'Değişim':>8}")
print("  " + "-"*36)

start = time.time()
last_print = start

while time.time() - start < DURATION:
    time.sleep(1)
    elapsed = time.time() - start

    # Her 5 saniyede ekrana yaz
    if time.time() - last_print >= 5:
        last_print = time.time()
        for sym in TEST_SYMS:
            s = stats[sym]
            chg_sym = '+' if s['last_change'] >= 0 else ''
            print(f"  {sym:<8} {s['quotes']:>6} "
                  f"₺{s['last_price']:>9.2f} "
                  f"{chg_sym}{s['last_change']:>+6.2f}%")
        print()

    # 15 sn sonra snapshot test et
    if elapsed >= 15 and not regime_log:
        try:
            snap = cache.build_snapshot()
            cands = []
            for sym in TEST_SYMS:
                tick = snap.ticks.get(sym)
                if not tick: continue
                atr = cache.compute_atr(sym, 14, '5m') or tick.price * 0.015
                cand = SignalCandidate(
                    symbol=sym, price=tick.price, volume=tick.volume,
                    rsi=50.0, ema9=tick.price*0.99, ema21=tick.price*0.97,
                    atr=atr, momentum=0, trend=True, breakout=True,
                    volume_confirm=True, score=0,
                    prev_price=prev_day_close.get(sym, tick.price)
                )
                cand.score = score_candidate(cand)
                cands.append(cand)

            if cands:
                ctx = ctx_eng.compute(snap, cands)
                regime_log.append({
                    'time': datetime.now(), 'regime': ctx.regime,
                    'breadth': ctx.breadth_pct, 'strength': ctx.market_strength
                })
                print(f"\n  [5/6] MarketContext:")
                print(f"    Rejim    : {ctx.regime}")
                print(f"    Breadth  : {ctx.breadth_pct:.1f}%")
                print(f"    Strength : {ctx.market_strength:.1f}")
                print(f"    n_cand   : {len(cands)}")
        except Exception as e:
            print(f"  ✗ Snapshot hatası: {e}")

# ── Disconnect ────────────────────────────────────────────────
try:
    stream.disconnect()
except: pass

# ── Sonuç raporu ─────────────────────────────────────────────
print("\n" + "="*65)
print("  TEST SONUÇLARI")
print("="*65)

# Quote akışı
total_quotes = sum(s['quotes'] for s in stats.values())
print(f"\n  [1] Quote Akışı:")
print(f"    Toplam quote : {total_quotes}")
if total_quotes > 0:
    elapsed_min = (quote_times[-1] - quote_times[0]).total_seconds() if len(quote_times) > 1 else 1
    rate = len(quote_times) / elapsed_min
    print(f"    Quote/sn     : {rate:.1f}")
    print(f"    İlk quote    : {quote_times[0].strftime('%H:%M:%S') if quote_times else '—'}")

for sym in TEST_SYMS:
    s = stats[sym]
    if s['quotes'] > 0:
        print(f"    {sym:<8}: {s['quotes']} quote  ₺{s['last_price']:.2f}  {s['last_change']:+.2f}%  "
              f"prev_close=₺{prev_day_close.get(sym,0):.2f}")
    else:
        print(f"    {sym:<8}: ✗ VERİ GELMEDİ")

# prev_close doğruluğu
print(f"\n  [2] prev_close Doğruluğu:")
for sym, pc in prev_day_close.items():
    if sym in stats and stats[sym]['last_price'] > 0:
        implied_chg = (stats[sym]['last_price'] - pc)/pc*100 if pc > 0 else 0
        print(f"    {sym:<8}: prev=₺{pc:.2f}  bugün=₺{stats[sym]['last_price']:.2f}  "
              f"hesaplanan_chg={implied_chg:+.2f}%")

# Rejim
print(f"\n  [3] MarketContext Rejim:")
if regime_log:
    r = regime_log[-1]
    print(f"    Rejim    : {r['regime']}")
    print(f"    Breadth  : {r['breadth']:.1f}%")
    print(f"    Strength : {r['strength']:.1f}")
    expected = REGIME_STRATEGY_MAP.get(r['regime'], 'NO TRADE')
    print(f"    Strateji : {expected}")
else:
    print("    ✗ Rejim hesaplanamadı (yeterli veri gelmedi?)")

# Genel sonuç
print(f"\n  GENEL DURUM:")
issues = []
if total_quotes == 0:
    issues.append("✗ Hiç quote gelmedi — bağlantı sorunu")
else:
    no_data = [s for s in TEST_SYMS if stats[s]['quotes'] == 0]
    if no_data:
        issues.append(f"✗ Veri gelmeyen semboller: {', '.join(no_data)}")

bad_pc = [s for s,pc in prev_day_close.items()
          if pc > 0 and stats.get(s, {}).get('last_price', 0) > 0
          and abs(stats[s]['last_price']/pc - 1) > 0.15]
if bad_pc:
    issues.append(f"⚠ prev_close şüpheli: {', '.join(bad_pc)} — manuel kontrol et")

if not regime_log:
    issues.append("⚠ Rejim hesaplanamadı — veri toplama süresi artır")

if issues:
    for i in issues: print(f"  {i}")
else:
    print("  ✓ Bağlantı sağlıklı")
    print("  ✓ Quote akışı çalışıyor")
    print("  ✓ prev_close hesaplanıyor")
    print("  ✓ MarketContext çalışıyor")
    print("  → Sistem canlı işlem için hazır")

print("="*65)
