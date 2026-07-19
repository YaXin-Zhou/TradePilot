"""全局紧急停止（Kill Switch）— 实盘安全最后一道防线

状态机：
  ARMED    → 正常运行（默认）
  TRIGGERED → 所有下单/策略启动被拒绝，需手动 RESET

触发后：
  1. 撤销所有开仓挂单
  2. 市价平掉所有持仓
  3. 停止所有运行中的策略
  4. 持久化状态到 DB，进程重启后仍保持 TRIGGERED（需手动解除）

解除：POST /api/trading/emergency-reset（需二次确认）

P0-1 修复：状态持久化从 JSON 文件迁入 DB（kill_switch_state 表），
消除多 worker 下 JSON 文件竞态覆盖问题。
内存为读源（快速同步读取），DB 为持久化层（多 worker 一致性）。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.logger import log

# ------------------------------------------------------------------
# 状态
# ------------------------------------------------------------------

ARMED = "ARMED"
TRIGGERED = "TRIGGERED"


@dataclass
class KillSwitchState:
    status: str = ARMED
    triggered_at: Optional[float] = None
    triggered_by: Optional[str] = None
    reason: Optional[str] = None
    actions_taken: list[str] = field(default_factory=list)
    # 统计
    orders_cancelled: int = 0
    positions_closed: int = 0
    strategies_stopped: int = 0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "triggered_at": self.triggered_at,
            "triggered_by": self.triggered_by,
            "reason": self.reason,
            "actions_taken": self.actions_taken,
            "orders_cancelled": self.orders_cancelled,
            "positions_closed": self.positions_closed,
            "strategies_stopped": self.strategies_stopped,
            "timestamp": time.time(),
        }

    @classmethod
    def from_db(cls, record) -> "KillSwitchState":
        """从 DB 记录构建状态"""
        return cls(
            status=record.status or ARMED,
            triggered_at=record.triggered_at,
            triggered_by=record.triggered_by,
            reason=record.reason,
            actions_taken=record.actions_taken or [],
            orders_cancelled=record.orders_cancelled or 0,
            positions_closed=record.positions_closed or 0,
            strategies_stopped=record.strategies_stopped or 0,
        )


class KillSwitch:
    """全局紧急停止管理器（单例）

    P0-1: 状态持久化到 DB（kill_switch_state 表）。
    - 内存状态为读源（sync 快速读取）
    - 写操作内存更新后 fire-and-forget 异步写 DB
    - 启动时从 DB 加载（init_from_db）
    - 多 worker 可通过 refresh_from_db 同步状态
    """

    def __init__(self):
        self._state = KillSwitchState()
        self._db_ready = False  # DB 初始化完成标志

    # ------------------------------------------------------------------
    # DB 初始化与刷新（异步，启动时调用）
    # ------------------------------------------------------------------

    async def init_from_db(self):
        """从 DB 加载状态（lifespan 启动时调用）"""
        try:
            from db.database import async_session
            from db.models import KillSwitchStateRecord

            async with async_session() as session:
                record = await session.get(KillSwitchStateRecord, 1)
                if record:
                    self._state = KillSwitchState.from_db(record)
                    if self.is_triggered:
                        log.warning(
                            f"⚠️ Kill switch is TRIGGERED (from "
                            f"{self._state.triggered_by}). "
                            "Trading blocked. POST /api/trading/emergency-reset to clear."
                        )
                else:
                    # 首次启动：创建默认 ARMED 记录
                    record = KillSwitchStateRecord(id=1, status=ARMED)
                    session.add(record)
                    await session.commit()
            self._db_ready = True
            log.info(f"KillSwitch: loaded from DB (status={self._state.status})")
        except Exception as e:
            log.warning(f"KillSwitch: DB init failed ({e}), using in-memory default")
            self._db_ready = True  # 标记为 ready，允许 fire-and-forget 重试

    async def refresh_from_db(self):
        """从 DB 重新加载状态（多 worker 同步，定时调用）"""
        if not self._db_ready:
            return
        try:
            from db.database import async_session
            from db.models import KillSwitchStateRecord

            async with async_session() as session:
                record = await session.get(KillSwitchStateRecord, 1)
                if record:
                    new_state = KillSwitchState.from_db(record)
                    # 只在状态变化时更新 + 日志
                    if new_state.status != self._state.status:
                        log.warning(
                            f"KillSwitch: status changed via DB "
                            f"{self._state.status} → {new_state.status}"
                        )
                        self._state = new_state
                    elif new_state != self._state:
                        # 统计数据变化（increment 操作）
                        self._state = new_state
        except Exception as e:
            log.debug(f"KillSwitch: DB refresh failed ({e})")

    # ------------------------------------------------------------------
    # 查询（同步，读内存）
    # ------------------------------------------------------------------

    @property
    def is_triggered(self) -> bool:
        return self._state.status == TRIGGERED

    @property
    def is_armed(self) -> bool:
        return self._state.status == ARMED

    def get_state(self) -> dict:
        return self._state.to_dict()

    # ------------------------------------------------------------------
    # 状态变更（同步更新内存 + 异步持久化 DB）
    # ------------------------------------------------------------------

    def trigger(self, by: str = "manual", reason: str = "") -> KillSwitchState:
        """触发紧急停止"""
        self._state = KillSwitchState(
            status=TRIGGERED,
            triggered_at=time.time(),
            triggered_by=by,
            reason=reason or "Manual emergency stop",
        )
        self._persist()
        log.warning(
            f"⚠️ KILL SWITCH TRIGGERED by={by} reason={reason}. "
            "All trading is now BLOCKED until manual reset."
        )
        return self._state

    def record_action(self, action: str):
        """记录紧急停止执行的动作"""
        self._state.actions_taken.append(action)
        self._persist()

    def increment_cancelled(self, n: int = 1):
        self._state.orders_cancelled += n
        self._persist()

    def increment_closed(self, n: int = 1):
        self._state.positions_closed += n
        self._persist()

    def increment_stopped(self, n: int = 1):
        self._state.strategies_stopped += n
        self._persist()

    def reset(self) -> KillSwitchState:
        """解除紧急停止（需手动调用，二次确认在 API 层）"""
        old = self._state
        self._state = KillSwitchState()
        self._persist()
        log.info(
            f"Kill switch reset (was triggered at "
            f"{datetime.fromtimestamp(old.triggered_at or 0, tz=timezone.utc).isoformat() if old.triggered_at else 'N/A'})"
        )
        return self._state

    # ------------------------------------------------------------------
    # 持久化（fire-and-forget 异步写 DB）
    # ------------------------------------------------------------------

    def _persist(self):
        """调度异步 DB 写入（不阻塞调用方）"""
        if not self._db_ready:
            return  # DB 未就绪，仅内存
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._save_to_db())
        except RuntimeError:
            # 无事件循环（同步脚本中调用）— 跳过 DB 写入
            pass

    async def _save_to_db(self):
        """异步写入 DB"""
        try:
            from db.database import async_session
            from db.models import KillSwitchStateRecord

            async with async_session() as session:
                record = await session.get(KillSwitchStateRecord, 1)
                if record:
                    record.status = self._state.status
                    record.triggered_at = self._state.triggered_at
                    record.triggered_by = self._state.triggered_by
                    record.reason = self._state.reason
                    record.actions_taken = list(self._state.actions_taken)
                    record.orders_cancelled = self._state.orders_cancelled
                    record.positions_closed = self._state.positions_closed
                    record.strategies_stopped = self._state.strategies_stopped
                else:
                    record = KillSwitchStateRecord(
                        id=1,
                        status=self._state.status,
                        triggered_at=self._state.triggered_at,
                        triggered_by=self._state.triggered_by,
                        reason=self._state.reason,
                        actions_taken=list(self._state.actions_taken),
                        orders_cancelled=self._state.orders_cancelled,
                        positions_closed=self._state.positions_closed,
                        strategies_stopped=self._state.strategies_stopped,
                    )
                    session.add(record)
                await session.commit()
        except Exception as e:
            log.error(f"KillSwitch: DB save failed: {e}")


# 全局单例
kill_switch = KillSwitch()
