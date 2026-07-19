"""Load exchange config from DB on startup (with decryption)

Phase 8.1: 支持双配置（模拟盘/实盘），读取 active 模式对应配置。
向后兼容：自动迁移旧版单配置格式。
"""
import json
from sqlalchemy import select
from db.database import async_session
from db.models import AppConfig
from core.crypto import decrypt
from core.logger import log
from config import settings as _s


def _empty_creds(testnet: bool) -> dict:
    return {
        "api_key_enc": "",
        "secret_enc": "",
        "passphrase_enc": "",
        "testnet": testnet,
    }


async def load_exchange_config():
    """启动时从 DB 加载激活模式的交易所配置，重建 shared_exchange。"""
    try:
        async with async_session() as session:
            r = await session.execute(
                select(AppConfig).where(AppConfig.key == "exchange_settings")
            )
            row = r.scalar_one_or_none()
            if not row or not row.value:
                log.info("No exchange config in DB, using .env defaults")
                return
            try:
                data = json.loads(row.value)
            except json.JSONDecodeError:
                log.warning("DB exchange_settings JSON invalid, using .env defaults")
                return

        # 向后兼容：旧版单配置格式（有 api_key_enc 但没有 active 字段）
        if "active" not in data and ("api_key_enc" in data or "api_key" in data):
            log.info("Migrating legacy single-config to dual-config (as testnet)")
            old_testnet = data.get("testnet", True)
            if old_testnet:
                data = {
                    "active": "testnet",
                    "testnet": {
                        "api_key_enc": data.get("api_key_enc", ""),
                        "secret_enc": data.get("secret_enc", ""),
                        "passphrase_enc": data.get("passphrase_enc", ""),
                        "testnet": True,
                    },
                    "live": _empty_creds(False),
                }
            else:
                data = {
                    "active": "live",
                    "testnet": _empty_creds(True),
                    "live": {
                        "api_key_enc": data.get("api_key_enc", ""),
                        "secret_enc": data.get("secret_enc", ""),
                        "passphrase_enc": data.get("passphrase_enc", ""),
                        "testnet": False,
                    },
                }

        data.setdefault("active", "testnet")
        data.setdefault("testnet", _empty_creds(True))
        data.setdefault("live", _empty_creds(False))

        active = data.get("active", "testnet")
        creds = data.get(active, {})
        api_key = decrypt(creds.get("api_key_enc", "")) or creds.get("api_key", "")
        secret = decrypt(creds.get("secret_enc", "")) or creds.get("secret", "")
        passphrase = decrypt(creds.get("passphrase_enc", "")) or creds.get("passphrase", "")

        if api_key and secret:
            from core.exchange import ExchangeClient
            import core.exchange as exmod
            testnet = (active == "testnet")
            client = ExchangeClient(
                exchange_name=_s.EXCHANGE_NAME,
                api_key=api_key,
                secret=secret,
                passphrase=passphrase,
                testnet=testnet,
            )
            exmod.shared_exchange = client
            client._last_attempt = 0
            _s.EXCHANGE_TESTNET = testnet  # 同步全局设置
            mode_label = "TESTNET" if testnet else "LIVE"
            log.info(f"Exchange config loaded from DB (active={mode_label})")
        else:
            log.info(f"Exchange config in DB has no {'testnet' if active=='testnet' else 'live'} creds, using .env defaults")
    except Exception as e:
        log.warning(f"Load exchange config from DB skipped: {e}")


async def load_deepseek_config():
    """启动时从 DB 加载 DeepSeek API Key，覆盖 settings.DEEPSEEK_API_KEY。

    若 DB 无配置则保留 .env 的值。所有 DeepSeek 使用方
    (ai_service / ai_iterator / news_sentiment / ai_heartbeat) 均从
    settings.DEEPSEEK_API_KEY 读取，此处统一注入。
    """
    try:
        async with async_session() as session:
            r = await session.execute(
                select(AppConfig).where(AppConfig.key == "deepseek_settings")
            )
            row = r.scalar_one_or_none()
            if not row or not row.value:
                log.info("No DeepSeek config in DB, using .env DEEPSEEK_API_KEY")
                return
            try:
                data = json.loads(row.value)
            except json.JSONDecodeError:
                log.warning("DB deepseek_settings JSON invalid, using .env defaults")
                return

        api_key_enc = data.get("api_key_enc", "")
        api_key = decrypt(api_key_enc) if api_key_enc else ""
        if api_key:
            _s.DEEPSEEK_API_KEY = api_key
            log.info("DeepSeek API Key loaded from DB")
        else:
            log.info("DeepSeek config in DB has no key, using .env defaults")
    except Exception as e:
        log.warning(f"Load DeepSeek config from DB skipped: {e}")
