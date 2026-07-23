"""MA 均线交叉策略（占位 — 待实现完整交叉逻辑）"""
from strategies.base import BaseStrategy, Signal, SignalType


class MACrossStrategy(BaseStrategy):
    """MA 交叉策略"""

    def __init__(self, symbol: str = "BTC/USDT", fast: int = 7, slow: int = 25, **kw):
        config = {"symbol": symbol, "fast": fast, "slow": slow}
        config.update(kw)
        super().__init__(strategy_id="ma_cross", name="MA Cross", config=config)
        self.fast = fast
        self.slow = slow

    async def analyze(self, market_data: dict) -> Signal | None:
        return Signal(type=SignalType.HOLD, price=market_data.get("last", 0),
                      confidence=0.0, reason="MA Cross: not implemented")
