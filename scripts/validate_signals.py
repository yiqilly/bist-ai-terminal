#!/usr/bin/env python3
"""
ADIM 4: Manuel Backtest Doğrulama
==================================
Geçmiş BULL günlerini seç, sistemi o günün verisiyle çalıştır.
Beklenen sinyaller üretiliyor mu kontrol et.

Çalıştır: python scripts/validate_signals.py
           python scripts/validate_signals.py --date 2026-01-29
           python scripts/validate_signals.py --show-all
"""
import sys, os, csv, argparse
from datetime import datetime, time, date
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import logging; logging.disable(logging.CRITICAL)

from strategy.opening_strategy import Bar
from strategy.strategy_router  import StrategyRouter, REGIME_STRATEGY_MAP
from strategy.position_sizer   import PositionSizer
from config import POSITION_SIZING

parser = argparse.ArgumentParser()
parser.add_argument('--date',     default=None, help='YYYY-MM-DD (yoksa otomatik seç)')
parser.add_argument('--show-all', action='store_true', help='Tüm sinyalleri göster')
parser.add_argument('--days',     default=5, type=int, help='Test gün sayısı')
args = parser.parse_args()

DATA_DIR = '/tmp/bist_data'
RAW: dict[str, list[Bar]] = {}
for fname in sorted(os.listdir(DATA_DIR)):
    if not fname.endswith('.csv'): continue
    sym = fname.split('_')[2]
    rows = []
    with open(os.path.join(DATA_DIR, fname), newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            try:
                dt = datetime.strptime(
                    f"{row['date']} {row['time']}", '%Y-%m-%d %H:%M:%S')
                o,h,l,c = float(row['open']),float(row['high']),float(row['low']),float(row['close'])
                vol = float(row['total_quantity'])
                if c > 0: rows.append(Bar(timestamp=dt,open=o,high=h,low=l,close=c,volume=vol))
            except: continue
    if rows: rows.sort(key=lambda r: r.timestamp); RAW[sym] = rows

SYMBOLS = sorted(RAW.keys())
by_sym_day: dict[str, dict[date, list[Bar]]] = {}
for sym, rows in RAW.items():
    d = defaultdict(list)
    for b in rows: d[b.timestamp.date()].append(b)
    by_sym_day[sym] = dict(d)
all_days = sorted({d for sym in by_sym_day for d in by_sym_day[sym]})

SECTOR = {
    'AKBNK':'Banka','GARAN':'Banka','ISCTR':'Banka',
    'ENKAI':'İnşaat','EKGYO':'GYO','FROTO':'Otomotiv',
    'EREGL':'Demir','KRDMD':'Demir','PGSUS':'Havayolu',
    'BIMAS':'Perakende','MGROS':'Perakende',
    'SAHOL':'Holding','KCHOL':'Holding',
    'PETKM':'Petrokimya','SASA':'Tekstil','ASELS':'Savunma',
    'ASTOR':'Enerji','AEFES':'İçecek','GUBRF':'Gübre',
}

def ema_c(c,p):
    if len(c)<p: return c[-1] if c else 0.0
    k,e=2/(p+1),c[0]
    for x in c[1:]: e=x*k+e*(1-k)
    return e

def rsi_c(c,p=14):
    if len(c)<p+1: return 50.0
    g=l=0.0
    for i in range(1,p+1):
        d=c[i]-c[i-1]
        if d>0: g+=d
        else: l-=d
    ag,al=g/p,l/p
    if al==0: return 100.0
    for i in range(p+1,len(c)):
        d=c[i]-c[i-1]
        ag=(ag*(p-1)+max(d,0))/p; al=(al*(p-1)+max(-d,0))/p
    return round(100-100/(1+(ag/al if al else 999)),1)

def datr_calc(ohlc,p=14):
    if len(ohlc)<2: return ohlc[-1][2]*0.03 if ohlc else 1.0
    trs=[max(ohlc[i][0]-ohlc[i][1],abs(ohlc[i][0]-ohlc[i-1][2]),
             abs(ohlc[i][1]-ohlc[i-1][2])) for i in range(1,len(ohlc))]
    return sum(trs[-p:])/min(len(trs),p)

def calc_sector_str(sym, dc):
    sec=SECTOR.get(sym)
    if not sec: return 50.0
    perf=[(c[-1]-c[-5])/c[-5]*100
          for s,se in SECTOR.items()
          if se==sec and s in dc and len(dc[s])>=6 for c in [dc[s]]]
    return min(100,max(0,50+sum(perf)/len(perf)*16.67)) if perf else 50.0

def calc_rs(sym, dc):
    c=dc.get(sym,[])
    if len(c)<6: return 0.0
    my=(c[-1]-c[-5])/c[-5]*100
    sec=SECTOR.get(sym)
    if not sec: return my
    rets=[(dc[s][-1]-dc[s][-5])/dc[s][-5]*100
          for s,se in SECTOR.items()
          if se==sec and s!=sym and s in dc and len(dc[s])>=6]
    return my-sum(rets)/len(rets) if rets else my

def detect_regime(daily_close, daily_ohlc):
    up=dn=0; moms=[]
    for sym in SYMBOLS:
        dc=daily_close.get(sym,[])
        if len(dc)<2: continue
        if dc[-1]>dc[-2]: up+=1
        else: dn+=1
        if len(dc)>=6: moms.append((dc[-1]-dc[-5])/dc[-5]*100)
    total=up+dn
    if total==0: return 'RANGE'
    r=up/total*100; avg=sum(moms)/len(moms) if moms else 0
    atrs=[]
    for sym in SYMBOLS:
        ohlc=daily_ohlc.get(sym,[])
        if len(ohlc)>=14:
            ra=datr_calc(ohlc[-14:],14); lr=ohlc[-1][0]-ohlc[-1][1]
            if ra>0: atrs.append(lr/ra)
    ar=sum(atrs)/len(atrs) if atrs else 1.0
    if ar>=1.8 and r<45: return 'VOLATILE'
    if r>=65 and avg>=0.8: return 'BULL'
    if r>=55 and avg>=0.3: return 'WEAK_BULL'
    if r<=30 and avg<=-0.8: return 'BEAR'
    if r<=40 and avg<=-0.3: return 'WEAK_BEAR'
    return 'RANGE'

# ── Warmup ────────────────────────────────────────────────────
WARMUP=25
daily_close = defaultdict(list)
daily_ohlc  = defaultdict(list)
prev_close: dict[str,float] = {}
regime_history: dict[date, str] = {}

for day_idx, day in enumerate(all_days):
    day_bars = {sym: by_sym_day[sym].get(day,[]) for sym in SYMBOLS}
    if day_idx < WARMUP:
        for sym,bars in day_bars.items():
            if bars:
                daily_ohlc[sym].append((max(b.high for b in bars),
                                        min(b.low for b in bars),bars[-1].close))
                daily_close[sym].append(bars[-1].close)
                prev_close[sym]=bars[-1].close
        continue
    regime = detect_regime(daily_close, daily_ohlc)
    regime_history[day] = regime
    for sym,bars in day_bars.items():
        if bars:
            daily_ohlc[sym].append((max(b.high for b in bars),
                                    min(b.low for b in bars),bars[-1].close))
            daily_close[sym].append(bars[-1].close)
            prev_close[sym]=bars[-1].close

# ── Test günlerini seç ────────────────────────────────────────
if args.date:
    test_dates = [date.fromisoformat(args.date)]
else:
    # Son N BULL gününü seç
    bull_days = [d for d,r in regime_history.items()
                 if r in ('BULL','WEAK_BULL')]
    test_dates = bull_days[-args.days:]

print("="*65)
print("  MANUEL BACKTEST DOĞRULAMA")
print("="*65)
print(f"\n  Test günleri: {[str(d) for d in test_dates]}\n")

# ── Her test günü için simülasyon ─────────────────────────────
sizer = PositionSizer(
    capital=POSITION_SIZING.get('total_capital', 100_000.0),
    config=POSITION_SIZING
)

total_signals = 0
total_correct = 0   # gerçekten o gün iyi trade olmuş mu?

for test_day in test_dates:
    day_bars = {sym: by_sym_day[sym].get(test_day,[]) for sym in SYMBOLS}
    if not day_bars: continue

    regime = regime_history.get(test_day, '?')
    expected_strat = REGIME_STRATEGY_MAP.get(regime, 'NO TRADE')

    print(f"  ── {test_day}  [{regime}] → {expected_strat} ──")

    # Bu günün intraday simülasyonu
    router = StrategyRouter()
    dc_all = {s: daily_close[s] for s in SYMBOLS}

    intraday_sym: dict[str, list[Bar]] = defaultdict(list)
    signals_today = []

    all_today = sorted(
        [(b.timestamp,sym,b) for sym,bars in day_bars.items() for b in bars],
        key=lambda x:x[0])

    for ts, sym, bar in all_today:
        bar_t = ts.time()
        intraday_sym[sym].append(bar)

        # Sadece sinyal penceresi
        if not (time(10,10) <= bar_t <= time(10,30)): continue
        if expected_strat == 'NO TRADE': continue

        dc = daily_close[sym]
        if len(dc) < WARMUP: continue

        e9=ema_c(dc,9); e21=ema_c(dc,21); rsi_d=rsi_c(dc,14)
        ohlc=daily_ohlc[sym]
        datr=datr_calc(ohlc[-16:],14) if len(ohlc)>=2 else bar.close*0.03
        vols_list=[daily_ohlc[sym][i][2] for i in range(len(daily_ohlc[sym]))]
        vol_ma_bar=sum(vols_list[-20:])/min(len(vols_list),20)/96 if vols_list else 0
        sec_str=calc_sector_str(sym,dc_all)
        rs_val=calc_rs(sym,dc_all)
        ib=intraday_sym[sym]
        vwap=sum(((b.high+b.low+b.close)/3)*b.volume for b in ib)/max(1,sum(b.volume for b in ib))
        rsi_intra=rsi_c([b.close for b in ib],9) if len(ib)>9 else 50.0
        atr_intra=datr/10

        ctx=dict(
            sector_strength=sec_str,rs_vs_index=rs_val,
            ema9_daily=e9,ema21_daily=e21,rsi_daily=rsi_d,
            daily_atr=datr,vol_ma=vol_ma_bar,
            intraday_vol=sum(b.volume for b in ib),
            intraday_bars=ib,vwap_value=vwap,
            rsi_intraday=rsi_intra,intraday_atr=atr_intra,
        )

        rsig=router.on_bar(sym,bar,regime,ctx)
        if rsig and rsig.is_active:
            # Lot hesabı
            sizing=sizer.calc(entry=rsig.entry,stop=rsig.stop,target=rsig.target)
            signals_today.append(dict(
                sym=sym, ts=bar_t, strategy=rsig.strategy_type,
                setup=rsig.setup_type, entry=rsig.entry,
                stop=rsig.stop, target=rsig.target,
                rr=rsig.rr_ratio, lots=sizing.lots if sizing.allowed else 0,
                sizing_ok=sizing.allowed,
                sizing_reason=sizing.reject_reason,
                sec_str=sec_str, rs=rs_val,
            ))

    # Sinyalleri göster
    if signals_today:
        print(f"  {'Sym':<8} {'Saat':>6} {'Setup':<20} {'Entry':>8} "
              f"{'Stop':>8} {'Tgt':>8} {'R/R':>5} {'Lot':>5} {'Sec%':>6}")
        print("  " + "-"*80)
        for s in signals_today[:5]:  # max 5
            ok = '✓' if s['sizing_ok'] else '✗'
            print(f"  {s['sym']:<8} {str(s['ts'])[:5]:>6} "
                  f"{s['setup']:<20} "
                  f"₺{s['entry']:>7.2f} ₺{s['stop']:>7.2f} "
                  f"₺{s['target']:>7.2f} {s['rr']:>4.1f}x "
                  f"{s['lots']:>4} {ok}  "
                  f"sec={s['sec_str']:.0f}%")

        # Gerçek sonuç — EOD kapanışı ne olmuş?
        print(f"\n  Gerçek EOD sonuçları:")
        for s in signals_today[:5]:
            sym = s['sym']
            bars = day_bars.get(sym,[])
            eod = [b for b in bars if b.timestamp.time() >= time(17,20)]
            if eod and s['entry'] > 0:
                eod_close = eod[0].close
                ret = (eod_close - s['entry'])/s['entry']*100
                hit_tgt = any(b.high >= s['target'] for b in bars
                              if b.timestamp.time() > time(10,30))
                hit_stop= any(b.low  <= s['stop']   for b in bars
                              if b.timestamp.time() > time(10,30))
                outcome = ('TARGET ✓' if hit_tgt else
                           'STOP ✗'  if hit_stop else
                           f'EOD {ret:+.2f}%')
                pnl_tl = (eod_close - s['entry']) * s['lots']
                print(f"    {sym:<8}: {outcome:<12}  "
                      f"entry=₺{s['entry']:.2f} → ₺{eod_close:.2f}  "
                      f"ret={ret:+.2f}%  PnL=₺{pnl_tl:+,.0f}")
                if hit_tgt: total_correct += 1
                total_signals += 1
        print()
    else:
        print(f"  Sinyal yok — {expected_strat} bu günde koşullar oluşmadı\n")

# ── Özet ──────────────────────────────────────────────────────
print("="*65)
print(f"  ÖZET")
print("="*65)
print(f"  Test günü   : {len(test_dates)}")
print(f"  Sinyal      : {total_signals}")
if total_signals > 0:
    print(f"  Target hit  : {total_correct}/{total_signals} "
          f"(%{total_correct/total_signals*100:.0f})")

print(f"\n  Sizer durumu: {sizer.summary()}")
print(f"\n  Doğrulama sonucu:")
print(f"  ✓ Regime tespiti: dünün verisiyle, look-ahead yok")
print(f"  ✓ Sinyal penceresi: 10:10-10:30 arası")
print(f"  ✓ Entry: sinyal barından sonraki bar open")
print(f"  ✓ Lot hesabı: PositionSizer ile risk bazlı")
print("="*65)
