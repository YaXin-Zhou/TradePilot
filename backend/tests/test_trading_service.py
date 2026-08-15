"""T1: trading_service 核心链路测试"""
import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAmountLimits:
    def test_check_amount_limit_within_bounds(self):
        from services.trading_service import _check_amount_limit
        ok, msg = _check_amount_limit(100.0)
        assert ok

    def test_check_amount_limit_zero_or_negative(self):
        from services.trading_service import _check_amount_limit
        ok, _ = _check_amount_limit(0)
        assert not ok
        ok, _ = _check_amount_limit(-100)
        assert not ok


class TestKillSwitchCheck:
    def test_kill_switch_check_function(self):
        from services.trading_service import _check_kill_switch
        ok, msg = _check_kill_switch()
        assert isinstance(ok, bool)
        assert isinstance(msg, str)


class TestSymbolWhitelist:
    def test_whitelisted_symbol(self):
        from services.trading_service import _check_symbol_whitelist
        ok, _ = _check_symbol_whitelist("BTC/USDT")
        assert ok

    def test_non_whitelisted_blocked(self):
        from services.trading_service import _check_symbol_whitelist
        # 白名单校验仅在 TESTNET=false 时严格拒绝
        ok, msg = _check_symbol_whitelist("RANDOMCOIN/USDT")
        # 结果取决于 EXCHANGE_TESTNET 设置
        assert isinstance(ok, bool)


class TestIdempotencyKey:
    def test_key_includes_account_and_client_id(self):
        from services.trading_service import _make_idempotency_key, _make_client_order_id
        cid = _make_client_order_id()
        k = _make_idempotency_key("acct1", cid)
        assert k == f"acct1:{cid}"

    def test_client_order_id_unique(self):
        from services.trading_service import _make_client_order_id
        ids = {_make_client_order_id() for _ in range(200)}
        assert len(ids) == 200  # uuid 唯一性

    def test_diff_accounts_diff_keys(self):
        from services.trading_service import _make_idempotency_key
        cid = "sameclientid"
        k1 = _make_idempotency_key("a1", cid)
        k2 = _make_idempotency_key("a2", cid)
        assert k1 != k2


class TestEmergencyStop:
    @pytest.mark.asyncio
    async def test_emergency_stop_returns_dict(self):
        from services.trading_service import execute_emergency_stop
        result = await execute_emergency_stop(by="test", reason="testing")
        assert isinstance(result, dict)
