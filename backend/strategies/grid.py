"""网格交易策略"""
import math
from typing import Optional
from strategies.base import BaseStrategy, Signal, SignalType


class GridLevel:
    def __init__(self, index: int, price: float):
        self.index = index
        self.price = price
        self.has_buy_order = False
        self.has_sell_order = False
        self.buy_order_id: Optional[str] = None
        self.sell_order_id: Optional[str] = None
        self.buy_price: float = 0.0


class GridStrategy(BaseStrategy):
    """网格交易策略"""

    def __init__(self, strategy_id: str, name: str, config: dict):
        super().__init__(strategy_id, name, config)
        lower = config.get("lower_bound")
        upper = config.get("upper_bound")
        if lower is None or upper is None:
            try:
                from core.exchange import shared_exchange
                t = shared_exchange.fetch_ticker(self.symbol)
                p = t.get("last", 86500)
                lower = p * 0.9
                upper = p * 1.1
            except Exception:
                lower = 83000
                upper = 93000
        self.lower = float(lower)
        self.upper = float(upper)
        self.grid_count = int(config.get("grid_count", 20))
        self.order_amount = float(config.get("order_amount", 100))
        self.max_investment = float(config.get("max_investment", 2000))
        self.spacing = (self.upper - self.lower) / self.grid_count
        self.grid_lines = [
            round(self.lower + i * self.spacing, 8)
            for i in range(self.grid_count + 1)
        ]
        self.levels = [GridLevel(i, p) for i, p in enumerate(self.grid_lines)]
        self.total_invested = 0.0
        self.entry_price = 0.0

    def _get_grid_index(self, price: float) -> int:
        for i, line_price in enumerate(self.grid_lines):
            if line_price >= price:
                return max(0, i - 1)
        return len(self.grid_lines) - 2

    async def analyze(self, market_data: dict) -> Optional[Signal]:
        current_price = market_data.get("last", 0)
        if current_price <= 0:
            return None
        if self.entry_price == 0:
            self.entry_price = current_price
        idx = self._get_grid_index(current_price)
        nearest_level = self.levels[idx]
        if current_price > self.upper:
            return Signal(type=SignalType.HOLD, price=current_price, reason="out of range upper")
        if current_price < self.lower:
            return Signal(type=SignalType.HOLD, price=current_price, reason="out of range lower")
        if (
            not nearest_level.has_buy_order
            and not nearest_level.has_sell_order
            and nearest_level.price < current_price
            and self.total_invested + self.order_amount <= self.max_investment
        ):
            qty = self.order_amount / nearest_level.price
            self.total_invested += self.order_amount
            return Signal(
                type=SignalType.BUY,
                price=nearest_level.price,
                confidence=0.8,
                reason=f"grid buy #{idx}",
            )
        return None

