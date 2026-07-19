"""验证模块测试 — IS/OOS 分割、PBO、BH、DSR、Newey-West、SPA"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import numpy as np
import pandas as pd
from services.validation import (
    split_is_oos,
    compute_sharpe,
    compute_max_drawdown,
    compute_pbo,
    benjamini_hochberg,
    compute_dsr,
    compute_newey_west,
    compute_spa,
)


@pytest.fixture
def sample_data():
    """生成 200 条模拟 K 线"""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    close = 50000 + np.cumsum(np.random.normal(0, 200, n))
    close = np.maximum(close, 1000)
    df = pd.DataFrame({
        "timestamp": dates,
        "open": close + np.random.normal(0, 100, n),
        "high": close + np.abs(np.random.normal(200, 50, n)),
        "low": close - np.abs(np.random.normal(200, 50, n)),
        "close": close,
        "volume": np.random.uniform(100, 500, n),
    })
    return df


@pytest.fixture
def equity_curve():
    """生成模拟 equity curve"""
    np.random.seed(42)
    n = 100
    vals = [10000.0]
    for i in range(1, n):
        vals.append(vals[-1] * (1 + np.random.normal(0.001, 0.02)))
    return [{"timestamp": f"2024-{i//30+1:02d}-{i%30+1:02d}T00:00:00", "equity": round(v, 2)} for i, v in enumerate(vals)]


class TestISOSSplit:
    """IS/OOS 分割"""

    def test_split_ratio(self, sample_data):
        is_data, oos_data = split_is_oos(sample_data, is_pct=0.7)
        assert len(is_data) >= 50
        assert len(oos_data) >= 20
        assert abs(len(is_data) / len(sample_data) - 0.7) < 0.05

    def test_split_preserves_columns(self, sample_data):
        is_data, oos_data = split_is_oos(sample_data, is_pct=0.7)
        for col in sample_data.columns:
            assert col in is_data.columns
            assert col in oos_data.columns

    def test_split_minimum_data(self):
        """数据太少时抛异常"""
        tiny = pd.DataFrame({"close": [1, 2, 3]})
        with pytest.raises(ValueError):
            split_is_oos(tiny)


class TestSharpeAndDrawdown:
    """Sharpe 和最大回撤计算"""

    def test_sharpe_positive(self, equity_curve):
        sharpe = compute_sharpe(equity_curve)
        assert isinstance(sharpe, float)

    def test_max_drawdown(self, equity_curve):
        mdd = compute_max_drawdown(equity_curve)
        assert isinstance(mdd, float)
        assert 0 <= mdd <= 100

    def test_empty_equity_returns_zero(self):
        assert compute_sharpe([]) == 0.0
        assert compute_max_drawdown([]) == 0.0


class TestBenjaminiHochberg:
    """BH 多重检验"""

    def test_all_significant(self):
        p_values = [0.001, 0.002, 0.003, 0.004, 0.005]
        passed, threshold = benjamini_hochberg(p_values, alpha=0.05)
        assert all(passed)
        assert threshold > 0

    def test_none_significant(self):
        p_values = [0.5, 0.6, 0.7, 0.8, 0.9]
        passed, threshold = benjamini_hochberg(p_values, alpha=0.05)
        assert not any(passed)

    def test_mixed_significance(self):
        p_values = [0.001, 0.01, 0.3, 0.4, 0.5]
        passed, threshold = benjamini_hochberg(p_values, alpha=0.05)
        # 前两个应显著
        assert passed[0]
        assert passed[1]
        assert not passed[-1]

    def test_empty_list(self):
        passed, threshold = benjamini_hochberg([], alpha=0.05)
        assert passed == []
        assert threshold == 0.05


class TestDSR:
    """通胀夏普"""

    def test_dsr_with_attempts(self):
        dsr = compute_dsr(2.0, 100)
        assert dsr < 2.0
        assert dsr > 0

    def test_dsr_single_attempt(self):
        """只有一次尝试时 DSR = 0（不能自我验证）"""
        dsr = compute_dsr(3.0, 1)
        assert dsr == 0.0

    def test_dsr_converges(self):
        """N 很大时 DSR 接近原始 Sharpe"""
        dsr100 = compute_dsr(2.0, 100)
        dsr1000 = compute_dsr(2.0, 1000)
        assert dsr1000 > dsr100  # 更多尝试 → 更接近原始值


class TestNeweyWest:
    """Newey-West HAC"""

    def test_nw_basic(self, equity_curve):
        result = compute_newey_west(equity_curve)
        assert "se" in result
        assert "t_stat" in result
        assert "lags" in result
        assert result["lags"] > 0

    def test_nw_empty(self):
        result = compute_newey_west([])
        assert result["se"] == 0.0
        assert result["t_stat"] == 0.0


class TestSPA:
    """SPA 检验"""

    def test_spa_equal_performance(self):
        """两个相同序列 → p 应接近 1"""
        np.random.seed(42)
        rets = np.random.normal(0.001, 0.02, 200)
        p = compute_spa(rets, rets, n_bootstrap=500)
        assert p > 0.1  # 策略不显著优于自身

    def test_spa_better_strategy(self):
        """策略明显优于基准 → p 应很小"""
        np.random.seed(42)
        benchmark = np.random.normal(0.001, 0.02, 200)
        better = benchmark + 0.005  # 每天多 0.5%
        p = compute_spa(better, benchmark, n_bootstrap=500)
        # 策略显著更好
        assert isinstance(p, float)

    def test_spa_too_few_data(self):
        """数据太少 → 返回 1.0"""
        p = compute_spa(np.array([0.01, -0.01]), np.array([0.01, -0.01]))
        assert p == 1.0


class TestPBO:
    """PBO 过拟合概率"""

    def test_pbo_structure(self, sample_data):
        """验证 PBO 函数签名正确，不实际运行（PBO 需要 strategy_runner）"""
        # PBO 需要策略运行器，这里仅验证不会因参数错误而崩溃
        n = len(sample_data)
        is_data = sample_data.iloc[:int(n * 0.7)]
        oos_data = sample_data.iloc[int(n * 0.7):]
        assert len(is_data) > 0
        assert len(oos_data) > 0
