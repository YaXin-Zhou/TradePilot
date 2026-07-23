"""RSI 策略 — 基于相对强弱指标的超买超卖信号"""
import numpy as np
from strategies.base import BaseStrategy, Signal, SignalType
from core.logger import log


def _calc_rsi(closes: list[float], period: int = 14) -> float:
    """计算 RSI"""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class RSIStrategy(BaseStrategy):
    """RSI 策略：RSI < oversold → 买入，RSI > overbought → 卖出"""

    def __init__(self, symbol: str = "BTC/USDT", period: int = 14,
                 oversold: int = 30, overbought: int = 70,
                 **kwargs):
        # 兼容旧版 config key 命名（rsi_period / oversold_threshold / overbought_threshold）
        p = kwargs.get("rsi_period")
        if p:
            period = int(p)
        o1 = kwargs.get("oversold_threshold")
        if o1:
            oversold = int(o1)
        o2 = kwargs.get("overbought_threshold")
        if o2:
            overbought = int(o2)

        config = {"symbol": symbol, "period": period,
                   "oversold": oversold, "overbought": overbought}
        config.update(kwargs)
        super().__init__(strategy_id="rsi", name="RSI", config=config)
        self._period = period
        self._oversold = oversold
        self._overbought = overbought
        self._price_history: list[float] = []

    async def analyze(self, market_data: dict) -> Signal | None:
        price = market_data.get("last", 0)
        if price <= 0:
            return None
        self._price_history.append(price)
        if len(self._price_history) > self._period * 2:
            self._price_history = self._price_history[-self._period * 2:]

        rsi = _calc_rsi(self._price_history, self._period)

        if rsi < self._oversold:
            return Signal(type=SignalType.BUY, price=price,
                          confidence=min(1.0, (self._oversold - rsi) / 20),
                          reason=f"RSI={rsi:.1f} < {self._oversold} (oversold)")
        elif rsi > self._overbought:
            return Signal(type=SignalType.SELL, price=price,
                          confidence=min(1.0, (rsi - self._overbought) / 20),
                          reason=f"RSI={rsi:.1f} > {self._overbought} (overbought)")
        return Signal(type=SignalType.HOLD, price=price,
                      confidence=0.0, reason=f"RSI={rsi:.1f}")
