# ============================================================
# portfolio/portfolio_engine.py — Portföy Takip Motoru
# ============================================================
from config import PORTFOLIO
from data.models import PortfolioPosition, MarketSnapshot


class PortfolioEngine:
    def __init__(self, initial_cash: float | None = None):
        self._cash = initial_cash or PORTFOLIO["initial_cash"]
        self._positions: dict[str, PortfolioPosition] = {}

    def update_prices(self, snapshot: MarketSnapshot) -> None:
        for symbol, pos in self._positions.items():
            tick = snapshot.ticks.get(symbol)
            if tick:
                pos.current_price = tick.price

    def open_position(self, symbol: str, quantity: float, price: float) -> bool:
        cost = quantity * price
        if cost > self._cash:
            return False
        self._cash -= cost
        if symbol in self._positions:
            existing = self._positions[symbol]
            total_qty = existing.quantity + quantity
            avg = (existing.avg_cost * existing.quantity + price * quantity) / total_qty
            existing.quantity = total_qty
            existing.avg_cost = round(avg, 2)
        else:
            self._positions[symbol] = PortfolioPosition(
                symbol=symbol, quantity=quantity, avg_cost=price, current_price=price
            )
        return True

    def close_position(self, symbol: str) -> bool:
        if symbol not in self._positions:
            return False
        pos = self._positions.pop(symbol)
        self._cash += pos.quantity * pos.current_price
        return True

    @property
    def cash(self) -> float:
        return round(self._cash, 2)

    @property
    def positions(self) -> list[PortfolioPosition]:
        return list(self._positions.values())

    @property
    def total_pnl(self) -> float:
        return round(sum(p.pnl for p in self._positions.values()), 2)

    @property
    def total_value(self) -> float:
        equity = sum(p.quantity * p.current_price for p in self._positions.values())
        return round(self._cash + equity, 2)
