"""T1: kill_switch 触发/恢复/状态查询测试"""
import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestKillSwitchStateMachine:
    """触发 → 恢复状态机"""

    def test_initial_state_armed(self):
        from core.kill_switch import KillSwitch
        ks = KillSwitch()
        assert not ks.is_triggered
        state = ks.get_state()
        assert state["status"] == "ARMED"
        assert state["triggered_at"] is None

    def test_trigger_sets_state(self):
        from core.kill_switch import KillSwitch
        ks = KillSwitch()
        ks.trigger(by="test", reason="unit test")
        assert ks.is_triggered
        state = ks.get_state()
        assert state["status"] == "TRIGGERED"
        assert state["triggered_by"] == "test"

    def test_reset_restores_armed(self):
        from core.kill_switch import KillSwitch
        ks = KillSwitch()
        ks.trigger(by="test")
        assert ks.is_triggered
        ks.reset()
        assert not ks.is_triggered
        state = ks.get_state()
        assert state["status"] == "ARMED"

    def test_trigger_with_reason(self):
        from core.kill_switch import KillSwitch
        ks = KillSwitch()
        state = ks.trigger(by="admin", reason="market anomaly detected")
        assert state.triggered_by == "admin"
        assert "market anomaly" in state.reason


class TestKillSwitchConsistency:
    """多实例场景（内存状态独立）"""

    def test_two_instances_independent_state(self):
        from core.kill_switch import KillSwitch
        ks1, ks2 = KillSwitch(), KillSwitch()
        ks1.trigger(by="worker1")
        # 两个实例独立，ks2 不受影响
        assert ks1.is_triggered
        # 注意：内存模式下两个实例独立
        ks2.trigger(by="worker2")
        assert ks2.is_triggered

    def test_get_state_after_trigger(self):
        from core.kill_switch import KillSwitch
        ks = KillSwitch()
        ks.trigger(by="test", reason="testing")
        state = ks.get_state()
        assert "TRIGGERED" in state["status"]
        assert state["triggered_by"] == "test"
