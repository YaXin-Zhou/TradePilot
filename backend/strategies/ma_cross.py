"""MA 均线交叉策略 — 金叉买入、死叉卖出"""
from strategies.base import BaseStrategy, Signal, SignalType


class MACrossStrategy(BaseStrategy):
    """MA 交叉策略"""

    def __init__(self, symbol: str = "BTC/USDT", fast: int = 7, slow: int = 25, **kw):
        config = {"symbol": symbol, "fast": fast, "slow": slow}
        config.update(kw)
        super().__init__(strategy_id="ma_cross", name="MA Cross", config=config)
        self.fast = int(fast)
        self.slow = int(slow)
        self._price_history: list[float] = []
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    async def analyze(self, market_data: dict) -> Signal | None:
        price = market_data.get("last", 0)
        if price <= 0:
            return None
        self._price_history.append(price)
        if len(self._price_history) > self.slow * 2:
            self._price_history = self._price_history[-self.slow * 2:]
        if len(self._price_history) < self.slow + 1:
            return Signal(type=SignalType.HOLD, price=price, confidence=0.0, reason="warming up")

        fast_ma = sum(self._price_history[-self.fast:]) / self.fast
        slow_ma = sum(self._price_history[-self.slow:]) / self.slow

        if self._prev_fast is not None and self._prev_slow is not None:
            if self._prev_fast <= self._prev_slow and fast_ma > slow_ma:
                signal = Signal(type=SignalType.BUY, price=price, confidence=0.7,
                                reason=f"MA golden cross: fast={fast_ma:.1f} slow={slow_ma:.1f}")
            elif self._prev_fast >= self._prev_slow and fast_ma < slow_ma:
                signal = Signal(type=SignalType.SELL, price=price, confidence=0.7,
                                reason=f"MA death cross: fast={fast_ma:.1f} slow={slow_ma:.1f}")
            else:
                signal = Signal(type=SignalType.HOLD, price=price, confidence=0.0,
                                reason=f"fast={fast_ma:.1f} slow={slow_ma:.1f}")
        else:
            signal = Signal(type=SignalType.HOLD, price=price, confidence=0.0,
                            reason=f"fast={fast_ma:.1f} slow={slow_ma:.1f}")

        self._prev_fast = fast_ma
        self._prev_slow = slow_ma
        return signal
