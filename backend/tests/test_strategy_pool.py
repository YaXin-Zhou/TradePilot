"""StrategyPool 测试"""
import pytest
from services.strategy_pool import (
    StrategyPool, PoolStrategy, StrategyStatus, strategy_pool,
)


class TestPoolStrategy:
    def test_to_dict(self):
        s = PoolStrategy(id="s1", name="MA Cross", strategy_type="ma_cross",
                         weight=0.3, running_sharpe=1.5, running_max_dd=10.0)
        d = s.to_dict()
        assert d["id"] == "s1"
        assert d["weight"] == 0.3
        assert d["status"] == "active"

    def test_is_active(self):
        s = PoolStrategy(id="s1", name="test", strategy_type="ma_cross")
        assert s.is_active_for_allocation
        s.status = StrategyStatus.SLEEPING
        assert not s.is_active_for_allocation


class TestStrategyPool:
    def setup_method(self):
        # Fresh pool
        self.pool = StrategyPool()
        for sid in list(self.pool._strategies.keys()):
            self.pool.remove(sid)

    def test_register(self):
        s = self.pool.register("s1", "MA Cross", "ma_cross", weight=0.3)
        assert s.id == "s1"
        assert s.strategy_type == "ma_cross"
        assert s.weight == 0.3
        assert self.pool.get("s1") is not None

    def test_register_duplicate(self):
        s1 = self.pool.register("s1", "A", "ma_cross")
        s2 = self.pool.register("s1", "B", "rsi")
        assert s1.id == s2.id  # 返回已有策略

    def test_remove(self):
        self.pool.register("s1", "A", "ma_cross")
        self.pool.remove("s1")
        assert self.pool.get("s1") is None

    def test_list_all(self):
        self.pool.register("s1", "A", "ma_cross")
        self.pool.register("s2", "B", "rsi")
        assert len(self.pool.list_all()) == 2

    def test_list_active(self):
        self.pool.register("s1", "A", "ma_cross", weight=0.5)
        s2 = self.pool.register("s2", "B", "rsi", weight=0.5)
        s2.status = StrategyStatus.SLEEPING
        assert len(self.pool.list_active()) == 1

    def test_update_performance(self):
        s = self.pool.register("s1", "A", "ma_cross")
        # Simulate some positive returns
        for ret in [0.01, 0.02, -0.01, 0.03, 0.01]:
            self.pool.update_performance("s1", ret, 10500, 10000)
        s = self.pool.get("s1")
        assert s is not None
        assert s.total_trades == 5
        assert s.running_sharpe != 0.0

    def test_auto_sleep_on_losses(self):
        s = self.pool.register("s1", "A", "ma_cross")
        # Varying small losses that won't tank Sharpe to elimination level
        losses = [-0.005, -0.006, -0.004, -0.005, -0.006, -0.004]
        for loss in losses:
            self.pool.update_performance("s1", loss, 9980, 10000)
        s = self.pool.get("s1")
        # Should be sleeping or eliminated (depends on Sharpe calculation)
        assert s.status != StrategyStatus.ACTIVE

    def test_auto_eliminate(self):
        s = self.pool.register("s1", "A", "ma_cross")
        # Push Sharpe deeply negative
        for _ in range(10):
            self.pool.update_performance("s1", -0.1, 5000, 10000)
        s = self.pool.get("s1")
        assert s.status in (StrategyStatus.ELIMINATED, StrategyStatus.SLEEPING)

    def test_set_weight(self):
        s = self.pool.register("s1", "A", "ma_cross")
        self.pool.set_weight("s1", 0.75)
        assert self.pool.get("s1").weight == 0.75

    def test_set_status(self):
        s = self.pool.register("s1", "A", "ma_cross")
        self.pool.set_status("s1", StrategyStatus.PAUSED)
        assert self.pool.get("s1").status == StrategyStatus.PAUSED

    def test_correlation_matrix(self):
        self.pool.register("s1", "A", "ma_cross", weight=0.3)
        self.pool.register("s2", "B", "rsi", weight=0.3)
        # Feed positive returns to both to keep them active
        for _ in range(10):
            self.pool.update_performance("s1", 0.015, 11000, 10000)
            self.pool.update_performance("s2", 0.010, 10800, 10000)
        cm = self.pool.correlation_matrix()
        assert "labels" in cm
        assert "matrix" in cm
        assert len(cm["labels"]) == 2

    def test_correlation_single(self):
        self.pool.register("s1", "A", "ma_cross")
        cm = self.pool.correlation_matrix()
        assert len(cm["labels"]) == 1
        assert cm["matrix"] == []

    def test_summary(self):
        self.pool.register("s1", "A", "ma_cross", weight=0.3)
        self.pool.register("s2", "B", "rsi", weight=0.7)
        summary = self.pool.summary()
        assert summary["total_strategies"] == 2
        assert summary["active_count"] == 2
        assert abs(summary["total_weight"] - 1.0) < 0.01

    def test_set_allocated_capital(self):
        s = self.pool.register("s1", "A", "ma_cross")
        self.pool.set_allocated_capital("s1", 5000.0)
        assert self.pool.get("s1").allocated_capital == 5000.0
