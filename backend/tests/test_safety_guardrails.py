"""v2.1: 策略级风控测试 — 频率/连续亏损/手动风控/默认放行"""
import sys, os, pytest, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestStrategyFrequency:
    def test_first_order_allowed(self):
        from services.trading_service import _check_strategy_frequency, _order_timestamps
        _order_timestamps.clear()
        ok, _ = _check_strategy_frequency("strat_a", max_per_minute=5)
        assert ok

    def test_frequency_exceeds_limit(self):
        from services.trading_service import _check_strategy_frequency, _order_timestamps
        _order_timestamps.clear()
        now = time.time()
        _order_timestamps["strat_b"] = [now - i for i in range(5)]
        ok, msg = _check_strategy_frequency("strat_b", max_per_minute=5)
        assert not ok
        assert "5" in msg

    def test_frequency_respects_configured_limit(self):
        from services.trading_service import _check_strategy_frequency, _order_timestamps
        _order_timestamps.clear()
        now = time.time()
        _order_timestamps["strat_c"] = [now - i for i in range(3)]
        # 阈值=5，当前只有3条，应该通过
        ok, _ = _check_strategy_frequency("strat_c", max_per_minute=5)
        assert ok


class TestEnhancedRiskCheckDefaults:
    """默认风控全放行"""

    @pytest.mark.asyncio
    async def test_manual_default_no_limits(self):
        from services.trading_service import _enhanced_risk_check
        ok, msg = await _enhanced_risk_check(
            "user1", "BTC/USDT", "buy", 1.0,
            source="manual", skip_cold_start=True,
        )
        assert ok

    @pytest.mark.asyncio
    async def test_strategy_default_no_limits(self):
        from services.trading_service import _enhanced_risk_check
        ok, msg = await _enhanced_risk_check(
            "user1", "BTC/USDT", "buy", 1.0,
            source="strategy", strategy_id="test_s",
            skip_cold_start=True,
        )
        assert ok

    @pytest.mark.asyncio
    async def test_emergency_allows_sell(self):
        from services.trading_service import _enhanced_risk_check
        ok, msg = await _enhanced_risk_check(
            "user1", "BTC/USDT", "sell", 100.0,
            source="emergency",
        )
        assert ok


class TestStrategyRiskLimits:
    """策略风控生效时检查"""

    @pytest.mark.asyncio
    async def test_max_order_blocked(self):
        from services.trading_service import _enhanced_risk_check
        risk = {"enabled": True, "max_order_usdt": 50}
        ok, msg = await _enhanced_risk_check(
            "user1", "BTC/USDT", "buy", 100.0,
            source="strategy", strategy_id="test_limit",
            strategy_risk=risk, skip_cold_start=True,
        )
        assert not ok

    @pytest.mark.asyncio
    async def test_max_order_allowed(self):
        from services.trading_service import _enhanced_risk_check
        risk = {"enabled": True, "max_order_usdt": 50}
        ok, msg = await _enhanced_risk_check(
            "user1", "BTC/USDT", "buy", 10.0,
            source="strategy", strategy_id="test_limit2",
            strategy_risk=risk, skip_cold_start=True,
        )
        assert ok

    @pytest.mark.asyncio
    async def test_symbol_whitelist(self):
        from services.trading_service import _enhanced_risk_check
        risk = {"enabled": True, "allowed_symbols": ["BTC/USDT"]}
        ok, _ = await _enhanced_risk_check(
            "user1", "BTC/USDT", "buy", 10.0,
            source="strategy", strategy_id="test_wl",
            strategy_risk=risk, skip_cold_start=True,
        )
        assert ok

    @pytest.mark.asyncio
    async def test_symbol_whitelist_blocked(self):
        from services.trading_service import _enhanced_risk_check
        risk = {"enabled": True, "allowed_symbols": ["BTC/USDT"]}
        ok, msg = await _enhanced_risk_check(
            "user1", "ETH/USDT", "buy", 10.0,
            source="strategy", strategy_id="test_wl2",
            strategy_risk=risk, skip_cold_start=True,
        )
        assert not ok
