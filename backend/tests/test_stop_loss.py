"""StopLoss 测试"""
import time
import pytest
from services.stop_loss import (
    StopLossManager, StopLossConfig, StopReason, StopLossResult,
)


class TestStopLossConfig:
    def test_defaults(self):
        c = StopLossConfig()
        assert c.hard_stop_pct == 8.0
        assert c.trailing_stop_pct == 3.0
        assert c.time_stop_hours == 72
        assert c.atr_multiplier == 2.0

    def test_from_policy(self):
        from services.risk_engine import RiskPolicy
        from services.regime_detector import MarketRegime
        p = RiskPolicy(
            regime=MarketRegime.TRENDING_UP,
            stop_loss_pct=10.0,
            trailing_stop_pct=4.0,
            time_stop_hours=48,
            atr_stop_multiplier=3.0,
        )
        c = StopLossConfig.from_policy(p)
        assert c.hard_stop_pct == 10.0
        assert c.trailing_stop_pct == 4.0
        assert c.time_stop_hours == 48
        assert c.atr_multiplier == 3.0


class TestHardStop:
    """硬止损"""

    def test_not_triggered(self):
        cfg = StopLossConfig(hard_stop_pct=8.0, trailing_stop_pct=10.0)
        mgr = StopLossManager(cfg, entry_price=100)
        mgr.update_price(95)  # -5%, 未到 hard(8%) 或 trailing(10%)
        r = mgr.check()
        assert not r.triggered

    def test_triggered(self):
        mgr = StopLossManager(StopLossConfig(hard_stop_pct=8.0), entry_price=100)
        mgr.update_price(90)  # -10%
        r = mgr.check()
        assert r.triggered
        assert r.reason == StopReason.HARD_STOP
        assert r.loss_pct > 8.0

    def test_exact_threshold(self):
        mgr = StopLossManager(StopLossConfig(hard_stop_pct=8.0), entry_price=100)
        mgr.update_price(92)  # exactly -8%
        r = mgr.check()
        assert r.triggered


class TestTrailingStop:
    """移动止损"""

    def test_not_triggered_after_rise(self):
        mgr = StopLossManager(StopLossConfig(trailing_stop_pct=3.0), entry_price=100)
        mgr.update_price(105)   # 上涨 5%
        mgr.update_price(103)   # 从最高回撤 ~1.9%
        r = mgr.check()
        assert not r.triggered

    def test_triggered_after_drawdown(self):
        mgr = StopLossManager(StopLossConfig(trailing_stop_pct=3.0), entry_price=100)
        mgr.update_price(110)   # 最高 110
        mgr.update_price(106)   # 回撤 4/110 = 3.6% > 3%
        r = mgr.check()
        assert r.triggered
        assert r.reason == StopReason.TRAILING_STOP

    def test_highest_only_updates_up(self):
        mgr = StopLossManager(StopLossConfig(trailing_stop_pct=5.0), entry_price=100)
        mgr.update_price(110)
        mgr.update_price(95)   # 不更新最高
        assert mgr.highest_price == 110


class TestTimeStop:
    """时间止损"""

    def test_not_triggered_profit(self):
        """盈利持仓不触发时间止损"""
        mgr = StopLossManager(
            StopLossConfig(time_stop_hours=1), entry_price=100,
            entry_time=time.time() - 4000,  # > 1h
        )
        mgr.update_price(105)   # +5% 盈利
        r = mgr.check()
        # 可能触发 trailing，但不触发 time（因为盈利）
        if r.triggered:
            assert r.reason != StopReason.TIME_STOP

    def test_not_triggered_short_time(self):
        mgr = StopLossManager(
            StopLossConfig(time_stop_hours=1000), entry_price=100,
        )
        mgr.update_price(95)
        r = mgr.check()
        if r.triggered:
            assert r.reason != StopReason.TIME_STOP


class TestATRStop:
    """ATR 波动率止损"""

    def test_not_triggered_no_atr(self):
        mgr = StopLossManager(StopLossConfig(), entry_price=100)
        mgr.update_price(90)
        r = mgr.check()
        # 应该触发 hard stop，但不会触发 ATR stop
        if r.triggered:
            assert r.reason in (StopReason.HARD_STOP, StopReason.TIME_STOP)

    def test_triggered_with_atr(self):
        mgr = StopLossManager(
            StopLossConfig(atr_multiplier=2.0), entry_price=100, atr_value=10)
        mgr.update_price(78)   # 跌幅 22 > 2×ATR=20
        r = mgr.check()
        assert r.triggered
        # ATR 止损或者硬止损都会触发

    def test_atr_not_triggered_within_range(self):
        cfg = StopLossConfig(hard_stop_pct=20.0, trailing_stop_pct=20.0, atr_multiplier=2.0)
        mgr = StopLossManager(cfg, entry_price=100, atr_value=10)
        mgr.update_price(85)   # 跌 15 < hard(20) 和 ATR(20) 和 trailing(20)
        r = mgr.check()
        assert not r.triggered


class TestStopLossResult:
    def test_to_dict(self):
        r = StopLossResult(
            triggered=True, reason=StopReason.HARD_STOP,
            stop_price=92, current_price=90, entry_price=100,
            loss_pct=10.0, message="Hard stop",
        )
        d = r.to_dict()
        assert d["triggered"] is True
        assert d["reason"] == "hard_stop"
        assert d["loss_pct"] == 10.0

    def test_not_triggered(self):
        r = StopLossResult(triggered=False, entry_price=100, current_price=99)
        d = r.to_dict()
        assert d["triggered"] is False
        assert d["reason"] == "none"


class TestReset:
    def test_reset_clears_state(self):
        mgr = StopLossManager(StopLossConfig(hard_stop_pct=8.0), entry_price=100)
        mgr.update_price(90)
        assert mgr.check().triggered

        mgr.reset(entry_price=90)
        assert not mgr.check().triggered
        assert mgr.entry_price == 90
        assert mgr.highest_price == 90
