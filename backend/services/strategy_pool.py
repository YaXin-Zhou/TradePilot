"""
策略池管理 — 活跃策略的权重/Sharpe/回撤/相关性矩阵

功能:
  - 策略注册/注销
  - 运行中 Sharpe / 回撤追踪
  - 相关性矩阵（热力图数据源）
  - 自动启停：连续亏损自动休眠、Sharpe 归零淘汰
  - 前端仪表盘数据源

P1-3: JSON 文件持久化迁入 DB（StrategyPoolRecord），
      内存为读源 + fire-and-forget 异步 DB 写，调度器定期 refresh。
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from core.logger import log


class StrategyStatus(str, Enum):
    ACTIVE = "active"         # 活跃运行中
    SLEEPING = "sleeping"     # 自动休眠（Regime不适配/连续亏损）
    PAUSED = "paused"         # 手动暂停
    ELIMINATED = "eliminated" # 已淘汰（Sharpe 归零）
    DEPLOYED = "deployed"     # 已部署到模拟盘


@dataclass
class PoolStrategy:
    """池中单个策略"""
    id: str
    name: str
    strategy_type: str                     # ma_cross / rsi / bollinger / grid / ai_generated
    weight: float = 0.0                    # 当前权重 (0.0 ~ 1.0, 所有活跃策略合计 = 1.0)
    running_sharpe: float = 0.0            # 运行中 Sharpe（滚动窗口）
    running_max_dd: float = 0.0            # 运行中最大回撤 (%)
    return_series: list[float] = field(default_factory=list)  # 日收益率序列
    status: StrategyStatus = StrategyStatus.ACTIVE
    consecutive_losses: int = 0
    total_trades: int = 0
    allocated_capital: float = 0.0
    deployed_at: Optional[float] = None
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "strategy_type": self.strategy_type,
            "weight": round(self.weight, 4),
            "running_sharpe": round(self.running_sharpe, 4),
            "running_max_dd": round(self.running_max_dd, 4),
            "status": self.status.value,
            "consecutive_losses": self.consecutive_losses,
            "total_trades": self.total_trades,
            "allocated_capital": round(self.allocated_capital, 2),
            "last_updated": self.last_updated,
        }

    @property
    def is_active_for_allocation(self) -> bool:
        return self.status in (StrategyStatus.ACTIVE, StrategyStatus.DEPLOYED)


class StrategyPool:
    """策略池管理器"""

    MAX_SLEEP_LOSSES: int = 5       # 连续亏损 5 次自动休眠
    SHARPE_ELIMINATE: float = -0.5  # Sharpe 低于此值淘汰
    # 旧 JSON 文件（仅用于一次性迁移）
    _LEGACY_FILE = Path(__file__).parent.parent / "data" / "strategy_pool.json"

    def __init__(self):
        self._strategies: dict[str, PoolStrategy] = {}
        self._db_ready: bool = False

    async def init_from_db(self):
        """启动时从 DB 加载策略池（P1-3）"""
        try:
            from db.database import async_session
            from db.models import StrategyPoolRecord
            from sqlalchemy import select

            async with async_session() as session:
                r = await session.execute(select(StrategyPoolRecord))
                rows = r.scalars().all()
                if rows:
                    for row in rows:
                        s = PoolStrategy(
                            id=row.id, name=row.name,
                            strategy_type=row.strategy_type,
                            weight=row.weight,
                            running_sharpe=row.running_sharpe,
                            running_max_dd=row.running_max_dd,
                            status=StrategyStatus(row.status) if row.status else StrategyStatus.ACTIVE,
                            consecutive_losses=row.consecutive_losses,
                            total_trades=row.total_trades,
                            allocated_capital=row.allocated_capital,
                            deployed_at=row.deployed_at,
                            last_updated=row.last_updated or time.time(),
                        )
                        s.return_series = row.return_series or []
                        self._strategies[row.id] = s
                    log.info(f"StrategyPool: loaded {len(self._strategies)} strategies from DB")
                else:
                    await self._migrate_from_json()
        except Exception as e:
            log.warning(f"StrategyPool: init_from_db failed ({e}), starting fresh")
        finally:
            self._db_ready = True

    async def _migrate_from_json(self):
        """一次性迁移：strategy_pool.json → DB"""
        try:
            if self._LEGACY_FILE.exists():
                raw = json.loads(self._LEGACY_FILE.read_text(encoding="utf-8"))
                for sid, data in raw.items():
                    returns = data.pop("return_series", [])
                    fields = {k: v for k, v in data.items()
                              if k in PoolStrategy.__dataclass_fields__ and k != "id"}
                    s = PoolStrategy(id=sid, **fields)
                    s.return_series = returns
                    if isinstance(data.get("status"), str):
                        try:
                            s.status = StrategyStatus(data["status"])
                        except ValueError:
                            pass
                    self._strategies[sid] = s
                log.info(f"StrategyPool: migrated {len(self._strategies)} strategies from JSON")
                await self._save_to_db()
                self._LEGACY_FILE.replace(self._LEGACY_FILE.with_suffix(".migrated"))
        except Exception as e:
            log.warning(f"StrategyPool: JSON migration failed: {e}")

    async def refresh_from_db(self):
        """多 worker 同步：从 DB 刷新内存状态（调度器每 N 秒调用）"""
        try:
            from db.database import async_session
            from db.models import StrategyPoolRecord
            from sqlalchemy import select

            async with async_session() as session:
                r = await session.execute(select(StrategyPoolRecord))
                rows = r.scalars().all()
                if rows:
                    self._strategies.clear()
                    for row in rows:
                        s = PoolStrategy(
                            id=row.id, name=row.name,
                            strategy_type=row.strategy_type,
                            weight=row.weight,
                            running_sharpe=row.running_sharpe,
                            running_max_dd=row.running_max_dd,
                            status=StrategyStatus(row.status) if row.status else StrategyStatus.ACTIVE,
                            consecutive_losses=row.consecutive_losses,
                            total_trades=row.total_trades,
                            allocated_capital=row.allocated_capital,
                            deployed_at=row.deployed_at,
                            last_updated=row.last_updated or time.time(),
                        )
                        s.return_series = row.return_series or []
                        self._strategies[row.id] = s
        except Exception:
            pass  # 刷新失败不影响运行

    async def _save_to_db(self):
        """异步全量写入 DB"""
        from db.database import async_session
        from db.models import StrategyPoolRecord
        from sqlalchemy import select, delete

        async with async_session() as session:
            # 全量替换：先删后插（策略池数据量小）
            await session.execute(delete(StrategyPoolRecord))
            for sid, s in self._strategies.items():
                record = StrategyPoolRecord(
                    id=sid, name=s.name, strategy_type=s.strategy_type,
                    weight=s.weight, running_sharpe=s.running_sharpe,
                    running_max_dd=s.running_max_dd,
                    return_series=s.return_series[-100:],
                    status=s.status.value if hasattr(s.status, "value") else str(s.status),
                    consecutive_losses=s.consecutive_losses,
                    total_trades=s.total_trades,
                    allocated_capital=s.allocated_capital,
                    deployed_at=s.deployed_at,
                    last_updated=s.last_updated,
                )
                session.add(record)
            await session.commit()

    # ------------------------------------------------------------------
    # 策略 CRUD
    # ------------------------------------------------------------------

    def register(self, strategy_id: str, name: str, strategy_type: str,
                 weight: float = 0.0) -> PoolStrategy:
        """注册策略到池"""
        if strategy_id in self._strategies:
            log.warning(f"StrategyPool: {strategy_id} already registered")
            return self._strategies[strategy_id]

        s = PoolStrategy(
            id=strategy_id, name=name, strategy_type=strategy_type,
            weight=weight, deployed_at=time.time(),
        )
        self._strategies[strategy_id] = s
        self._persist()
        log.info(f"StrategyPool: registered {strategy_id} ({name}, {strategy_type})")
        return s

    def remove(self, strategy_id: str):
        """从池中移除策略"""
        if strategy_id in self._strategies:
            del self._strategies[strategy_id]
            self._persist()
            log.info(f"StrategyPool: removed {strategy_id}")

    def get(self, strategy_id: str) -> Optional[PoolStrategy]:
        return self._strategies.get(strategy_id)

    def list_all(self) -> list[PoolStrategy]:
        return list(self._strategies.values())

    def list_active(self) -> list[PoolStrategy]:
        return [s for s in self._strategies.values() if s.is_active_for_allocation]

    # ------------------------------------------------------------------
    # 状态更新
    # ------------------------------------------------------------------

    def update_performance(self, strategy_id: str, daily_return: float,
                           current_capital: float, peak_capital: float):
        """更新策略运行表现"""
        s = self._strategies.get(strategy_id)
        if not s:
            return

        s.return_series.append(daily_return)
        s.total_trades += 1

        # 滚动 Sharpe（最近 30 个交易日）
        recent = s.return_series[-30:]
        if len(recent) >= 5:
            mean_ret = sum(recent) / len(recent)
            variance = sum((r - mean_ret) ** 2 for r in recent) / max(len(recent) - 1, 1)
            std_ret = math.sqrt(variance) if variance > 0 else 0.001
            s.running_sharpe = (mean_ret / std_ret) if std_ret > 0 else 0.0
        else:
            s.running_sharpe = daily_return / 0.01 if abs(daily_return) > 0 else 0.0

        # 回撤
        if peak_capital > 0:
            dd = (peak_capital - current_capital) / peak_capital * 100
            s.running_max_dd = max(s.running_max_dd, dd)

        # 连续亏损
        if daily_return < 0:
            s.consecutive_losses += 1
        else:
            s.consecutive_losses = 0

        s.last_updated = time.time()

        # 自动休眠
        if s.consecutive_losses >= self.MAX_SLEEP_LOSSES and s.status == StrategyStatus.ACTIVE:
            s.status = StrategyStatus.SLEEPING
            log.warning(f"StrategyPool: {strategy_id} auto-slept after {s.consecutive_losses} losses")

        # 自动淘汰
        if s.running_sharpe <= self.SHARPE_ELIMINATE and s.status != StrategyStatus.ELIMINATED:
            s.status = StrategyStatus.ELIMINATED
            s.weight = 0.0
            log.warning(f"StrategyPool: {strategy_id} eliminated (Sharpe={s.running_sharpe:.3f})")

        self._persist()

    def set_weight(self, strategy_id: str, weight: float):
        s = self._strategies.get(strategy_id)
        if s:
            s.weight = max(0.0, min(1.0, weight))
            s.last_updated = time.time()
            self._persist()

    def set_status(self, strategy_id: str, status: StrategyStatus):
        s = self._strategies.get(strategy_id)
        if s:
            s.status = status
            s.last_updated = time.time()
            self._persist()
            log.info(f"StrategyPool: {strategy_id} → {status.value}")

    def set_allocated_capital(self, strategy_id: str, capital: float):
        s = self._strategies.get(strategy_id)
        if s:
            s.allocated_capital = capital
            s.last_updated = time.time()

    # ------------------------------------------------------------------
    # 相关性矩阵
    # ------------------------------------------------------------------

    def correlation_matrix(self) -> dict:
        """计算活跃策略间的相关性矩阵（供热力图）"""
        active = self.list_active()
        if len(active) < 2:
            return {"labels": [s.name for s in active], "matrix": []}

        ids = [s.id for s in active]
        labels = [s.name for s in active]
        n = len(ids)

        # 构建 n×n 矩阵
        matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                si = self._strategies[ids[i]]
                sj = self._strategies[ids[j]]
                corr = self._pearson(
                    si.return_series[-30:],
                    sj.return_series[-30:],
                )
                matrix[i][j] = round(corr, 3)
                matrix[j][i] = round(corr, 3)

        return {"labels": labels, "matrix": matrix}

    # ------------------------------------------------------------------
    # 仪表盘摘要
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """策略池仪表盘摘要"""
        all_s = self.list_all()
        active = [s for s in all_s if s.status == StrategyStatus.ACTIVE]
        sleeping = [s for s in all_s if s.status == StrategyStatus.SLEEPING]
        deployed = [s for s in all_s if s.status == StrategyStatus.DEPLOYED]

        total_weight = sum(s.weight for s in active)
        avg_sharpe = sum(s.running_sharpe for s in active) / max(len(active), 1)
        max_corr = 0.0
        cm = self.correlation_matrix()
        if cm["matrix"]:
            for row in cm["matrix"]:
                for v in row:
                    if v < 1.0:
                        max_corr = max(max_corr, v)

        return {
            "total_strategies": len(all_s),
            "active_count": len(active),
            "sleeping_count": len(sleeping),
            "deployed_count": len(deployed),
            "total_weight": round(total_weight, 4),
            "avg_sharpe": round(avg_sharpe, 4),
            "max_correlation": round(max_corr, 3),
            "strategies": [s.to_dict() for s in all_s],
        }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _pearson(x: list[float], y: list[float]) -> float:
        n = min(len(x), len(y))
        if n < 3:
            return 0.0
        mx = sum(x[:n]) / n
        my = sum(y[:n]) / n
        num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
        dx = math.sqrt(sum((xi - mx) ** 2 for xi in x[:n]))
        dy = math.sqrt(sum((yi - my) ** 2 for yi in y[:n]))
        return num / (dx * dy) if dx and dy else 0.0

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
strategy_pool = StrategyPool()
