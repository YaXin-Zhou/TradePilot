"""
在线学习权重分配 — Adaptive Fixed-Share Hedge + Sleeping Experts

算法:
  1. 损失函数归一化（每个策略的损失映射到 [0,1]）
  2. η 学习率自适应（根据最近 N 个周期表现动态调整）
  3. 族内聚合（同类型策略先加权平均），族间 Hedge（族间用指数加权）
  4. Sleeping Experts：Regime 不适配时自动休眠（weight → min_weight）

P1-3: JSON 文件持久化迁入 DB（OnlineLearnerStateRecord），
      内存为读源 + fire-and-forget 异步 DB 写，调度器定期 refresh。
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.logger import log


@dataclass
class ExpertState:
    """单个 Expert 的学习状态"""
    strategy_id: str
    strategy_type: str
    weight: float = 0.0            # 当前权重
    cumulative_loss: float = 0.0   # 累积损失
    recent_losses: list[float] = field(default_factory=list)  # 最近 N 周期损失
    is_sleeping: bool = False

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_type": self.strategy_type,
            "weight": round(self.weight, 4),
            "cumulative_loss": round(self.cumulative_loss, 4),
            "is_sleeping": self.is_sleeping,
        }


@dataclass
class LearnerResult:
    weights: dict[str, float]       # strategy_id → weight
    sleeping: list[str]             # 休眠的 strategy_id
    learning_rate: float
    iteration: int

    def to_dict(self) -> dict:
        return {
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "sleeping": self.sleeping,
            "learning_rate": round(self.learning_rate, 4),
            "iteration": self.iteration,
        }


class OnlineLearner:
    """
    Adaptive Fixed-Share Hedge 在线学习器

    用法:
      learner = OnlineLearner()
      # 每周期:
      result = learner.update({
          "s1": -0.02,   # 策略 s1 本周收益 = -2%
          "s2": 0.05,    # 策略 s2 本周收益 = +5%
      }, sleeping=["s3"], regime="RANGING_HIGH_VOL")

    P1-3: 持久化迁入 DB（OnlineLearnerStateRecord），内存为读源 + 异步 DB 写。
    """

    # 旧 JSON 状态文件（仅用于一次性迁移）
    _LEGACY_FILE = Path(__file__).parent.parent / "data" / "online_learner.json"

    def __init__(self, min_weight: float = 0.01, eta: float = 0.1,
                 window: int = 20, fixed_share: float = 0.05):
        self.min_weight: float = min_weight     # 最小权重（不至完全归零）
        self.eta: float = eta                   # 初始学习率
        self.window: int = window               # 自适应窗口
        self.fixed_share: float = fixed_share   # Fixed-Share 再分配比例
        self._experts: dict[str, ExpertState] = {}
        self._iteration: int = 0
        self._db_ready: bool = False

    async def init_from_db(self):
        """启动时从 DB 加载状态（P1-3）"""
        try:
            from db.database import async_session
            from db.models import OnlineLearnerStateRecord
            from sqlalchemy import select

            async with async_session() as session:
                r = await session.execute(
                    select(OnlineLearnerStateRecord).where(OnlineLearnerStateRecord.id == 1)
                )
                row = r.scalar_one_or_none()
                if row:
                    self.eta = row.eta or 0.1
                    self._iteration = row.iteration or 0
                    for sid, data in (row.experts or {}).items():
                        self._experts[sid] = ExpertState(**data)
                    log.info(f"OnlineLearner: loaded {len(self._experts)} experts from DB")
                else:
                    # 尝试从旧 JSON 迁移
                    await self._migrate_from_json()
        except Exception as e:
            log.warning(f"OnlineLearner: init_from_db failed ({e}), starting fresh")
        finally:
            self._db_ready = True

    async def _migrate_from_json(self):
        """一次性迁移：online_learner.json → DB"""
        try:
            if self._LEGACY_FILE.exists():
                raw = json.loads(self._LEGACY_FILE.read_text(encoding="utf-8"))
                self.eta = raw.get("eta", 0.1)
                self._iteration = raw.get("iteration", 0)
                for sid, data in raw.get("experts", {}).items():
                    self._experts[sid] = ExpertState(**data)
                log.info(f"OnlineLearner: migrated {len(self._experts)} experts from JSON")
                await self._save_to_db()
                self._LEGACY_FILE.replace(self._LEGACY_FILE.with_suffix(".migrated"))
        except Exception as e:
            log.warning(f"OnlineLearner: JSON migration failed: {e}")

    async def refresh_from_db(self):
        """多 worker 同步：从 DB 刷新内存状态（调度器每 N 秒调用）"""
        try:
            from db.database import async_session
            from db.models import OnlineLearnerStateRecord
            from sqlalchemy import select

            async with async_session() as session:
                r = await session.execute(
                    select(OnlineLearnerStateRecord).where(OnlineLearnerStateRecord.id == 1)
                )
                row = r.scalar_one_or_none()
                if row:
                    self.eta = row.eta or 0.1
                    self._iteration = row.iteration or 0
                    self._experts.clear()
                    for sid, data in (row.experts or {}).items():
                        self._experts[sid] = ExpertState(**data)
        except Exception:
            pass  # 刷新失败不影响运行

    async def _save_to_db(self):
        """异步写入 DB"""
        from db.database import async_session
        from db.models import OnlineLearnerStateRecord
        from sqlalchemy import select

        async with async_session() as session:
            r = await session.execute(
                select(OnlineLearnerStateRecord).where(OnlineLearnerStateRecord.id == 1)
            )
            row = r.scalar_one_or_none()
            data = {
                "eta": self.eta,
                "iteration": self._iteration,
                "experts": {sid: e.to_dict() for sid, e in self._experts.items()},
            }
            if row is None:
                row = OnlineLearnerStateRecord(id=1, **data)
                session.add(row)
            else:
                row.eta = self.eta
                row.iteration = self._iteration
                row.experts = data["experts"]
            await session.commit()

    # ------------------------------------------------------------------
    # 核心更新
    # ------------------------------------------------------------------

    def update(self, returns: dict[str, float],
               sleeping: list[str] | None = None,
               regime: str = "") -> LearnerResult:
        """
        根据本周各策略收益更新权重。

        Args:
          returns: {strategy_id: periodic_return}  (负值=亏损)
          sleeping: 当前应休眠的策略ID列表
          regime: 当前市场状态（用于日志）

        Returns:
          LearnerResult with updated weights
        """
        self._iteration += 1
        sleeping = sleeping or []

        # 1) 确保所有策略已注册
        for sid in returns:
            if sid not in self._experts:
                self._experts[sid] = ExpertState(strategy_id=sid, strategy_type="unknown")

        # 2) 计算损失（损失 = -收益，归一化到 [0,1]）
        loss_map = self._compute_losses(returns)

        # 3) 标记 Sleeping Experts
        for sid in sleeping:
            if sid in self._experts:
                self._experts[sid].is_sleeping = True
                self._experts[sid].weight = self.min_weight

        # 4) 自适应学习率
        self._adapt_eta()

        # 5) 指数加权更新活跃 Expert
        active_ids = [sid for sid in returns if sid not in sleeping]
        if active_ids:
            self._hedge_update(loss_map, active_ids)

        # 6) Fixed-Share: 将固定比例从活跃 Expert 重新分配给全体
        self._fixed_share_redistribute(sleeping)

        # 7) 归一化权重
        self._normalize_weights()

        # 构建结果
        weights = {}
        for sid, expert in self._experts.items():
            if sid in returns or sid in sleeping:
                weights[sid] = expert.weight

        result = LearnerResult(
            weights=weights,
            sleeping=sleeping,
            learning_rate=self.eta,
            iteration=self._iteration,
        )

        self._persist()
        log.info(f"OnlineLearner[{regime or 'GENERAL'}]: iter={self._iteration} "
                 f"eta={self.eta:.3f} active={len(active_ids)} sleeping={len(sleeping)}")
        return result

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_weights(self) -> dict[str, float]:
        return {sid: e.weight for sid, e in self._experts.items() if not e.is_sleeping}

    def get_all_states(self) -> list[dict]:
        return [e.to_dict() for e in self._experts.values()]

    def reset(self):
        self._experts.clear()
        self._iteration = 0
        self.eta = 0.1
        self._persist()

    # ------------------------------------------------------------------
    # 内部算法
    # ------------------------------------------------------------------

    def _compute_losses(self, returns: dict[str, float]) -> dict[str, float]:
        """收益 → 归一化损失"""
        if not returns:
            return {}

        min_ret = min(returns.values())
        max_ret = max(returns.values())
        rng = max_ret - min_ret if max_ret != min_ret else 1.0

        losses = {}
        for sid, ret in returns.items():
            # 损失 = 1 - 归一化收益（最优 = 0 损失，最差 = 1 损失）
            norm_ret = (ret - min_ret) / rng
            losses[sid] = 1.0 - norm_ret
        return losses

    def _adapt_eta(self):
        """自适应学习率：根据最近表现调整"""
        if self._iteration < self.window:
            return

        # 计算总损失的波动率
        all_losses = []
        for expert in self._experts.values():
            all_losses.extend(expert.recent_losses[-self.window:])

        if not all_losses:
            return

        mean_loss = sum(all_losses) / len(all_losses)
        variance = sum((l - mean_loss) ** 2 for l in all_losses) / len(all_losses)

        # 高波动 → 降低学习率；低波动 → 提高学习率
        if variance > 0.1:
            self.eta = max(0.01, self.eta * 0.9)
        elif variance < 0.01:
            self.eta = min(0.5, self.eta * 1.05)
        # 否则保持不变

    def _hedge_update(self, losses: dict[str, float], active_ids: list[str]):
        """指数加权 Hedge 更新"""
        for sid in active_ids:
            if sid not in self._experts:
                continue
            expert = self._experts[sid]
            loss = losses.get(sid, 0.5)
            expert.cumulative_loss += loss
            expert.recent_losses.append(loss)

            # 权重 = exp(-η × 累积损失)
            expert.weight = math.exp(-self.eta * expert.cumulative_loss)
            expert.is_sleeping = False

    def _fixed_share_redistribute(self, sleeping: list[str]):
        """
        Fixed-Share: 从每个活跃 Expert 取 fixed_share 比例，均分给所有 Expert。
        这保证即使表现最差的 Expert 也不会完全归零。
        """
        active = [e for sid, e in self._experts.items() if sid not in sleeping]
        if not active:
            return

        total_pool = 0.0
        for expert in active:
            share = expert.weight * self.fixed_share
            expert.weight -= share
            total_pool += share

        # 均分给所有 Expert（包括休眠的）
        n = max(len(self._experts), 1)
        per_expert = total_pool / n
        for expert in self._experts.values():
            expert.weight += per_expert

    def _normalize_weights(self):
        """权重归一化到总和 = 1.0"""
        total = sum(e.weight for e in self._experts.values())
        if total > 0:
            for expert in self._experts.values():
                expert.weight /= total

    def _persist(self):
        """P1-3: fire-and-forget 异步 DB 写（内存已更新，DB 写失败不影响运行）"""
        if not self._db_ready:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._save_to_db())
        except RuntimeError:
            pass  # 无事件循环（同步脚本），跳过 DB 写


# 全局单例
online_learner = OnlineLearner()
