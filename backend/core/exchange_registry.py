"""多租户交易所实例池 — 消除全局单例，支持多账户

M2 核心基础设施：按 (tenant_id, account_id) 索引 ccxt 实例。

设计：
  - 从 ExchangeCredential 表加载凭据（AES-256-GCM 解密）
  - 缓存 ExchangeClient 实例，避免重复创建
  - 凭据变更时调用 invalidate() 清除缓存
  - 找不到凭据时 fallback 到 shared_exchange（单账户向后兼容）
"""
import asyncio
from typing import Optional
from sqlalchemy import select

from db.database import async_session
from db.models import ExchangeCredential
from core.crypto import decrypt
from core.exchange import ExchangeClient
import core.exchange as exmod
from core.logger import log
from config import settings as global_settings


class ExchangeRegistry:
    """多租户交易所实例池"""

    def __init__(self):
        # key = "tenant_id:account_id" -> ExchangeClient
        self._instances: dict[str, ExchangeClient] = {}

    async def get(
        self,
        tenant_id: str = "default",
        account_id: str = "default",
    ) -> ExchangeClient:
        """获取账户专属 exchange 实例。

        优先从 ExchangeCredential 表加载；找不到则 fallback 到 shared_exchange。
        """
        key = f"{tenant_id}:{account_id}"

        # 1. 缓存命中
        if key in self._instances:
            return self._instances[key]

        # 2. 从 DB 加载凭据
        cred = await self._load_credential(tenant_id, account_id)
        if cred is None:
            # 仅 "default" 账户允许 fallback（单账户向后兼容）；非 default 抛错避免跨账户污染
            if account_id == "default":
                log.debug(f"ExchangeRegistry: no credential for {key}, fallback to shared_exchange")
                return exmod.shared_exchange
            raise RuntimeError(f"账户 {account_id} 无凭据（ExchangeCredential 表无记录）")

        # 3. 创建新实例
        try:
            api_key = decrypt(cred.api_key_enc) if cred.api_key_enc else ""
            secret = decrypt(cred.api_secret_enc) if cred.api_secret_enc else ""
            passphrase = decrypt(cred.passphrase_enc) if cred.passphrase_enc else ""

            if not api_key or not secret:
                raise RuntimeError(f"账户 {account_id} 凭据解密失败或为空")

            client = ExchangeClient(
                exchange_name=cred.exchange_id or global_settings.EXCHANGE_NAME,
                api_key=api_key,
                secret=secret,
                passphrase=passphrase,
                testnet=cred.is_testnet,
            )
            client._last_attempt = 0  # 立即尝试连接
            self._instances[key] = client
            log.info(f"ExchangeRegistry: loaded credential for {key} (exchange={cred.exchange_id}, testnet={cred.is_testnet})")
            return client
        except Exception as e:
            log.error(f"ExchangeRegistry: failed to create instance for {key}: {e}")
            raise

    async def _load_credential(
        self,
        tenant_id: str,
        account_id: str,
    ) -> Optional[ExchangeCredential]:
        """从 DB 加载凭据"""
        try:
            async with async_session() as session:
                r = await session.execute(
                    select(ExchangeCredential).where(
                        ExchangeCredential.tenant_id == tenant_id,
                        ExchangeCredential.account_label == account_id,
                        ExchangeCredential.is_active == True,
                    )
                )
                return r.scalar_one_or_none()
        except Exception as e:
            log.warning(f"ExchangeRegistry: failed to load credential for {tenant_id}:{account_id}: {e}")
            return None

    async def invalidate(
        self,
        tenant_id: str = "default",
        account_id: str = "default",
    ):
        """清除指定账户的缓存实例（凭据变更时调用）"""
        key = f"{tenant_id}:{account_id}"
        if key in self._instances:
            del self._instances[key]
            log.info(f"ExchangeRegistry: invalidated {key}")

    async def close_all(self):
        """关闭所有实例（应用关闭时调用）"""
        for key, client in list(self._instances.items()):
            try:
                if hasattr(client, "_exchange") and client._exchange:
                    await client._exchange.close()
                log.debug(f"ExchangeRegistry: closed {key}")
            except Exception as e:
                log.warning(f"ExchangeRegistry: failed to close {key}: {e}")
        self._instances.clear()
        log.info("ExchangeRegistry: all instances closed and cleared")


# 模块级单例
exchange_registry = ExchangeRegistry()
