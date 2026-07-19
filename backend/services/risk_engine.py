"""
风控规则引擎 — Regime 绑定风控参数 + 多维度检查

检查链（按顺序）:
  1. Regime 准入 — 当前市场状态是否允许该策略类型
  2. 仓位上限 — 总仓位 + 单策略仓位不超限
  3. 日亏损熔断 — 触达则暂停所有策略
  4. 策略相关性 — 过高则自动降权
  5. 新策略入场门槛 — 最低 Sharpe 要求
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from core.logger import log
from services.regime_detector import MarketRegime

# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------


class StrategyType(str, Enum):
    MA_CROSS = "ma_cross"
    RSI = "rsi"
    BOLLINGER = "bollinger"
    GRID = "grid"
    AI_GENERATED = "ai_generated"


@dataclass
class RiskPolicy:
    """单 Regime 的风控参数"""
    regime: MarketRegime
    max_position_pct: float = 0.3       # 最大仓位占总资金比例
    max_single_strategy_pct: float = 0.15  # 单策略最大仓位
    max_daily_loss_pct: float = 5.0     # 日亏损上限 (%)
    stop_loss_pct: float = 8.0          # 硬止损线 (%)
    trailing_stop_pct: float = 3.0      # 移动止损 (%)
    min_sharpe_entry: float = 0.8       # 新策略最低入场 Sharpe
    max_correlation: float = 0.7        # 策略间最大相关性
    time_stop_hours: int = 72           # 时间止损（小时）
    atr_stop_multiplier: float = 2.0    # ATR 止损倍数
    allowed_strategies: list[str] = field(default_factory=list)  # 空=全部允许

    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "max_position_pct": self.max_position_pct,
            "max_single_strategy_pct": self.max_single_strategy_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "trailing_stop_pct": self.trailing_stop_pct,
            "min_sharpe_entry": self.min_sharpe_entry,
            "max_correlation": self.max_correlation,
            "time_stop_hours": self.time_stop_hours,
            "atr_stop_multiplier": self.atr_stop_multiplier,
            "allowed_strategies": self.allowed_strategies,
        }


@dataclass
class RiskCheckResult:
    passed: bool
    reason: str = ""
    checks: dict = field(default_factory=dict)
    active_policy: Optional[dict] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "checks": self.checks,
            "active_policy": self.active_policy,
            "timestamp": self.timestamp,
        }


# ------------------------------------------------------------------
# 默认策略集 — 每个 Regime 的风控配置
# ------------------------------------------------------------------

DEFAULT_POLICIES: dict[MarketRegime, RiskPolicy] = {
    MarketRegime.TRENDING_UP: RiskPolicy(
        regime=MarketRegime.TRENDING_UP,
        max_position_pct=0.40,
        max_single_strategy_pct=0.20,
        max_daily_loss_pct=5.0,
        stop_loss_pct=8.0,
        trailing_stop_pct=3.0,
        min_sharpe_entry=0.8,
        max_correlation=0.7,
        time_stop_hours=72,
        atr_stop_multiplier=2.0,
        allowed_strategies=[],  # 全部允许
    ),
    MarketRegime.TRENDING_DOWN: RiskPolicy(
        regime=MarketRegime.TRENDING_DOWN,
        max_position_pct=0.15,
        max_single_strategy_pct=0.08,
        max_daily_loss_pct=3.0,
        stop_loss_pct=5.0,
        trailing_stop_pct=2.0,
        min_sharpe_entry=1.0,
        max_correlation=0.6,
        time_stop_hours=48,
        atr_stop_multiplier=1.5,
        allowed_strategies=[StrategyType.RSI.value],
    ),
    MarketRegime.RANGING_HIGH_VOL: RiskPolicy(
        regime=MarketRegime.RANGING_HIGH_VOL,
        max_position_pct=0.20,
        max_single_strategy_pct=0.10,
        max_daily_loss_pct=4.0,
        stop_loss_pct=6.0,
        trailing_stop_pct=2.5,
        min_sharpe_entry=0.7,
        max_correlation=0.6,
        time_stop_hours=48,
        atr_stop_multiplier=2.5,
        allowed_strategies=[StrategyType.BOLLINGER.value, StrategyType.GRID.value],
    ),
    MarketRegime.RANGING_LOW_VOL: RiskPolicy(
        regime=MarketRegime.RANGING_LOW_VOL,
        max_position_pct=0.25,
        max_single_strategy_pct=0.12,
        max_daily_loss_pct=4.0,
        stop_loss_pct=7.0,
        trailing_stop_pct=2.0,
        min_sharpe_entry=0.6,
        max_correlation=0.65,
        time_stop_hours=96,
        atr_stop_multiplier=1.5,
        allowed_strategies=[StrategyType.GRID.value, StrategyType.MA_CROSS.value],
    ),
}

# ------------------------------------------------------------------
# 引擎
# ------------------------------------------------------------------


class RiskEngine:
    """风控规则引擎"""

    POLICIES_FILE = Path(__file__).parent.parent / "data" / "risk_policies.json"

    def __init__(self):
        self._policies: dict[MarketRegime, RiskPolicy] = {}
        self._daily_pnl: dict[str, float] = {}     # user_id → daily PnL
        self._daily_reset: float = time.time()
        self._load_policies()

    # ------------------------------------------------------------------
    # 策略管理
    # ------------------------------------------------------------------

    def get_policy(self, regime: MarketRegime) -> RiskPolicy:
        return self._policies.get(regime, DEFAULT_POLICIES.get(regime,
            RiskPolicy(regime=regime)))

    def update_policy(self, regime: MarketRegime, **kwargs) -> RiskPolicy:
        """更新单 Regime 策略并持久化（创建副本，避免污染默认值）"""
        old = self.get_policy(regime)
        # 从旧策略复制一份，避免修改 DEFAULT_POLICIES 中的对象
        policy = RiskPolicy(regime=regime)
        for field_name in old.__dataclass_fields__:
            if field_name != "regime":
                setattr(policy, field_name, getattr(old, field_name))
        for k, v in kwargs.items():
            if hasattr(policy, k):
                setattr(policy, k, v)
        self._policies[regime] = policy
        self._save_policies()
        log.info(f"RiskEngine: policy updated for {regime.value}")
        return policy

    def get_all_policies(self) -> dict[str, dict]:
        return {r.value: self.get_policy(r).to_dict() for r in MarketRegime}

    def reset_to_defaults(self):
        self._policies = dict(DEFAULT_POLICIES)
        self._save_policies()
        log.info("RiskEngine: policies reset to defaults")

    # ------------------------------------------------------------------
    # 核心检查
    # ------------------------------------------------------------------

    def check_strategy_entry(self, regime: MarketRegime, strategy_type: str,
                             sharpe_oos: float) -> RiskCheckResult:
        """检查新策略是否可以入场"""
        policy = self.get_policy(regime)
        checks = {}

        # 1) Regime 准入
        allowed = policy.allowed_strategies
        checks["regime_allowed"] = not allowed or strategy_type in allowed
        if not checks["regime_allowed"]:
            return RiskCheckResult(
                passed=False,
                reason=f"{strategy_type} not allowed in {regime.value}",
                checks=checks,
                active_policy=policy.to_dict(),
            )

        # 2) 最小 Sharpe
        checks["min_sharpe"] = sharpe_oos >= policy.min_sharpe_entry
        if not checks["min_sharpe"]:
            return RiskCheckResult(
                passed=False,
                reason=f"Sharpe(OOS) {sharpe_oos:.3f} < min {policy.min_sharpe_entry}",
                checks=checks,
                active_policy=policy.to_dict(),
            )

        return RiskCheckResult(passed=True, checks=checks, active_policy=policy.to_dict())

    def check_position_limit(self, regime: MarketRegime, total_capital: float,
                             current_position: float, new_amount: float,
                             strategy_position: float = 0) -> RiskCheckResult:
        """检查仓位是否超限"""
        policy = self.get_policy(regime)
        checks = {}

        new_total = current_position + new_amount
        checks["total_position"] = new_total <= total_capital * policy.max_position_pct
        if not checks["total_position"]:
            return RiskCheckResult(
                passed=False,
                reason=f"Total position {new_total:.0f} exceeds "
                       f"{total_capital * policy.max_position_pct:.0f}",
                checks=checks,
                active_policy=policy.to_dict(),
            )

        checks["single_strategy"] = (strategy_position + new_amount) <= \
                                     total_capital * policy.max_single_strategy_pct
        if not checks["single_strategy"]:
            return RiskCheckResult(
                passed=False,
                reason=f"Strategy position exceeds single-strategy limit",
                checks=checks,
                active_policy=policy.to_dict(),
            )

        return RiskCheckResult(passed=True, checks=checks, active_policy=policy.to_dict())

    def check_daily_loss(self, user_id: str, daily_pnl: float,
                         total_capital: float, regime: MarketRegime) -> RiskCheckResult:
        """检查日亏损是否熔断"""
        policy = self.get_policy(regime)
        checks = {}

        loss_pct = abs(daily_pnl) / total_capital * 100 if daily_pnl < 0 and total_capital > 0 else 0
        checks["daily_loss"] = loss_pct < policy.max_daily_loss_pct

        if not checks["daily_loss"]:
            return RiskCheckResult(
                passed=False,
                reason=f"Daily loss {loss_pct:.1f}% exceeds limit {policy.max_daily_loss_pct}%",
                checks=checks,
                active_policy=policy.to_dict(),
            )

        return RiskCheckResult(passed=True, checks=checks, active_policy=policy.to_dict())

    def check_correlation(self, strategy_returns: list[float],
                          pool_returns: dict[str, list[float]],
                          regime: MarketRegime) -> RiskCheckResult:
        """检查策略与池中其他策略的相关性"""
        policy = self.get_policy(regime)
        checks = {}

        if not pool_returns:
            return RiskCheckResult(passed=True, checks={"correlation": "empty_pool"},
                                   active_policy=policy.to_dict())

        corr = self._max_correlation(strategy_returns, pool_returns)
        checks["correlation"] = corr
        checks["max_correlation"] = corr < policy.max_correlation

        if not checks["max_correlation"]:
            return RiskCheckResult(
                passed=False,
                reason=f"Max correlation {corr:.3f} exceeds {policy.max_correlation}",
                checks=checks,
                active_policy=policy.to_dict(),
            )

        return RiskCheckResult(passed=True, checks=checks, active_policy=policy.to_dict())

    def full_check(self, regime: MarketRegime, strategy_type: str,
                   sharpe_oos: float, total_capital: float,
                   current_position: float, new_amount: float,
                   strategy_position: float, daily_pnl: float,
                   user_id: str, strategy_returns: Optional[list[float]] = None,
                   pool_returns: Optional[dict[str, list[float]]] = None
                   ) -> RiskCheckResult:
        """全链路风控检查（按顺序，任一不通过即返回）"""
        # 1) 入场准入
        r = self.check_strategy_entry(regime, strategy_type, sharpe_oos)
        if not r.passed:
            return r

        # 2) 仓位
        r = self.check_position_limit(regime, total_capital, current_position,
                                      new_amount, strategy_position)
        if not r.passed:
            return r

        # 3) 日亏损
        r = self.check_daily_loss(user_id, daily_pnl, total_capital, regime)
        if not r.passed:
            return r

        # 4) 相关性（可选）
        if strategy_returns and pool_returns:
            r = self.check_correlation(strategy_returns, pool_returns, regime)
            if not r.passed:
                return r

        policy = self.get_policy(regime)
        return RiskCheckResult(passed=True, reason="All checks passed",
                               checks={"all": True}, active_policy=policy.to_dict())

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _pearson_corr(x: list[float], y: list[float]) -> float:
        n = min(len(x), len(y))
        if n < 3:
            return 0.0
        mx = sum(x[:n]) / n
        my = sum(y[:n]) / n
        num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
        dx = math.sqrt(sum((xi - mx) ** 2 for xi in x[:n]))
        dy = math.sqrt(sum((yi - my) ** 2 for yi in y[:n]))
        return num / (dx * dy) if dx and dy else 0.0

    def _max_correlation(self, strat_ret: list[float],
                         pool: dict[str, list[float]]) -> float:
        if not pool:
            return 0.0
        return max(abs(self._pearson_corr(strat_ret, r)) for r in pool.values())

    def _load_policies(self):
        try:
            if self.POLICIES_FILE.exists():
                raw = json.loads(self.POLICIES_FILE.read_text(encoding="utf-8"))
                for key, data in raw.items():
                    try:
                        regime = MarketRegime(key)
                        self._policies[regime] = RiskPolicy(regime=regime, **data)
                    except (ValueError, TypeError):
                        pass
                log.info(f"RiskEngine: loaded {len(self._policies)} policy overrides")
        except Exception as e:
            log.warning(f"RiskEngine: failed to load policies ({e}), using defaults")

        # 填充默认值
        for regime in MarketRegime:
            if regime not in self._policies:
                self._policies[regime] = DEFAULT_POLICIES[regime]

    def _save_policies(self):
        try:
            self.POLICIES_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {r.value: p.to_dict() for r, p in self._policies.items()
                    if r in MarketRegime}
            self.POLICIES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            log.error(f"RiskEngine: failed to save policies: {e}")


# 全局单例
risk_engine = RiskEngine()
