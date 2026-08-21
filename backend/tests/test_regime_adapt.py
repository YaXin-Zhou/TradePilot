"""regime_adapt 单元测试 — regime × 策略类型权重映射 + fail-closed"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.regime_detector import MarketRegime
from services.regime_adapt import (
    strategy_multiplier, adapt_weights, REGIME_PREFERENCE,
)


class TestStrategyMultiplier:
    def test_trend_prefers_trend_following(self):
        # 趋势市：ma_cross 最匹配（1.0），grid 不兼容（0）
        assert strategy_multiplier(MarketRegime.TRENDING_UP, "ma_cross") == 1.0
        assert strategy_multiplier(MarketRegime.TRENDING_UP, "grid") == 0.0

    def test_range_prefers_mean_reversion(self):
        # 震荡市：rsi/bollinger 最匹配，ma_cross 基本不匹配
        assert strategy_multiplier(MarketRegime.RANGING_LOW_VOL, "rsi") == 1.0
        assert strategy_multiplier(MarketRegime.RANGING_LOW_VOL, "bollinger") == 0.9
        assert strategy_multiplier(MarketRegime.RANGING_LOW_VOL, "ma_cross") == 0.1

    def test_unknown_type_neutral(self):
        assert strategy_multiplier(MarketRegime.TRENDING_UP, "unknown_type") == 0.5


class TestAdaptWeights:
    def test_normalizes_and_filters_incompatible(self):
        strategies = [
            {"strategy_id": "s1", "strategy_type": "ma_cross"},
            {"strategy_id": "s2", "strategy_type": "grid"},
        ]
        weights = adapt_weights(MarketRegime.TRENDING_UP, strategies)
        # grid 在趋势市不兼容（乘 0）→ 被排除，只剩 s1
        assert set(weights.keys()) == {"s1"}
        assert weights["s1"] == pytest.approx(1.0)

    def test_fail_closed_when_all_incompatible(self):
        strategies = [{"strategy_id": "s1", "strategy_type": "grid"}]
        weights = adapt_weights(MarketRegime.TRENDING_UP, strategies)
        # grid 在趋势市乘 0 → 无兼容策略 → fail-closed 空仓
        assert weights == {}

    def test_high_vol_scales_down_exposure(self):
        strategies = [
            {"strategy_id": "s1", "strategy_type": "bollinger"},
            {"strategy_id": "s2", "strategy_type": "rsi"},
        ]
        weights = adapt_weights(MarketRegime.RANGING_HIGH_VOL, strategies)
        # 高波动 regime 总敞口 × 0.5，权重之和 = 0.5
        assert sum(weights.values()) == pytest.approx(0.5)

    def test_base_weights_respected(self):
        strategies = [
            {"strategy_id": "s1", "strategy_type": "ma_cross"},
            {"strategy_id": "s2", "strategy_type": "ma_cross"},
        ]
        weights = adapt_weights(
            MarketRegime.TRENDING_UP, strategies,
            base_weights={"s1": 0.8, "s2": 0.2},
        )
        # 同类型同乘数，归一化后保持 8:2
        assert weights["s1"] == pytest.approx(0.8)
        assert weights["s2"] == pytest.approx(0.2)


class TestPreferenceTableCompleteness:
    def test_all_strategy_types_present_in_all_regimes(self):
        # 偏好表覆盖所有 strategy type，缺失则落入 strategy_multiplier 的默认 0.5
        # 此处只验证表结构完整性（每个 regime 都定义了表）
        assert len(REGIME_PREFERENCE) == 4
        for regime in MarketRegime:
            assert regime in REGIME_PREFERENCE
