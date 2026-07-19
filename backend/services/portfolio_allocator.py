"""
组合资金分配器 — 权重×总资金 → 各策略下单额度 + 再平衡

功能:
  - 单次分配: 权重 × (总资金 × 配置的仓位比例)
  - 再平衡检查: 实际仓位偏离目标超过 5% → 触发渐进式再平衡
  - 最大分配上限: 不超过 RiskPolicy.max_single_strategy_pct
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from core.logger import log
from services.regime_detector import MarketRegime
from services.risk_engine import risk_engine


@dataclass
class Allocation:
    strategy_id: str
    target_capital: float       # 目标资金
    current_capital: float      # 当前已分配
    weight: float               # 权重
    deviation_pct: float        # 偏差 (%)
    action: str                 # "hold" / "buy" / "sell"
    amount: float               # 调整金额（正=买入, 负=卖出）

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "target_capital": round(self.target_capital, 2),
            "current_capital": round(self.current_capital, 2),
            "weight": round(self.weight, 4),
            "deviation_pct": round(self.deviation_pct, 2),
            "action": self.action,
            "amount": round(self.amount, 2),
        }


@dataclass
class AllocationPlan:
    allocations: list[Allocation]
    total_capital: float
    allocated_capital: float
    reserve_capital: float          # 未分配保留金
    needs_rebalance: bool
    regime: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "allocations": [a.to_dict() for a in self.allocations],
            "total_capital": round(self.total_capital, 2),
            "allocated_capital": round(self.allocated_capital, 2),
            "reserve_capital": round(self.reserve_capital, 2),
            "needs_rebalance": self.needs_rebalance,
            "regime": self.regime,
            "timestamp": self.timestamp,
        }


class PortfolioAllocator:
    """组合资金分配器"""

    REBALANCE_THRESHOLD: float = 5.0   # 偏差 5% 触发再平衡
    REBALANCE_SPEED: float = 0.5       # 渐进式：每次只调整偏差的 50%

    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # 分配计算
    # ------------------------------------------------------------------

    def allocate(self, weights: dict[str, float],
                 total_capital: float,
                 current_positions: dict[str, float],
                 regime: MarketRegime | str = MarketRegime.RANGING_LOW_VOL,
                 ) -> AllocationPlan:
        """
        根据权重分配资金。

        Args:
          weights: {strategy_id: weight}  权重总和应为 1.0
          total_capital: 总可用资金
          current_positions: {strategy_id: current_allocated_capital}
          regime: 当前市场状态

        Returns:
          AllocationPlan with per-strategy allocations
        """
        if isinstance(regime, str):
            try:
                regime = MarketRegime(regime)
            except ValueError:
                regime = MarketRegime.RANGING_LOW_VOL

        policy = risk_engine.get_policy(regime)
        max_single = total_capital * policy.max_single_strategy_pct

        allocations: list[Allocation] = []
        total_allocated = 0.0
        needs_rebalance = False

        for sid, weight in weights.items():
            if weight <= 0:
                continue

            target = min(total_capital * weight, max_single)
            current = current_positions.get(sid, 0.0)
            deviation = ((current - target) / target * 100) if target > 0 else 0.0

            if abs(deviation) > self.REBALANCE_THRESHOLD:
                needs_rebalance = True

            # 渐进式调整：只调整偏差的 50%
            if abs(deviation) > 1.0:
                adj_amount = (target - current) * self.REBALANCE_SPEED
                action = "buy" if adj_amount > 0 else "sell"
            else:
                adj_amount = 0.0
                action = "hold"

            allocations.append(Allocation(
                strategy_id=sid,
                target_capital=target,
                current_capital=current,
                weight=weight,
                deviation_pct=deviation,
                action=action,
                amount=adj_amount,
            ))
            total_allocated += target

        reserve = total_capital - total_allocated

        plan = AllocationPlan(
            allocations=allocations,
            total_capital=total_capital,
            allocated_capital=total_allocated,
            reserve_capital=max(0, reserve),
            needs_rebalance=needs_rebalance,
            regime=regime.value,
        )

        log.info(f"PortfolioAllocator: allocated {total_allocated:.0f}/{total_capital:.0f} "
                 f"across {len(allocations)} strategies, rebalance={needs_rebalance}")
        return plan

    # ------------------------------------------------------------------
    # 再平衡
    # ------------------------------------------------------------------

    def rebalance(self, weights: dict[str, float],
                  total_capital: float,
                  current_positions: dict[str, float],
                  regime: MarketRegime | str = MarketRegime.RANGING_LOW_VOL,
                  ) -> AllocationPlan:
        """
        全量再平衡（适用于定时任务触发）。
        与 allocate 的区别：不使用渐进式，直接计算全额调整。
        """
        if isinstance(regime, str):
            try:
                regime = MarketRegime(regime)
            except ValueError:
                regime = MarketRegime.RANGING_LOW_VOL

        policy = risk_engine.get_policy(regime)
        max_single = total_capital * policy.max_single_strategy_pct

        allocations: list[Allocation] = []
        total_allocated = 0.0

        for sid, weight in weights.items():
            if weight <= 0:
                continue

            target = min(total_capital * weight, max_single)
            current = current_positions.get(sid, 0.0)
            deviation = ((current - target) / target * 100) if target > 0 else 0.0

            # 全量调整
            adj_amount = target - current
            if abs(adj_amount) < 1.0:
                action = "hold"
                adj_amount = 0.0
            else:
                action = "buy" if adj_amount > 0 else "sell"

            allocations.append(Allocation(
                strategy_id=sid,
                target_capital=target,
                current_capital=current,
                weight=weight,
                deviation_pct=deviation,
                action=action,
                amount=adj_amount,
            ))
            total_allocated += target

        plan = AllocationPlan(
            allocations=allocations,
            total_capital=total_capital,
            allocated_capital=total_allocated,
            reserve_capital=max(0, total_capital - total_allocated),
            needs_rebalance=True,
            regime=regime.value,
        )

        log.info(f"PortfolioAllocator: full rebalance {total_allocated:.0f}/{total_capital:.0f}")
        return plan


# 全局单例
portfolio_allocator = PortfolioAllocator()
