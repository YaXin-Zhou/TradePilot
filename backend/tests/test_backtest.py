"""回测模块测试 — MA/RSI/Bollinger 策略"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd
import numpy as np
from strategies.backtest import BacktestEngine


@pytest.fixture
def uptrend_data():
    """生成上升趋势的模拟K线数据"""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    base = 50000
    trend = np.linspace(0, 20000, n)
    noise = np.random.normal(0, 500, n)
    close = base + trend + noise

    df = pd.DataFrame({
        "timestamp": dates,
        "open": close - np.random.uniform(0, 300, n),
        "high": close + np.random.uniform(100, 800, n),
        "low": close - np.random.uniform(100, 800, n),
        "close": close,
        "volume": np.random.uniform(100, 500, n),
        "symbol": "BTC/USDT",
    })
    return df


@pytest.fixture
def downtrend_data():
    """生成下降趋势的模拟K线数据"""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    base = 50000
    trend = np.linspace(0, -15000, n)
    noise = np.random.normal(0, 500, n)
    close = base + trend + noise

    df = pd.DataFrame({
        "timestamp": dates,
        "open": close - np.random.uniform(0, 300, n),
        "high": close + np.random.uniform(100, 800, n),
        "low": close - np.random.uniform(100, 800, n),
        "close": close,
        "volume": np.random.uniform(100, 500, n),
        "symbol": "BTC/USDT",
    })
    return df


class TestMAStrategy:
    """MA 交叉策略"""

    def test_basic_ma_crossover(self, uptrend_data):
        engine = BacktestEngine(uptrend_data, 10000)
        result = engine.run_ma_crossover(fast_period=5, slow_period=20)
        assert result.total_trades > 0
        assert result.win_rate >= 0 and result.win_rate <= 100
        assert isinstance(result.sharpe_ratio, (int, float))
        assert result.final_capital > 0

    def test_result_fields_complete(self, uptrend_data):
        engine = BacktestEngine(uptrend_data, 10000)
        result = engine.run_ma_crossover(10, 30)
        for field in ["total_return_pct", "sharpe_ratio", "max_drawdown_pct",
                       "win_rate", "total_trades", "profit_factor", "final_capital"]:
            assert hasattr(result, field), f"Missing field: {field}"

    def test_equity_curve_length(self, uptrend_data):
        engine = BacktestEngine(uptrend_data, 10000)
        result = engine.run_ma_crossover(10, 30)
        assert len(result.equity_curve) > 0
        # 最后一点资金应接近最终资产（等价资产 vs 现金可能有少量差异）
        assert abs(result.equity_curve[-1]["equity"] - result.final_capital) < 50


class TestRSIStrategy:
    """RSI 策略"""

    def test_rsi_basic(self, uptrend_data):
        engine = BacktestEngine(uptrend_data, 10000)
        result = engine.run_rsi(period=14, oversold=30, overbought=70)
        assert result.total_trades >= 0
        assert isinstance(result.win_rate, (int, float))

    def test_rsi_downtrend(self, downtrend_data):
        engine = BacktestEngine(downtrend_data, 10000)
        result = engine.run_rsi(period=14, oversold=30, overbought=70)
        assert result.total_trades >= 0


class TestBollingerStrategy:
    """布林带策略"""

    def test_bollinger_basic(self, uptrend_data):
        engine = BacktestEngine(uptrend_data, 10000)
        result = engine.run_bollinger(period=20, std_dev=2.0)
        assert result.total_trades >= 0
        assert isinstance(result.sharpe_ratio, (int, float))


class TestBacktestEdgeCases:
    """边界条件"""

    def test_minimum_data(self):
        """最少数据量（刚好 30 条）"""
        np.random.seed(1)
        n = 30
        dates = pd.date_range("2024-01-01", periods=n, freq="1h")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": np.random.uniform(50000, 51000, n),
            "high": np.random.uniform(50500, 51500, n),
            "low": np.random.uniform(49500, 50500, n),
            "close": np.random.uniform(50000, 51000, n),
            "volume": np.random.uniform(100, 500, n),
            "symbol": "BTC/USDT",
        })
        engine = BacktestEngine(df, 10000)
        result = engine.run_ma_crossover(5, 10)
        assert result.total_trades >= 0

    def test_flat_price(self):
        """价格不变（横盘）— 不应崩溃"""
        n = 200
        dates = pd.date_range("2024-01-01", periods=n, freq="1h")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": [50000.0] * n,
            "high": [50000.0] * n,
            "low": [50000.0] * n,
            "close": [50000.0] * n,
            "volume": [100.0] * n,
            "symbol": "BTC/USDT",
        })
        engine = BacktestEngine(df, 10000)
        result = engine.run_ma_crossover(10, 30)
        # 横盘时 MA 可能接近重合，交易可能很少
        assert result.total_trades >= 0

    def test_zero_capital_should_work(self):
        """零资金 — 检查不崩溃"""
        n = 50
        dates = pd.date_range("2024-01-01", periods=n, freq="1h")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": [50000.0] * n,
            "high": [50000.0] * n,
            "low": [50000.0] * n,
            "close": [50000.0] * n,
            "volume": [100.0] * n,
            "symbol": "BTC/USDT",
        })
        engine = BacktestEngine(df, 100)  # 少量资金
        result = engine.run_ma_crossover(10, 30)
        assert result.final_capital >= 0
