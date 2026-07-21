"""v2.0 P5: 交易安全护栏测试 — 冷启动/滑点/频率/连续亏损"""
import sys, os, pytest, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestColdStart:
    def test_cold_start_blocks_during_window(self):
        from services.trading_service import _check_cold_start, _APP_START_TIME
        # 模拟刚启动
        old_start = _APP_START_TIME
        try:
            import services.trading_service as svc
            svc._APP_START_TIME = time.time()
            ok, msg = _check_cold_start()
            assert not ok
            assert "预热" in msg
        finally:
            svc._APP_START_TIME = old_start

    def test_cold_start_allows_after_window(self):
        from services.trading_service import _check_cold_start
        old_start = time.time() - 120  # 2 分钟前
        import services.trading_service as svc
        svc._APP_START_TIME = old_start
        ok, _ = _check_cold_start()
        assert ok


class TestSlippage:
    def test_slippage_within_limit(self):
        from services.trading_service import _check_slippage
        ok, _ = _check_slippage(85100, 85000)
        assert ok

    def test_slippage_exceeds_limit(self):
        from services.trading_service import _check_slippage
        ok, msg = _check_slippage(86000, 85000)
        assert not ok
        assert "滑点" in msg

    def test_slippage_no_market_price(self):
        from services.trading_service import _check_slippage
        ok, _ = _check_slippage(85000, 0)
        assert ok


class TestOrderFrequency:
    def test_first_order_allowed(self):
        from services.trading_service import _check_order_frequency, _order_timestamps
        _order_timestamps.clear()
        ok, _ = _check_order_frequency("test_strat_1")
        assert ok

    def test_frequency_exceeds_limit(self):
        from services.trading_service import _check_order_frequency, _order_timestamps
        _order_timestamps.clear()
        # 填满 10 条记录（模拟 1 分钟内 10 次下单）
        now = time.time()
        _order_timestamps["test_strat_2"] = [now - i for i in range(10)]
        ok, msg = _check_order_frequency("test_strat_2")
        assert not ok
        assert "10" in msg
