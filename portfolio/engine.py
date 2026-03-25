# ============================================================
# portfolio/engine.py — BIST v2 Akıllı Portföy Motoru
# ============================================================
import logging
from dataclasses import dataclass
from datetime import datetime
from config import CAPITAL_TL, MAX_POSITIONS

logger = logging.getLogger(__name__)

@dataclass
class Position:
    symbol: str
    setup: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    current_price: float
    highest_price: float
    entry_time: datetime

class PortfolioEngine:
    def __init__(self):
        self.cash = CAPITAL_TL
        self.max_positions = MAX_POSITIONS
        self.positions: dict[str, Position] = {}
        self.closed_trades: list[dict] = []
        logger.info(f"Portfoy Motoru baslatildi — Kasa: ₺{self.cash:,.2f}, Maksimum Pozisyon: {self.max_positions}")

    @property
    def free_slots(self) -> int:
        return self.max_positions - len(self.positions)

    def update_prices(self, snapshot) -> None:
        """Her piyasa guncellemesinde acik pozisyonlarin anlik fiyatini ve İzleyen Stop'unu gunceller."""
        for symbol, pos in self.positions.items():
            if snapshot and hasattr(snapshot, "ticks") and symbol in snapshot.ticks:
                tick = snapshot.ticks[symbol]
                price = getattr(tick, "price", pos.current_price)
                if price and price > 0:
                    pos.current_price = price
                    
                    # İzleyen Stop (Trailing Stop) Mantığı:
                    # Fiyat yeni bir zirve yaparsa, stop noktasını aradaki mesafe kadar yukarı çek
                    if price > pos.highest_price:
                        pos.highest_price = price
                        
                        # Giriş fiyatı ile stop arasındaki orijinal mesafeyi koru
                        trail_distance = pos.entry_price - pos.stop_loss
                        if trail_distance > 0:
                            new_stop = pos.highest_price - trail_distance
                            if new_stop > pos.stop_loss:
                                pos.stop_loss = new_stop

    def update_from_bar(self, symbol: str, high: float, low: float, close: float) -> list[str]:
        """Backtest için özel güncelleme. High ile zirveyi bulur, Trailing Stop'u yukarı taşır.
        Eğer gün içinde Low stop'u patlatırsa veya High target'i vurursa sebebiyle döner."""
        reasons = []
        if symbol in self.positions:
            pos = self.positions[symbol]
            
            # Önce hedef vuruldu mu diye kontrol et (gap up senaryosu)
            if high >= pos.take_profit:
                reasons.append(f"KAR AL: ₺{pos.take_profit:.2f}")
                pos.current_price = pos.take_profit
                return reasons
                
            # Stop vuruldu mu diye kontrol et
            if low <= pos.stop_loss:
                reasons.append(f"STOP LOSS (İzleyen): ₺{pos.stop_loss:.2f}")
                pos.current_price = pos.stop_loss
                return reasons
            
            # Gün içi stop/hedef vurulmadıysa, trailing stop'u High ile güncelle
            if high > pos.highest_price:
                pos.highest_price = high
                trail_distance = pos.entry_price - pos.stop_loss
                if trail_distance > 0:
                    new_stop = pos.highest_price - trail_distance
                    if new_stop > pos.stop_loss:
                        pos.stop_loss = new_stop
                        
            # Kapanış fiyatını son fiyat olarak kaydet
            pos.current_price = close
            
        return reasons

    def open_position(self, sig) -> bool:
        """Yeni bir AL sinyali geldiğinde portföy kurallarını (Bakiye, Yer) kontrol edip sanal alım yapar."""
        if self.free_slots <= 0:
            return False
        if sig.symbol in self.positions:
            return False # Zaten portföyde var
            
        # Dinamik Bütçe: Mevcut Toplam Portföy Değeri / 5
        total_equity = self.cash + sum((p.quantity * p.current_price) for p in self.positions.values())
        alloc = total_equity / self.max_positions
        if self.cash < alloc * 0.9: # Tolerans
            return False
            
        qty = int(alloc / sig.entry)
        if qty <= 0:
            return False
            
        cost = qty * sig.entry
        self.cash -= cost
        
        pos = Position(
            symbol=sig.symbol,
            setup=str(getattr(sig, "setup_type", "Signal")),
            entry_price=sig.entry,
            quantity=float(qty),
            stop_loss=sig.stop,
            take_profit=sig.target,
            current_price=sig.entry,
            highest_price=sig.entry,
            entry_time=datetime.now()
        )
        self.positions[sig.symbol] = pos
        logger.info(f"PORTFOY ALIMI: {sig.symbol} | Fiyat: ₺{sig.entry} | Adet: {qty} | Kalan Kasa: ₺{self.cash:,.2f}")
        return True

    def check_exits(self, news_engine=None) -> list[tuple[str, str]]:
        """Pozisyonlari Stop-Loss, Take-Profit ve Acil Kötü Haber acisindan kontrol eder. SAT sinyallerini dondurur."""
        sells = []
        to_remove = []
        
        for symbol, pos in self.positions.items():
            reason = ""
            
            # Acil Kötü Haber Çıkışı
            if news_engine and news_engine.has_negative_news(symbol):
                reason = "PANİK SATIŞI (Çok Kötü Haber Saptandı!)"
            elif pos.current_price <= pos.stop_loss:
                reason = f"STOP LOSS (veya İzleyen Stop) Tetiklendi! Fiyat: ₺{pos.current_price:.2f} <= Stop: ₺{pos.stop_loss:.2f}"
            elif pos.current_price >= pos.take_profit:
                reason = f"KAR AL (Target) Hedefine Ulaşıldı! Fiyat: ₺{pos.current_price:.2f} >= Hedef: ₺{pos.take_profit:.2f}"
                
            if reason:
                sells.append((symbol, reason))
                to_remove.append(symbol)
                
        # Sinyal tespit edilenleri portföyden çıkarıp bakiyeyi güncelle
        for sym in to_remove:
            self._close(sym, reason=next(r for s, r in sells if s == sym))
            
        return sells

    def _close(self, symbol: str, exit_time: datetime = None, reason: str = ""):
        pos = self.positions.pop(symbol, None)
        if pos:
            revenue = pos.quantity * pos.current_price
            cost = pos.quantity * pos.entry_price
            profit = revenue - cost
            self.cash += revenue
            
            self.closed_trades.append({
                'symbol': symbol,
                'setup': pos.setup,
                'entry': pos.entry_price,
                'exit': pos.current_price,
                'pnl': profit,
                'pnl_pct': (profit / cost * 100) if cost > 0 else 0,
                'reason': reason,
                'entry_time': pos.entry_time,
                'exit_time': exit_time or datetime.now()
            })
            logger.info(f"PORTFOY SATISI: {symbol} | Fiyat: ₺{pos.current_price} | Kar/Zarar: ₺{profit:,.2f} | Yeni Kasa: ₺{self.cash:,.2f}")
