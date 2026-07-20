"""T1: exchange_registry 多租户实例池测试"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestExchangeRegistry:
    def test_registry_class_exists(self):
        from core.exchange_registry import ExchangeRegistry
        reg = ExchangeRegistry()
        assert reg is not None

    @pytest.mark.asyncio
    async def test_get_returns_exchange_instance(self):
        from core.exchange_registry import ExchangeRegistry
        reg = ExchangeRegistry()
        instance = await reg.get("default")
        assert instance is not None
        assert hasattr(instance, "fetch_ticker")

    def test_testnet_flag_from_settings(self):
        from config import settings
        assert hasattr(settings, "EXCHANGE_TESTNET")
        assert isinstance(settings.EXCHANGE_TESTNET, bool)
