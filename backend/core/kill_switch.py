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
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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


class KillSwitch:
    """全局紧急停止管理器（单例）"""

    STATE_FILE = Path(__file__).parent.parent / "data" / "kill_switch.json"

    def __init__(self):
        self._state = KillSwitchState()
        self._load()

    # ------------------------------------------------------------------
    # 查询
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
    # 状态变更
    # ------------------------------------------------------------------

    def trigger(self, by: str = "manual", reason: str = "") -> KillSwitchState:
        """触发紧急停止"""
        self._state = KillSwitchState(
            status=TRIGGERED,
            triggered_at=time.time(),
            triggered_by=by,
            reason=reason or "Manual emergency stop",
        )
        self._save()
        log.warning(
            f"⚠️ KILL SWITCH TRIGGERED by={by} reason={reason}. "
            "All trading is now BLOCKED until manual reset."
        )
        return self._state

    def record_action(self, action: str):
        """记录紧急停止执行的动作"""
        self._state.actions_taken.append(action)
        self._save()

    def increment_cancelled(self, n: int = 1):
        self._state.orders_cancelled += n
        self._save()

    def increment_closed(self, n: int = 1):
        self._state.positions_closed += n
        self._save()

    def increment_stopped(self, n: int = 1):
        self._state.strategies_stopped += n
        self._save()

    def reset(self) -> KillSwitchState:
        """解除紧急停止（需手动调用，二次确认在 API 层）"""
        old = self._state
        self._state = KillSwitchState()
        self._save()
        log.info(
            f"Kill switch reset (was triggered at "
            f"{datetime.fromtimestamp(old.triggered_at or 0, tz=timezone.utc).isoformat() if old.triggered_at else 'N/A'})"
        )
        return self._state

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load(self):
        try:
            if self.STATE_FILE.exists():
                data = json.loads(self.STATE_FILE.read_text(encoding="utf-8"))
                self._state = KillSwitchState(
                    status=data.get("status", ARMED),
                    triggered_at=data.get("triggered_at"),
                    triggered_by=data.get("triggered_by"),
                    reason=data.get("reason"),
                    actions_taken=data.get("actions_taken", []),
                    orders_cancelled=data.get("orders_cancelled", 0),
                    positions_closed=data.get("positions_closed", 0),
                    strategies_stopped=data.get("strategies_stopped", 0),
                )
                if self.is_triggered:
                    log.warning(
                        f"⚠️ Kill switch is TRIGGERED (from {self._state.triggered_by}). "
                        "Trading blocked. POST /api/trading/emergency-reset to clear."
                    )
        except Exception as e:
            log.warning(f"KillSwitch: failed to load state ({e}), using ARMED default")

    def _save(self):
        try:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.STATE_FILE.write_text(
                json.dumps(self._state.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            log.error(f"KillSwitch: failed to save state: {e}")


# 全局单例
kill_switch = KillSwitch()
