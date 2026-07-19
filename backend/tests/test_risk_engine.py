"""RiskEngine 测试"""
import pytest
from services.regime_detector import MarketRegime
from services.risk_engine import (
    RiskEngine, RiskPolicy, RiskCheckResult, DEFAULT_POLICIES, risk_engine,
)


class TestRiskPolicy:
    """风控策略模型"""

    def test_default_policy(self):
        p = DEFAULT_POLICIES[MarketRegime.TRENDING_UP]
        assert p.max_position_pct == 0.40
        assert p.stop_loss_pct == 8.0
        assert p.allowed_strategies == []

    def test_policy_to_dict(self):
        p = RiskPolicy(regime=MarketRegime.TRENDING_DOWN)
        d = p.to_dict()
        assert d["regime"] == "TRENDING_DOWN"
        assert "max_position_pct" in d
        assert "allowed_strategies" in d

    def test_downtrend_restricted(self):
        """下跌趋势中只允许 RSI 策略"""
        p = DEFAULT_POLICIES[MarketRegime.TRENDING_DOWN]
        assert "rsi" in p.allowed_strategies
        assert "ma_cross" not in p.allowed_strategies
        assert p.max_position_pct < 0.3  # 更保守


class TestRiskCheckResult:
    def test_passed(self):
        r = RiskCheckResult(passed=True)
        assert r.passed
        assert r.reason == ""

    def test_failed_with_reason(self):
        r = RiskCheckResult(passed=False, reason="Position limit exceeded")
        assert not r.passed
        assert "Position" in r.reason

    def test_to_dict(self):
        r = RiskCheckResult(passed=True, checks={"a": 1})
        d = r.to_dict()
        assert d["passed"] is True
        assert d["checks"] == {"a": 1}


class TestRiskEngine:
    """风控引擎"""

    def setup_method(self):
        self.engine = RiskEngine()
        self.engine.reset_to_defaults()

    def test_get_policy(self):
        p = self.engine.get_policy(MarketRegime.TRENDING_UP)
        assert isinstance(p, RiskPolicy)
        assert p.max_position_pct > 0

    def test_get_all_policies(self):
        all_p = self.engine.get_all_policies()
        assert len(all_p) == 4
        assert "TRENDING_UP" in all_p
        assert "TRENDING_DOWN" in all_p

    def test_update_policy(self):
        p = self.engine.update_policy(MarketRegime.TRENDING_UP, max_position_pct=0.50)
        assert p.max_position_pct == 0.50
        # 另一个 regime 不受影响
        p2 = self.engine.get_policy(MarketRegime.TRENDING_DOWN)
        assert p2.max_position_pct != 0.50

    def test_reset_to_defaults(self):
        self.engine.update_policy(MarketRegime.TRENDING_UP, max_position_pct=0.99)
        self.engine.reset_to_defaults()
        p = self.engine.get_policy(MarketRegime.TRENDING_UP)
        assert p.max_position_pct == 0.40

    # 入场准入

    def test_strategy_entry_allowed(self):
        r = self.engine.check_strategy_entry(
            MarketRegime.TRENDING_UP, "ma_cross", sharpe_oos=1.5)
        assert r.passed

    def test_strategy_entry_sharpe_too_low(self):
        r = self.engine.check_strategy_entry(
            MarketRegime.TRENDING_UP, "ma_cross", sharpe_oos=0.3)
        assert not r.passed
        assert "Sharpe" in r.reason

    def test_strategy_entry_regime_blocked(self):
        r = self.engine.check_strategy_entry(
            MarketRegime.TRENDING_DOWN, "grid", sharpe_oos=2.0)
        assert not r.passed
        assert "not allowed" in r.reason.lower()

    def test_strategy_entry_rsi_in_downtrend(self):
        """RSI 在下跌趋势中允许"""
        r = self.engine.check_strategy_entry(
            MarketRegime.TRENDING_DOWN, "rsi", sharpe_oos=1.2)
        assert r.passed

    # 仓位检查

    def test_position_limit_pass(self):
        r = self.engine.check_position_limit(
            MarketRegime.TRENDING_UP, total_capital=100000,
            current_position=10000, new_amount=5000)
        assert r.passed

    def test_position_limit_exceeded(self):
        r = self.engine.check_position_limit(
            MarketRegime.TRENDING_UP, total_capital=100000,
            current_position=35000, new_amount=10000)
        assert not r.passed
        assert "exceeds" in r.reason.lower()

    # 日亏损

    def test_daily_loss_pass(self):
        r = self.engine.check_daily_loss(
            "user1", daily_pnl=-2000, total_capital=100000,
            regime=MarketRegime.TRENDING_UP)
        assert r.passed

    def test_daily_loss_exceeded(self):
        r = self.engine.check_daily_loss(
            "user1", daily_pnl=-8000, total_capital=100000,
            regime=MarketRegime.TRENDING_UP)
        assert not r.passed

    def test_daily_loss_profit_always_pass(self):
        r = self.engine.check_daily_loss(
            "user1", daily_pnl=5000, total_capital=100000,
            regime=MarketRegime.TRENDING_UP)
        assert r.passed

    # 相关性

    def test_correlation_empty_pool(self):
        r = self.engine.check_correlation(
            [0.01, -0.02, 0.03], {}, MarketRegime.TRENDING_UP)
        assert r.passed

    def test_correlation_low(self):
        import random
        random.seed(1)
        r = self.engine.check_correlation(
            [random.gauss(0, 0.01) for _ in range(50)],
            {"s1": [random.gauss(0, 0.01) for _ in range(50)]},
            MarketRegime.TRENDING_UP,
        )
        assert r.passed

    def test_correlation_high(self):
        rets = [0.01 * i for i in range(50)]
        r = self.engine.check_correlation(
            rets,
            {"s1": [0.01 * i + 0.001 for i in range(50)]},
            MarketRegime.TRENDING_UP,
        )
        # 高度相关的序列
        assert not r.passed

    # 全链路

    def test_full_check_pass(self):
        r = self.engine.full_check(
            regime=MarketRegime.TRENDING_UP,
            strategy_type="ma_cross",
            sharpe_oos=1.5,
            total_capital=100000,
            current_position=10000,
            new_amount=5000,
            strategy_position=0,
            daily_pnl=-1000,
            user_id="u1",
        )
        assert r.passed
        assert r.checks.get("all") is True

    def test_full_check_fail_at_entry(self):
        r = self.engine.full_check(
            regime=MarketRegime.TRENDING_DOWN,
            strategy_type="grid",
            sharpe_oos=2.0,
            total_capital=100000,
            current_position=0,
            new_amount=1000,
            strategy_position=0,
            daily_pnl=0,
            user_id="u1",
        )
        assert not r.passed
        assert "not allowed" in r.reason.lower()
