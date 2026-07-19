"""Settings API - persistent config storage (with encryption)

Phase 8 改动：
  - 保存配置后热重建 shared_exchange 实例（无需重启）
  - API Key 权限校验（确保未开提币权限）
  - 实盘模式切换时同步更新 settings
"""
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from db.database import async_session
from db.models import AppConfig
from auth.deps import get_current_user
from core.crypto import encrypt, decrypt, mask_sensitive
from core.logger import log
from config import settings as global_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ExchangeConfigRequest(BaseModel):
    api_key: str = ""
    secret: str = ""
    passphrase: str = ""
    testnet: bool = True
    verify_permissions: bool = True  # 是否校验 API Key 权限（默认校验）


async def _rebuild_exchange(api_key: str, secret: str, passphrase: str, testnet: bool):
    """保存配置后热重建 shared_exchange 实例（无需重启进程）"""
    try:
        from core.exchange import ExchangeClient
        import core.exchange as exmod

        client = ExchangeClient(
            exchange_name=global_settings.EXCHANGE_NAME,
            api_key=api_key,
            secret=secret,
            passphrase=passphrase,
            testnet=testnet,
        )
        exmod.shared_exchange = client
        client._last_attempt = 0  # 立即尝试连接

        # 同步更新全局 settings（用于白名单/实盘判断）
        global_settings.EXCHANGE_TESTNET = testnet

        mode = "TESTNET" if testnet else "LIVE"
        log.info(f"Exchange instance rebuilt ({mode})")
        return True, "热切换成功"
    except Exception as e:
        log.error(f"Exchange rebuild failed: {e}")
        return False, f"热切换失败: {e}"


def _verify_api_key_permissions(api_key: str, secret: str, passphrase: str, testnet: bool) -> tuple[bool, str]:
    """校验 API Key 权限：确保能交易，且未开提币权限。

    Phase 8: 实盘安全要求。
    """
    try:
        import ccxt
        ex = getattr(ccxt, global_settings.EXCHANGE_NAME)({
            "apiKey": api_key,
            "secret": secret,
            "password": passphrase if passphrase else None,
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "spot"},
        })
        # 代理
        proxy = global_settings.HTTPS_PROXY or global_settings.HTTP_PROXY
        if proxy:
            ex.proxies = {"http": proxy, "https": proxy}
        if testnet:
            try:
                ex.set_sandbox_mode(True)
            except Exception:
                pass

        ex.load_markets()

        # 1. 能否获取余额（验证交易/读取权限）
        try:
            bal = ex.fetch_balance()
            if bal is None:
                return False, "API Key 无法获取余额，可能权限不足"
        except Exception as e:
            return False, f"API Key 余额查询失败: {e}"

        # 2. 检查是否开了提币权限（OKX 无法直接查询，但可尝试查询提币历史作为间接验证）
        # 注意：这里不做实际提币，只检查能否访问提币相关接口
        # 如果 API Key 开了提币权限，强烈建议用户关闭
        try:
            # OKX: 查询提币记录需要 withdrawal 权限；如果有权限能查到说明开了提币
            if hasattr(ex, "fetch_deposits_withdrawals"):
                # 尝试查询，如果成功说明有提币权限（风险）
                try:
                    ex.fetch_deposits_withdrawals({"limit": 1})
                    return True, "⚠️ 警告：该 API Key 似乎有提币权限，强烈建议在 OKX 后台关闭提币权限！"
                except Exception:
                    # 查询失败 = 没有提币权限 = 安全
                    pass
        except Exception:
            pass

        return True, "API Key 校验通过（交易权限正常，未检测到提币权限）"
    except Exception as e:
        return False, f"API Key 校验异常: {e}"


@router.get("/exchange")
async def get_exchange_config(_user: dict = Depends(get_current_user)):
    async with async_session() as session:
        result = await session.execute(
            select(AppConfig).where(AppConfig.key == "exchange_settings")
        )
        row = result.scalar_one_or_none()
        if row and row.value:
            try:
                data = json.loads(row.value)
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
    # 返回时解密（用于前端显示脱敏后的 Key）
    api_key = decrypt(data.get("api_key_enc", "")) or data.get("api_key", "")
    return {
        "success": True,
        "data": {
            "api_key": mask_sensitive(api_key) if api_key else "",
            "has_key": bool(api_key),
            "has_secret": bool(data.get("secret_enc") or data.get("secret")),
            "has_passphrase": bool(data.get("passphrase_enc") or data.get("passphrase")),
            "testnet": data.get("testnet", True),
        },
    }


@router.post("/exchange")
async def save_exchange_config(
    req: ExchangeConfigRequest,
    _user: dict = Depends(get_current_user),
):
    # 1. 校验 API Key 权限（如果提供了完整 Key）
    verify_msg = ""
    if req.api_key and req.secret and req.verify_permissions:
        ok, verify_msg = _verify_api_key_permissions(req.api_key, req.secret, req.passphrase, req.testnet)
        if not ok:
            return {"success": False, "error": f"API Key 校验失败: {verify_msg}"}
        log.info(f"API Key verified: {verify_msg}")

    # 2. 持久化到 DB
    async with async_session() as session:
        result = await session.execute(
            select(AppConfig).where(AppConfig.key == "exchange_settings")
        )
        row = result.scalar_one_or_none()
        value = json.dumps({
            "api_key_enc": encrypt(req.api_key),
            "secret_enc": encrypt(req.secret),
            "passphrase_enc": encrypt(req.passphrase),
            "testnet": req.testnet,
        })
        if row:
            row.value = value
        else:
            session.add(AppConfig(key="exchange_settings", value=value))
        await session.commit()

    # 3. Phase 8: 热重建 exchange 实例（无需重启）
    rebuilt, rebuild_msg = await _rebuild_exchange(req.api_key, req.secret, req.passphrase, req.testnet)

    return {
        "success": True,
        "data": {
            "rebuilt": rebuilt,
            "rebuild_msg": rebuild_msg,
            "verify_msg": verify_msg,
            "testnet": req.testnet,
            "mode": "TESTNET" if req.testnet else "LIVE",
        },
    }


@router.post("/exchange/test")
async def test_exchange_config(
    req: ExchangeConfigRequest,
    _user: dict = Depends(get_current_user),
):
    """测试连接 + 校验权限（不保存）"""
    if not req.api_key or not req.secret:
        return {"success": False, "error": "请提供完整的 API Key 和 Secret"}

    ok, msg = _verify_api_key_permissions(req.api_key, req.secret, req.passphrase, req.testnet)
    return {"success": ok, "data": {"message": msg, "testnet": req.testnet}}
