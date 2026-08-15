"""布林带策略 — 触及下轨买入、上轨卖出"""
import statistics
from strategies.base import BaseStrategy, Signal, SignalType


class BollingerStrategy(BaseStrategy):
    """布林带策略"""

    def __init__(self, symbol: str = "BTC/USDT", period: int = 20, std: float = 2.0, **kw):
        config = {"symbol": symbol, "period": period, "std": std}
        config.update(kw)
        super().__init__(strategy_id="bollinger", name="Bollinger", config=config)
        self.period = int(period)
        self.std = float(std)
        self._price_history: list[float] = []

    async def analyze(self, market_data: dict) -> Signal | None:
        price = market_data.get("last", 0)
        if price <= 0:
            return None
        self._price_history.append(price)
        if len(self._price_history) > self.period * 3:
            self._price_history = self._price_history[-self.period * 3:]
        if len(self._price_history) < self.period:
            return Signal(type=SignalType.HOLD, price=price, confidence=0.0, reason="warming up")

        window = self._price_history[-self.period:]
        sma = sum(window) / self.period
        sd = statistics.stdev(window)
        upper = sma + self.std * sd
        lower = sma - self.std * sd

        if price <= lower:
            return Signal(type=SignalType.BUY, price=price, confidence=0.7,
                          reason=f"price {price:.1f} <= lower band {lower:.1f}")
        elif price >= upper:
            return Signal(type=SignalType.SELL, price=price, confidence=0.7,
                          reason=f"price {price:.1f} >= upper band {upper:.1f}")
        return Signal(type=SignalType.HOLD, price=price, confidence=0.0,
                      reason=f"mid band: {sma:.1f} [{lower:.1f}, {upper:.1f}]")
