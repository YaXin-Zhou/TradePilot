"""Load exchange config from DB on startup"""
import json
from sqlalchemy import select
from db.database import async_session
from db.models import AppConfig


async def load_exchange_config():
    try:
        async with async_session() as session:
            r = await session.execute(
                select(AppConfig).where(AppConfig.key == "exchange_settings")
            )
            row = r.scalar_one_or_none()
            if row and row.value:
                data = json.loads(row.value)
                if data.get("api_key") and data.get("secret"):
                    from core.exchange import ExchangeClient
                    from config import settings as _s
                    client = ExchangeClient(
                        exchange_name=_s.EXCHANGE_NAME,
                        api_key=data["api_key"],
                        secret=data["secret"],
                        passphrase=data.get("passphrase", ""),
                        testnet=data.get("testnet", True),
                    )
                    import core.exchange as exmod
                    exmod.shared_exchange = client
                    client._last_attempt = 0
                    print("Loaded exchange config from DB (will reconnect on next request)")
    except Exception as e:
        print(f"Load config skipped: {e}")
