"""AI 策略引擎测试 — 响应解析容错"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from strategies.ai_strategy import AIStrategyEngine
from strategies.base import SignalType


@pytest.fixture
def engine():
    return AIStrategyEngine(api_key="test_key")


class TestResponseParsing:
    """JSON 解析容错"""

    def make_response(self, content: str) -> dict:
        return {"choices": [{"message": {"content": content}}]}

    def test_valid_buy_signal(self, engine):
        raw = self.make_response(
            '{"signal": "buy", "confidence": 0.85, "reason": "RSI oversold", '
            '"strategy_type": "rsi", "strategy_params": {"period": 14, "oversold": 30, "overbought": 70}}'
        )
        signal, info = engine._parse_response(raw, {"last": 50000})
        assert signal.type == SignalType.BUY
        assert signal.confidence == 0.85
        assert signal.reason == "RSI oversold"
        assert info["type"] == "rsi"

    def test_valid_sell_signal(self, engine):
        raw = self.make_response(
            '{"signal": "sell", "confidence": 0.7, "reason": "MACD bearish", '
            '"strategy_type": "ma_crossover", "strategy_params": {"fast": 5, "slow": 20}}'
        )
        signal, info = engine._parse_response(raw, {"last": 60000})
        assert signal.type == SignalType.SELL
        assert info["type"] == "ma_crossover"

    def test_hold_signal(self, engine):
        raw = self.make_response(
            '{"signal": "hold", "confidence": 0.3, "reason": "No clear signal", '
            '"strategy_type": "", "strategy_params": {}}'
        )
        signal, info = engine._parse_response(raw, {"last": 50000})
        assert signal.type == SignalType.HOLD
        assert signal.confidence == 0.3

    def test_strong_buy(self, engine):
        raw = self.make_response(
            '{"signal": "strong_buy", "confidence": 0.95, "reason": "Multiple confirmations", '
            '"strategy_type": "bollinger", "strategy_params": {"period": 20, "std_dev": 2.0}}'
        )
        signal, info = engine._parse_response(raw, {"last": 50000})
        assert signal.type == SignalType.STRONG_BUY

    def test_json_with_extra_text(self, engine):
        """JSON 被其他文本包裹 — 用正则提取"""
        raw = self.make_response(
            'Here is my analysis:\n```json\n'
            '{"signal": "buy", "confidence": 0.8, "reason": "RSI divergence", '
            '"strategy_type": "rsi", "strategy_params": {"period": 14, "oversold": 28, "overbought": 72}}\n'
            '```\nPlease review.'
        )
        signal, info = engine._parse_response(raw, {"last": 50000})
        assert signal.type == SignalType.BUY
        assert info["type"] == "rsi"

    def test_invalid_json_graceful_fallback(self, engine):
        """无效 JSON — 不应崩溃，返回 HOLD"""
        raw = self.make_response("Sorry, I cannot analyze this market.")
        signal, info = engine._parse_response(raw, {"last": 50000})
        assert signal.type == SignalType.HOLD
        assert signal.reason == "Parse failed"

    def test_missing_signal_field(self, engine):
        """缺少 signal 字段 — 默认 HOLD"""
        raw = self.make_response('{"confidence": 0.5, "reason": "test"}')
        signal, info = engine._parse_response(raw, {"last": 50000})
        assert signal.type == SignalType.HOLD

    def test_empty_response(self, engine):
        """空响应 — 默认 HOLD"""
        raw = self.make_response("")
        signal, info = engine._parse_response(raw, {"last": 50000})
        assert signal.type == SignalType.HOLD

    def test_unknown_signal_type_defaults_to_hold(self, engine):
        """未识别的 signal — 默认 HOLD"""
        raw = self.make_response(
            '{"signal": "unknown_type", "confidence": 0.5, "reason": "test", '
            '"strategy_type": "", "strategy_params": {}}'
        )
        signal, info = engine._parse_response(raw, {"last": 50000})
        assert signal.type == SignalType.HOLD
