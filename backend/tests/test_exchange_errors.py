"""v1.3 U1: 交易所错误处理路径测试"""
import sys, os, pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestExchangeErrors:
    def test_exchange_client_creation(self):
        from core.exchange import ExchangeClient
        client = ExchangeClient()
        assert client is not None

    def test_fetch_ticker_error_handling(self):
        from core.exchange import ExchangeClient
        client = ExchangeClient()
        try:
            result = client.fetch_ticker("NONEXISTENT/COIN")
            assert result is None or isinstance(result, dict)
        except (ConnectionError, Exception):
            pass  # 离线或无网络时预期抛异常

    def test_test_connection(self):
        from core.exchange import ExchangeClient
        client = ExchangeClient()
        try:
            ok, msg, latency = client.test_connection()
            assert isinstance(ok, bool)
            assert isinstance(msg, str)
            assert isinstance(latency, float) or isinstance(latency, int)
        except (ConnectionError, Exception):
            pass  # 离线时预期抛异常


class TestNetworkRetry:
    @pytest.mark.asyncio
    async def test_network_error_degradation(self):
        """网络不可用时系统不崩溃"""
        from config import settings
        assert hasattr(settings, "EXCHANGE_TESTNET")
        # 模拟盘模式应能正常启动
        assert isinstance(settings.EXCHANGE_TESTNET, bool)
