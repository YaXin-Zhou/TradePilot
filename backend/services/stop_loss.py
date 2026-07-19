"""
止损管理器 — 硬止损 / 移动止损 / 时间止损 / ATR 波动率止损

使用方式:
  manager = StopLossManager(policy)
  manager.update_price(current_price)   # 每 tick 调用
  should_exit, reason = manager.check()  # 检查是否触发
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from core.logger import log


class StopReason(str, Enum):
    HARD_STOP = "hard_stop"           # 硬止损
    TRAILING_STOP = "trailing_stop"   # 移动止损
    TIME_STOP = "time_stop"           # 时间止损
    ATR_STOP = "atr_stop"             # 波动率止损
    NONE = "none"


@dataclass
class StopLossConfig:
    """止损配置"""
    hard_stop_pct: float = 8.0         # 硬止损线 (%)
    trailing_stop_pct: float = 3.0     # 移动止损 (%)
    time_stop_hours: int = 72          # 时间止损 (小时)
    atr_multiplier: float = 2.0        # ATR 止损倍数

    @classmethod
    def from_policy(cls, policy) -> StopLossConfig:
        from services.risk_engine import RiskPolicy
        if isinstance(policy, RiskPolicy):
            return cls(
                hard_stop_pct=policy.stop_loss_pct,
                trailing_stop_pct=policy.trailing_stop_pct,
                time_stop_hours=policy.time_stop_hours,
                atr_multiplier=policy.atr_stop_multiplier,
            )
        return cls()


@dataclass
class StopLossResult:
    triggered: bool
    reason: StopReason = StopReason.NONE
    stop_price: float = 0.0
    current_price: float = 0.0
    entry_price: float = 0.0
    loss_pct: float = 0.0
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "triggered": self.triggered,
            "reason": self.reason.value,
            "stop_price": self.stop_price,
            "current_price": self.current_price,
            "entry_price": self.entry_price,
            "loss_pct": round(self.loss_pct, 4),
            "message": self.message,
        }


class StopLossManager:
    """止损状态机"""

    def __init__(self, config: StopLossConfig, entry_price: float,
                 entry_time: Optional[float] = None, atr_value: Optional[float] = None):
        self.config = config
        self.entry_price: float = entry_price
        self.entry_time: float = entry_time or time.time()
        self.atr_value: Optional[float] = atr_value
        self.highest_price: float = entry_price     # 多头用最高价
        self.lowest_price: float = entry_price       # 空头用最低价
        self.current_price: float = entry_price
        self.side: str = "long"                      # long / short
        self._triggered: bool = False
        self._trigger_reason: StopReason = StopReason.NONE

    def set_side(self, side: str):
        """设置持仓方向: long / short"""
        self.side = side

    def set_atr(self, atr_value: float):
        self.atr_value = atr_value

    def update_price(self, price: float):
        """更新当前价格，维护追踪极值"""
        self.current_price = price
        if self.side == "long":
            self.highest_price = max(self.highest_price, price)
        else:
            self.lowest_price = min(self.lowest_price, price)

    def check(self) -> StopLossResult:
        """检查全部止损条件，返回最先触发的那个"""
        if self._triggered:
            return StopLossResult(
                triggered=True, reason=self._trigger_reason,
                stop_price=self._stop_price_for_reason(self._trigger_reason),
                current_price=self.current_price, entry_price=self.entry_price,
                loss_pct=self._calc_loss_pct(),
                message=f"Already triggered: {self._trigger_reason.value}",
            )

        # 按优先级检查: 硬止损 > ATR止损 > 移动止损 > 时间止损
        for check_fn, reason in [
            (self._check_hard_stop, StopReason.HARD_STOP),
            (self._check_atr_stop, StopReason.ATR_STOP),
            (self._check_trailing_stop, StopReason.TRAILING_STOP),
            (self._check_time_stop, StopReason.TIME_STOP),
        ]:
            result = check_fn()
            if result is not None:
                self._triggered = True
                self._trigger_reason = reason
                log.warning(f"StopLoss triggered: {reason.value} "
                            f"loss={self._calc_loss_pct():.2f}% price={self.current_price:.2f}")
                return result

        return StopLossResult(
            triggered=False, reason=StopReason.NONE,
            current_price=self.current_price, entry_price=self.entry_price,
        )

    def reset(self, entry_price: float, entry_time: Optional[float] = None):
        """重置止损（新开仓时调用）"""
        self.entry_price = entry_price
        self.entry_time = entry_time or time.time()
        self.highest_price = entry_price
        self.lowest_price = entry_price
        self.current_price = entry_price
        self._triggered = False
        self._trigger_reason = StopReason.NONE

    # ------------------------------------------------------------------
    # 四种止损检查
    # ------------------------------------------------------------------

    def _check_hard_stop(self) -> Optional[StopLossResult]:
        """硬止损：固定百分比"""
        loss_pct = self._calc_loss_pct()
        if loss_pct >= self.config.hard_stop_pct:
            return StopLossResult(
                triggered=True, reason=StopReason.HARD_STOP,
                stop_price=self.entry_price * (1 - self.config.hard_stop_pct / 100),
                current_price=self.current_price, entry_price=self.entry_price,
                loss_pct=loss_pct,
                message=f"Hard stop: {loss_pct:.2f}% >= {self.config.hard_stop_pct}%",
            )
        return None

    def _check_trailing_stop(self) -> Optional[StopLossResult]:
        """移动止损：从极值回撤 N%"""
        if self.side == "long":
            stop_price = self.highest_price * (1 - self.config.trailing_stop_pct / 100)
            if self.current_price <= stop_price:
                drawdown = (self.highest_price - self.current_price) / self.highest_price * 100
                return StopLossResult(
                    triggered=True, reason=StopReason.TRAILING_STOP,
                    stop_price=stop_price, current_price=self.current_price,
                    entry_price=self.entry_price,
                    loss_pct=self._calc_loss_pct(),
                    message=f"Trailing stop: drawdown {drawdown:.2f}% from high {self.highest_price:.2f}",
                )
        else:
            stop_price = self.lowest_price * (1 + self.config.trailing_stop_pct / 100)
            if self.current_price >= stop_price:
                return StopLossResult(
                    triggered=True, reason=StopReason.TRAILING_STOP,
                    stop_price=stop_price, current_price=self.current_price,
                    entry_price=self.entry_price,
                    loss_pct=self._calc_loss_pct(),
                    message=f"Trailing stop (short): rallied from low {self.lowest_price:.2f}",
                )
        return None

    def _check_time_stop(self) -> Optional[StopLossResult]:
        """时间止损：持仓超时未盈利"""
        elapsed_hours = (time.time() - self.entry_time) / 3600
        if elapsed_hours >= self.config.time_stop_hours:
            loss_pct = self._calc_loss_pct()
            if loss_pct > 0:  # 亏损才触发
                return StopLossResult(
                    triggered=True, reason=StopReason.TIME_STOP,
                    stop_price=self.current_price, current_price=self.current_price,
                    entry_price=self.entry_price, loss_pct=loss_pct,
                    message=f"Time stop: held {elapsed_hours:.1f}h with loss {loss_pct:.2f}%",
                )
        return None

    def _check_atr_stop(self) -> Optional[StopLossResult]:
        """ATR 波动率止损"""
        if self.atr_value is None or self.atr_value <= 0:
            return None
        stop_distance = self.atr_value * self.config.atr_multiplier
        if self.side == "long":
            stop_price = self.entry_price - stop_distance
            if self.current_price <= stop_price:
                return StopLossResult(
                    triggered=True, reason=StopReason.ATR_STOP,
                    stop_price=stop_price, current_price=self.current_price,
                    entry_price=self.entry_price, loss_pct=self._calc_loss_pct(),
                    message=f"ATR stop: {stop_distance:.2f} distance ({self.config.atr_multiplier}x ATR)",
                )
        return None

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _calc_loss_pct(self) -> float:
        if self.side == "long":
            return (self.entry_price - self.current_price) / self.entry_price * 100
        else:
            return (self.current_price - self.entry_price) / self.entry_price * 100

    def _stop_price_for_reason(self, reason: StopReason) -> float:
        if reason == StopReason.HARD_STOP:
            return self.entry_price * (1 - self.config.hard_stop_pct / 100)
        elif reason == StopReason.TRAILING_STOP:
            return self.highest_price * (1 - self.config.trailing_stop_pct / 100)
        elif reason == StopReason.ATR_STOP and self.atr_value:
            return self.entry_price - self.atr_value * self.config.atr_multiplier
        return self.current_price
