"""v1.3 U2: GridEngine 全覆盖测试"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestComputeLines:
    def test_grid_lines_count(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig(
            symbol="BTC/USDT", lower_price=80000, upper_price=90000,
            grid_count=10, investment_total=2000
        )
        lines = GridEngine.compute_lines(config)
        assert len(lines) == 11  # grid_count + 1
        assert lines[0] == 80000.0
        assert lines[-1] == 90000.0

    def test_grid_spacing(self):
        from services.grid_engine import GridConfig
        config = GridConfig(
            symbol="BTC/USDT", lower_price=80000, upper_price=90000,
            grid_count=10, investment_total=2000
        )
        assert config.grid_spacing == 1000.0


class TestDetectCross:
    def test_price_at_lower_bound(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig("BTC/USDT", 80000, 90000, 10, 2000)
        lines = GridEngine.compute_lines(config)
        crossed = GridEngine.detect_cross(80000.0, lines)
        assert len(crossed) > 0

    def test_price_at_upper_bound(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig("BTC/USDT", 80000, 90000, 10, 2000)
        lines = GridEngine.compute_lines(config)
        crossed = GridEngine.detect_cross(90000.0, lines)
        assert len(crossed) > 0

    def test_price_in_middle(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig("BTC/USDT", 80000, 90000, 10, 2000)
        lines = GridEngine.compute_lines(config)
        crossed = GridEngine.detect_cross(85000.0, lines)
        assert len(crossed) >= 1


class TestBuySellLogic:
    def test_empty_state_should_buy(self):
        from services.grid_engine import GridState, GridEngine
        state = GridState()
        assert GridEngine.should_place_buy(0, state)

    def test_already_has_buy_should_not_buy(self):
        from services.grid_engine import GridState, GridEngine
        state = GridState()
        state.buy_orders[0] = "order-001"
        assert not GridEngine.should_place_buy(0, state)

    def test_sell_price_is_above_buy(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig("BTC/USDT", 80000, 90000, 10, 2000)
        sell_price = GridEngine.get_sell_price(0, config)
        assert sell_price > config.lower_price


class TestStopLoss:
    def test_no_stop_loss_when_profitable(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig("BTC/USDT", 80000, 90000, 10, 2000, stop_loss_pct=10)
        assert not GridEngine.should_stop_loss(80000, 85000, config)

    def test_trigger_stop_loss(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig("BTC/USDT", 80000, 90000, 10, 2000, stop_loss_pct=10)
        assert GridEngine.should_stop_loss(80000, 70000, config)

    def test_zero_entry_no_stop_loss(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig("BTC/USDT", 80000, 90000, 10, 2000, stop_loss_pct=10)
        assert not GridEngine.should_stop_loss(0, 70000, config)


class TestOutOfRange:
    def test_price_below_range(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig("BTC/USDT", 80000, 90000, 10, 2000)
        assert GridEngine.is_price_out_of_range(70000, config)

    def test_price_within_range(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig("BTC/USDT", 80000, 90000, 10, 2000)
        assert not GridEngine.is_price_out_of_range(85000, config)

    def test_price_above_range(self):
        from services.grid_engine import GridConfig, GridEngine
        config = GridConfig("BTC/USDT", 80000, 90000, 10, 2000)
        assert GridEngine.is_price_out_of_range(100000, config)
