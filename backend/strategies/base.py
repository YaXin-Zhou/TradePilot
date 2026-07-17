"""策略基类"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    STRONG_BUY = "strong_buy"
    STRONG_SELL = "strong_sell"


@dataclass
class Signal:
    type: SignalType
    price: float
    confidence: float = 0.5
    reason: str = ""
    metadata: dict = field(default_factory=dict)


class BaseStrategy:
    """所有策略的基类"""

    def __init__(self, strategy_id: str, name: str, config: dict):
        self.id = strategy_id
        self.name = name
        self.config = config
        self.symbol = config.get("symbol", "BTC/USDT")

    async def analyze(self, market_data: dict) -> Optional[Signal]:
        """分析市场数据，返回交易信号"""
        raise NotImplementedError

    async def on_order_filled(self, order: dict):
        """订单成交回调"""
        pass

    def get_config_snapshot(self) -> dict:
        return self.config
