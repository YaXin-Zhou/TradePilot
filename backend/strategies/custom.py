"""自定义策略 - 基于 JSON 规则引擎"""
from typing import Optional
from strategies.base import BaseStrategy, Signal, SignalType


class CustomStrategy(BaseStrategy):
    def __init__(self, strategy_id: str, name: str, config: dict):
        super().__init__(strategy_id, name, config)
        self.rules = config.get("rules", [])

    async def analyze(self, market_data: dict) -> Optional[Signal]:
        price = market_data.get("last", 0)
        ind = market_data.get("indicators", {})
        for rule in self.rules:
            k, op, v, sig = rule.get("indicator"), rule.get("op"), rule.get("value"), rule.get("signal", "hold")
            iv = ind.get(k) if k else None
            if iv is None:
                continue
            ops = {"<": lambda a, b: a < b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b}
            if ops.get(op, lambda a, b: False)(iv, v):
                st = SignalType[sig.upper()] if sig.upper() in SignalType.__members__ else SignalType.HOLD
                return Signal(type=st, price=price, reason=f"{k}{op}{v}")
        return None
