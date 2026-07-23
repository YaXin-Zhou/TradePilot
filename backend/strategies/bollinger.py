"""布林带策略（占位 — 待实现完整逻辑）"""
from strategies.base import BaseStrategy, Signal, SignalType


class BollingerStrategy(BaseStrategy):
    """布林带策略"""

    def __init__(self, symbol: str = "BTC/USDT", period: int = 20, std: float = 2.0, **kw):
        config = {"symbol": symbol, "period": period, "std": std}
        config.update(kw)
        super().__init__(strategy_id="bollinger", name="Bollinger", config=config)

    async def analyze(self, market_data: dict) -> Signal | None:
        return Signal(type=SignalType.HOLD, price=market_data.get("last", 0),
                      confidence=0.0, reason="Bollinger: not implemented")
