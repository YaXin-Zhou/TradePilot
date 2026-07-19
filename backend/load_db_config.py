"""Load exchange config from DB on startup (with decryption)"""
import json
from sqlalchemy import select
from db.database import async_session
from db.models import AppConfig
from core.crypto import decrypt


async def load_exchange_config():
    try:
        async with async_session() as session:
            r = await session.execute(
                select(AppConfig).where(AppConfig.key == "exchange_settings")
            )
            row = r.scalar_one_or_none()
            if row and row.value:
                data = json.loads(row.value)
                # 优先读取加密字段，回退到旧版明文字段（兼容）
                api_key = decrypt(data.get("api_key_enc", "")) or data.get("api_key", "")
                secret = decrypt(data.get("secret_enc", "")) or data.get("secret", "")
                passphrase = decrypt(data.get("passphrase_enc", "")) or data.get("passphrase", "")
                if api_key and secret:
                    from core.exchange import ExchangeClient
                    from config import settings as _s
                    client = ExchangeClient(
                        exchange_name=_s.EXCHANGE_NAME,
                        api_key=api_key,
                        secret=secret,
                        passphrase=passphrase,
                        testnet=data.get("testnet", True),
                    )
                    import core.exchange as exmod
                    exmod.shared_exchange = client
                    client._last_attempt = 0
                    print("Loaded exchange config from DB (will reconnect on next request)")
    except Exception as e:
        print(f"Load config skipped: {e}")
