"""AI 心跳模块测试"""
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from tasks.ai_heartbeat import (
    AIHeartbeat, HeartbeatResult, StrategySnapshot,
    get_heartbeat,
)
from services.strategy_pool import strategy_pool, PoolStrategy, StrategyStatus


def make_snapshot(**kwargs) -> StrategySnapshot:
    defaults = {
        "strategy_id": "test_001",
        "name": "Test Strategy",
        "strategy_type": "grid",
        "weight": 0.2,
        "sharpe": 1.5,
        "max_drawdown": 0.10,
        "consecutive_losses": 1,
        "status": "active",
        "total_trades": 50,
    }
    defaults.update(kwargs)
    return StrategySnapshot(**defaults)


class TestStrategySnapshot:
    def test_to_dict(self):
        s = make_snapshot()
        d = s.to_dict()
        assert d["strategy_id"] == "test_001"
        assert d["sharpe"] == 1.5
        assert d["status"] == "active"

    def test_defaults(self):
        s = make_snapshot(strategy_id="s2", sharpe=-0.3, status="sleeping")
        d = s.to_dict()
        assert d["sharpe"] == -0.3
        assert d["status"] == "sleeping"


class TestHeartbeatResult:
    def test_to_dict(self):
        snap = make_snapshot()
        result = HeartbeatResult(
            cycle=5,
            pool_summary={"total": 3},
            strategies=[snap],
            changes_since_last=["[SHARPE] Test: 1.0 → 1.5 (↑0.50)"],
            recommendations=[{"action": "no_action"}],
            ai_raw_response="OK",
            report_file="/tmp/test.json",
        )
        d = result.to_dict()
        assert d["cycle"] == 5
        assert "timestamp" in d
        assert len(d["strategies"]) == 1
        assert len(d["changes_since_last"]) == 1
        assert len(d["recommendations"]) == 1


class TestAIHeartbeat:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.hb = AIHeartbeat(deepseek_api_key="", report_dir=self.tmpdir)

    def test_rule_based_review_healthy(self):
        """无问题的策略池 → no_action"""
        snapshots = [
            make_snapshot(strategy_id="s1", name="Grid BTC", sharpe=2.0, max_drawdown=0.05),
            make_snapshot(strategy_id="s2", name="ML ETH", sharpe=1.2, max_drawdown=0.15),
        ]
        recs = self.hb._rule_based_review({}, snapshots, [])
        assert any(r["action"] == "no_action" for r in recs)

    def test_rule_based_review_consecutive_losses(self):
        """连续亏损 → sleep 建议"""
        snapshots = [
            make_snapshot(strategy_id="s1", name="Bad Grid", sharpe=0.3,
                         consecutive_losses=7, status="active"),
        ]
        recs = self.hb._rule_based_review({}, snapshots, [])
        assert any(r["action"] == "sleep" for r in recs)

    def test_rule_based_review_negative_sharpe(self):
        """负 Sharpe → eliminate"""
        snapshots = [
            make_snapshot(strategy_id="s1", name="Terrible ML", sharpe=-1.2,
                         status="active"),
        ]
        recs = self.hb._rule_based_review({}, snapshots, [])
        assert any(r["action"] == "eliminate" for r in recs)

    def test_rule_based_review_high_drawdown(self):
        """高回撤 → reduce_weight"""
        snapshots = [
            make_snapshot(strategy_id="s1", name="Risky Grid", sharpe=0.5,
                         max_drawdown=0.40, status="active"),
        ]
        recs = self.hb._rule_based_review({}, snapshots, [])
        assert any(r["action"] == "reduce_weight" for r in recs)

    def test_rule_based_review_slightly_negative(self):
        """略负 Sharpe → reduce_weight (低优先级)"""
        snapshots = [
            make_snapshot(strategy_id="s1", name="Mediocre", sharpe=-0.15,
                         status="active"),
        ]
        recs = self.hb._rule_based_review({}, snapshots, [])
        assert any(r["action"] == "reduce_weight" and r["priority"] == "low" for r in recs)

    def test_rule_based_review_already_eliminated(self):
        """已淘汰策略不再建议淘汰"""
        snapshots = [
            make_snapshot(strategy_id="s1", name="Gone", sharpe=-1.0,
                         status="eliminated"),
        ]
        recs = self.hb._rule_based_review({}, snapshots, [])
        # 不应有 eliminate 建议（已经淘汰了）
        assert not any(r["action"] == "eliminate" for r in recs)

    def test_detect_changes_initial(self):
        """首次心跳 → 初始消息"""
        snapshots = [make_snapshot()]
        changes = self.hb._detect_changes(snapshots)
        assert any("Initial" in c for c in changes)

    def test_detect_changes_sharpe_up(self):
        """Sharpe 显著变化"""
        # 先设置上次周期
        self.hb._last_cycle = HeartbeatResult(
            cycle=0,
            strategies=[make_snapshot(strategy_id="s1", sharpe=1.0)],
        )
        current = [make_snapshot(strategy_id="s1", sharpe=2.0)]
        changes = self.hb._detect_changes(current)
        assert any("SHARPE" in c and "↑" in c for c in changes)

    def test_detect_changes_new_strategy(self):
        """新加入策略"""
        self.hb._last_cycle = HeartbeatResult(cycle=0, strategies=[])
        current = [make_snapshot(strategy_id="new_one", name="New Strategy")]
        changes = self.hb._detect_changes(current)
        assert any("NEW" in c for c in changes)

    def test_detect_changes_removed_strategy(self):
        """策略被移除"""
        self.hb._last_cycle = HeartbeatResult(
            cycle=0,
            strategies=[make_snapshot(strategy_id="removed", name="Gone")],
        )
        current = []
        changes = self.hb._detect_changes(current)
        assert any("REMOVED" in c for c in changes)

    def test_detect_changes_status_change(self):
        """状态变化"""
        self.hb._last_cycle = HeartbeatResult(
            cycle=0,
            strategies=[make_snapshot(strategy_id="s1", status="active")],
        )
        current = [make_snapshot(strategy_id="s1", status="sleeping")]
        changes = self.hb._detect_changes(current)
        assert any("STATUS" in c for c in changes)

    def test_detect_changes_weight_change(self):
        """权重显著变化"""
        self.hb._last_cycle = HeartbeatResult(
            cycle=0,
            strategies=[make_snapshot(strategy_id="s1", weight=0.3)],
        )
        current = [make_snapshot(strategy_id="s1", weight=0.15)]  # 降 50%
        changes = self.hb._detect_changes(current)
        assert any("WEIGHT" in c for c in changes)

    def test_detect_changes_consecutive_losses(self):
        """连续亏损增加"""
        self.hb._last_cycle = HeartbeatResult(
            cycle=0,
            strategies=[make_snapshot(strategy_id="s1", consecutive_losses=1)],
        )
        current = [make_snapshot(strategy_id="s1", consecutive_losses=4)]
        changes = self.hb._detect_changes(current)
        assert any("LOSSES" in c for c in changes)

    def test_detect_changes_no_significant(self):
        """无显著变化"""
        self.hb._last_cycle = HeartbeatResult(
            cycle=0,
            strategies=[make_snapshot(strategy_id="s1")],
        )
        current = [make_snapshot(strategy_id="s1")]
        changes = self.hb._detect_changes(current)
        assert any("No significant" in c for c in changes)

    def test_save_and_load_history(self):
        """保存报告并加载历史"""
        # 模拟 beat
        snapshots = [make_snapshot(strategy_id="s1", name="Test Grid")]
        recs = [{"action": "no_action", "strategy_name": "N/A"}]

        result = HeartbeatResult(
            cycle=1,
            pool_summary={"total": 1},
            strategies=snapshots,
            changes_since_last=["Initial heartbeat"],
            recommendations=recs,
        )

        self.hb._save_report(result)
        assert result.report_file != ""

        # 加载历史
        self.hb._history = []
        self.hb._load_history()
        assert self.hb._cycle_count >= 1

    def test_get_history(self):
        """获取历史记录"""
        self.hb._history = [
            HeartbeatResult(cycle=i, strategies=[make_snapshot(strategy_id=f"s{i}")])
            for i in range(1, 5)
        ]
        history = self.hb.get_history(limit=3)
        assert len(history) == 3

    def test_get_last_cycle_none(self):
        assert self.hb.get_last_cycle() is None

    def test_get_last_cycle_with_data(self):
        self.hb._last_cycle = HeartbeatResult(cycle=3)
        assert self.hb.get_last_cycle() is not None


class TestGlobalSingleton:
    def test_get_heartbeat(self):
        import tasks.ai_heartbeat as hb_module
        hb_module._heartbeat = None
        hb = hb_module.get_heartbeat()
        assert isinstance(hb, AIHeartbeat)
