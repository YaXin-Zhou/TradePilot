"""PortfolioAllocator 测试"""
import pytest
from services.portfolio_allocator import (
    PortfolioAllocator, Allocation, AllocationPlan, portfolio_allocator,
)
from services.regime_detector import MarketRegime
from services.risk_engine import risk_engine


class TestAllocation:
    def test_to_dict(self):
        a = Allocation(
            strategy_id="s1", target_capital=30000, current_capital=28000,
            weight=0.3, deviation_pct=6.67, action="buy", amount=1000,
        )
        d = a.to_dict()
        assert d["strategy_id"] == "s1"
        assert d["action"] == "buy"
        assert d["amount"] == 1000


class TestAllocationPlan:
    def test_to_dict(self):
        a = Allocation("s1", 30000, 28000, 0.3, 6.67, "buy", 1000)
        plan = AllocationPlan(
            allocations=[a], total_capital=100000, allocated_capital=30000,
            reserve_capital=70000, needs_rebalance=True, regime="TRENDING_UP",
        )
        d = plan.to_dict()
        assert len(d["allocations"]) == 1
        assert d["needs_rebalance"] is True
        assert d["regime"] == "TRENDING_UP"


class TestPortfolioAllocator:
    def setup_method(self):
        risk_engine.reset_to_defaults()

    def test_allocate_basic(self):
        weights = {"s1": 0.4, "s2": 0.3, "s3": 0.3}
        positions = {"s1": 15000, "s2": 10000}
        plan = portfolio_allocator.allocate(
            weights, total_capital=100000, current_positions=positions,
            regime=MarketRegime.TRENDING_UP,
        )
        assert len(plan.allocations) == 3
        assert plan.total_capital == 100000
        assert plan.allocated_capital > 0

    def test_allocate_respects_max_single(self):
        weights = {"s1": 0.9, "s2": 0.1}
        plan = portfolio_allocator.allocate(
            weights, total_capital=100000, current_positions={},
            regime=MarketRegime.TRENDING_UP,
        )
        s1 = next(a for a in plan.allocations if a.strategy_id == "s1")
        # TRENDING_UP max_single = 0.20, so s1 should be capped at 20000
        assert s1.target_capital <= 21000

    def test_allocate_detects_rebalance(self):
        weights = {"s1": 0.5, "s2": 0.5}
        positions = {"s1": 0, "s2": 0}
        plan = portfolio_allocator.allocate(
            weights, total_capital=100000, current_positions=positions,
            regime=MarketRegime.RANGING_LOW_VOL,
        )
        # 偏差很大 → needs_rebalance
        assert plan.needs_rebalance

    def test_rebalance_full(self):
        weights = {"s1": 0.5, "s2": 0.5}
        positions = {"s1": 10000, "s2": 90000}
        plan = portfolio_allocator.rebalance(
            weights, total_capital=100000, current_positions=positions,
        )
        s1 = next(a for a in plan.allocations if a.strategy_id == "s1")
        s2 = next(a for a in plan.allocations if a.strategy_id == "s2")
        # s1 should buy, s2 should sell
        assert s1.action in ("buy", "hold")
        assert s2.action in ("sell", "hold")
        assert plan.needs_rebalance

    def test_allocate_with_string_regime(self):
        plan = portfolio_allocator.allocate(
            {"s1": 1.0}, 100000, {}, regime="TRENDING_DOWN",
        )
        assert plan.regime == "TRENDING_DOWN"

    def test_allocate_empty_weights(self):
        plan = portfolio_allocator.allocate({}, 100000, {})
        assert plan.allocations == []

    def test_allocate_zero_weight_skipped(self):
        plan = portfolio_allocator.allocate({"s1": 0.0, "s2": 1.0}, 100000, {})
        assert len(plan.allocations) == 1
        assert plan.allocations[0].strategy_id == "s2"

    def test_allocate_with_existing_positions(self):
        # TRENDING_UP: max_single=0.20
        # s1 target=min(100000*0.4, 20000)=20000, s2=min(60000, 20000)=20000
        # positions close to target → deviation should be small
        weights = {"s1": 0.4, "s2": 0.6}
        positions = {"s1": 19000, "s2": 21000}
        plan = portfolio_allocator.allocate(
            weights, total_capital=100000, current_positions=positions,
            regime=MarketRegime.TRENDING_UP,
        )
        for a in plan.allocations:
            assert abs(a.deviation_pct) < 15

    def test_rebalance_with_tiny_deviation(self):
        # TRENDING_UP: max_single=0.20
        # target_s1=min(20000*0.5, 4000)=4000, target_s2=4000
        weights = {"s1": 0.5, "s2": 0.5}
        positions = {"s1": 4000, "s2": 4000}  # exact match
        plan = portfolio_allocator.rebalance(
            weights, total_capital=20000, current_positions=positions,
            regime=MarketRegime.TRENDING_UP,
        )
        for a in plan.allocations:
            assert a.action == "hold"
