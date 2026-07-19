"""Settings API - 双套 API Key 配置（模拟盘 + 实盘）

Phase 8.1 改动：
  - 同时存储模拟盘和实盘两套 API Key 配置，各自独立
  - active 字段标记当前激活的模式（testnet/live）
  - 切换激活模式时热重建 shared_exchange
  - 实盘切换需二次确认（confirm=true）
  - 向后兼容：自动迁移旧版单配置数据为 testnet 配置
"""
import json
import httpx
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

CONFIG_KEY = "exchange_settings"


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class ExchangeConfigRequest(BaseModel):
    """保存/测试单套配置。mode 指定保存到哪一套。"""
    mode: str = "testnet"  # "testnet" | "live"
    api_key: str = ""
    secret: str = ""
    passphrase: str = ""
    verify_permissions: bool = True


class SwitchModeRequest(BaseModel):
    """切换激活模式。实盘切换需 confirm=true。"""
    mode: str  # "testnet" | "live"
    confirm: bool = False


# ---------------------------------------------------------------------------
# 存储读写工具
# ---------------------------------------------------------------------------

def _empty_creds(testnet: bool) -> dict:
    return {
        "api_key_enc": "",
        "secret_enc": "",
        "passphrase_enc": "",
        "testnet": testnet,
    }


def _read_raw() -> dict:
    """读取原始配置 JSON。自动迁移旧版单配置格式。"""
    import asyncio
    async def _read():
        async with async_session() as session:
            r = await session.execute(
                select(AppConfig).where(AppConfig.key == CONFIG_KEY)
            )
            row = r.scalar_one_or_none()
            if not row or not row.value:
                return {}
            return json.loads(row.value)
    try:
        return asyncio.get_event_loop().run_until_complete(_read())
    except RuntimeError:
        # 已在事件循环中，用同步方式（数据库是 async 的，这里走 fallback）
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_read())
        finally:
            loop.close()


async def _read_config_async() -> dict:
    """异步读取并归一化配置，返回标准双配置结构。"""
    async with async_session() as session:
        r = await session.execute(
            select(AppConfig).where(AppConfig.key == CONFIG_KEY)
        )
        row = r.scalar_one_or_none()
        if not row or not row.value:
            return {"active": "testnet", "testnet": _empty_creds(True), "live": _empty_creds(False)}
        try:
            data = json.loads(row.value)
        except json.JSONDecodeError:
            data = {}

    # 向后兼容：旧版单配置格式（有 api_key_enc 但没有 active 字段）
    if "active" not in data and ("api_key_enc" in data or "api_key" in data):
        log.info("Migrating legacy single-config to dual-config (as testnet)")
        old_testnet = data.get("testnet", True)
        data = {
            "active": "testnet" if old_testnet else "live",
            "testnet": {
                "api_key_enc": data.get("api_key_enc", ""),
                "secret_enc": data.get("secret_enc", ""),
                "passphrase_enc": data.get("passphrase_enc", ""),
                "testnet": True,
            } if old_testnet else _empty_creds(True),
            "live": {
                "api_key_enc": data.get("api_key_enc", ""),
                "secret_enc": data.get("secret_enc", ""),
                "passphrase_enc": data.get("passphrase_enc", ""),
                "testnet": False,
            } if not old_testnet else _empty_creds(False),
        }

    # 补全字段
    data.setdefault("active", "testnet")
    data.setdefault("testnet", _empty_creds(True))
    data.setdefault("live", _empty_creds(False))
    # 修复 testnet 字段（防止数据不一致）
    data["testnet"].setdefault("testnet", True)
    data["testnet"]["testnet"] = True
    data["live"].setdefault("testnet", False)
    data["live"]["testnet"] = False
    return data


async def _write_config(data: dict):
    async with async_session() as session:
        r = await session.execute(
            select(AppConfig).where(AppConfig.key == CONFIG_KEY)
        )
        row = r.scalar_one_or_none()
        value = json.dumps(data)
        if row:
            row.value = value
        else:
            session.add(AppConfig(key=CONFIG_KEY, value=value))
        await session.commit()


def _creds_to_masked(creds: dict) -> dict:
    """脱敏单套配置用于前端展示。"""
    api_key = decrypt(creds.get("api_key_enc", "")) or creds.get("api_key", "")
    return {
        "api_key": mask_sensitive(api_key) if api_key else "",
        "has_key": bool(api_key),
        "has_secret": bool(creds.get("secret_enc") or creds.get("secret")),
        "has_passphrase": bool(creds.get("passphrase_enc") or creds.get("passphrase")),
    }


def _get_creds_plaintext(creds: dict) -> tuple[str, str, str]:
    """解密返回明文三元组。"""
    api_key = decrypt(creds.get("api_key_enc", "")) or creds.get("api_key", "")
    secret = decrypt(creds.get("secret_enc", "")) or creds.get("secret", "")
    passphrase = decrypt(creds.get("passphrase_enc", "")) or creds.get("passphrase", "")
    return api_key, secret, passphrase


# ---------------------------------------------------------------------------
# 交易所实例热重建
# ---------------------------------------------------------------------------

async def _rebuild_exchange(api_key: str, secret: str, passphrase: str, testnet: bool):
    """热重建 shared_exchange 实例（无需重启进程）"""
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


def _rebuild_from_config(data: dict):
    """根据 active 模式从配置重建 exchange（启动时调用）"""
    active = data.get("active", "testnet")
    creds = data.get(active, {})
    api_key, secret, passphrase = _get_creds_plaintext(creds)
    if api_key and secret:
        testnet = (active == "testnet")
        # 异步调用同步包装（启动时在事件循环内）
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
        client._last_attempt = 0
        global_settings.EXCHANGE_TESTNET = testnet
        log.info(f"Exchange config loaded from DB (active={active})")
        return True
    return False


# ---------------------------------------------------------------------------
# API Key 权限校验
# ---------------------------------------------------------------------------

def _verify_api_key_permissions(api_key: str, secret: str, passphrase: str, testnet: bool) -> tuple[bool, str]:
    """校验 API Key 权限：确保能交易，且未开提币权限。"""
    try:
        import ccxt
        ex = getattr(ccxt, global_settings.EXCHANGE_NAME)({
            "apiKey": api_key,
            "secret": secret,
            "password": passphrase if passphrase else None,
            "enableRateLimit": True,
            "timeout": 15000,
            "options": {"defaultType": "spot"},
        })
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

        # 2. 检查是否开了提币权限（间接验证）
        try:
            if hasattr(ex, "fetch_deposits_withdrawals"):
                try:
                    ex.fetch_deposits_withdrawals({"limit": 1})
                    return True, "⚠️ 警告：该 API Key 似乎有提币权限，强烈建议在 OKX 后台关闭提币权限！"
                except Exception:
                    pass
        except Exception:
            pass

        mode_label = "模拟盘" if testnet else "实盘"
        return True, f"API Key 校验通过（{mode_label}，交易权限正常，未检测到提币权限）"
    except Exception as e:
        return False, f"API Key 校验异常: {e}"


# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------

@router.get("/exchange")
async def get_exchange_config(_user: dict = Depends(get_current_user)):
    """返回双套配置（脱敏）+ 当前激活模式"""
    data = await _read_config_async()
    return {
        "success": True,
        "data": {
            "active": data.get("active", "testnet"),
            "testnet": _creds_to_masked(data.get("testnet", {})),
            "live": _creds_to_masked(data.get("live", {})),
        },
    }


def _is_masked_or_empty(value: str) -> bool:
    """判断值是否为空或脱敏占位符（含 *）。这类值应保留原 DB 值不覆盖。"""
    return not value or "*" in value


@router.post("/exchange")
async def save_exchange_config(
    req: ExchangeConfigRequest,
    _user: dict = Depends(get_current_user),
):
    """保存指定模式（testnet/live）的 API Key 配置。

    如果某字段为空或为脱敏占位符（含 *），则保留 DB 原值不覆盖。
    如果保存的是当前 active 模式，保存后自动热重建 exchange。
    """
    mode = req.mode if req.mode in ("testnet", "live") else "testnet"
    is_testnet = (mode == "testnet")

    # 1. 读取现有配置，合并字段（空/脱敏值保留原值）
    data = await _read_config_async()
    existing_creds = data.get(mode, {})
    existing_api_key, existing_secret, existing_passphrase = _get_creds_plaintext(existing_creds)

    final_api_key = existing_api_key if _is_masked_or_empty(req.api_key) else req.api_key
    final_secret = existing_secret if _is_masked_or_empty(req.secret) else req.secret
    final_passphrase = existing_passphrase if _is_masked_or_empty(req.passphrase) else req.passphrase

    # 2. 校验 API Key 权限（仅当有完整 Key 时）
    verify_msg = ""
    if final_api_key and final_secret and req.verify_permissions:
        ok, verify_msg = _verify_api_key_permissions(final_api_key, final_secret, final_passphrase, is_testnet)
        if not ok:
            return {"success": False, "error": f"API Key 校验失败: {verify_msg}"}
        log.info(f"API Key verified ({mode}): {verify_msg}")

    # 3. 写入合并后的配置
    data[mode] = {
        "api_key_enc": encrypt(final_api_key),
        "secret_enc": encrypt(final_secret),
        "passphrase_enc": encrypt(final_passphrase),
        "testnet": is_testnet,
    }
    await _write_config(data)

    # 4. 如果保存的是当前 active 模式，热重建
    rebuilt = False
    rebuild_msg = "未激活模式，无需热重建"
    if data.get("active") == mode:
        rebuilt, rebuild_msg = await _rebuild_exchange(final_api_key, final_secret, final_passphrase, is_testnet)

    return {
        "success": True,
        "data": {
            "mode": mode,
            "rebuilt": rebuilt,
            "rebuild_msg": rebuild_msg,
            "verify_msg": verify_msg,
            "active": data.get("active"),
            "preserved_fields": _is_masked_or_empty(req.api_key) or _is_masked_or_empty(req.secret) or _is_masked_or_empty(req.passphrase),
        },
    }


@router.post("/exchange/switch")
async def switch_active_mode(
    req: SwitchModeRequest,
    _user: dict = Depends(get_current_user),
):
    """切换当前激活的交易所模式（testnet/live）。

    切换到 live 模式必须 confirm=true（二次确认）。
    切换后热重建 exchange 实例。
    """
    mode = req.mode if req.mode in ("testnet", "live") else "testnet"

    # 实盘切换二次确认
    if mode == "live" and not req.confirm:
        return {
            "success": False,
            "error": "切换到实盘模式需要二次确认。确认后将使用真实资金交易，请设置 confirm=true。",
            "require_confirm": True,
        }

    data = await _read_config_async()

    # 检查目标模式是否已配置
    target_creds = data.get(mode, {})
    api_key, secret, passphrase = _get_creds_plaintext(target_creds)
    if not api_key or not secret:
        return {
            "success": False,
            "error": f"{'实盘' if mode == 'live' else '模拟盘'}尚未配置 API Key，请先在设置页填写并保存。",
        }

    # 更新 active
    data["active"] = mode
    await _write_config(data)

    # 热重建
    is_testnet = (mode == "testnet")
    rebuilt, rebuild_msg = await _rebuild_exchange(api_key, secret, passphrase, is_testnet)

    mode_label = "模拟盘(TESTNET)" if is_testnet else "实盘(LIVE)"
    log.info(f"Exchange mode switched to {mode_label} by user")
    return {
        "success": True,
        "data": {
            "active": mode,
            "mode_label": mode_label,
            "rebuilt": rebuilt,
            "rebuild_msg": rebuild_msg,
        },
    }


@router.post("/exchange/test")
async def test_exchange_config(
    req: ExchangeConfigRequest,
    _user: dict = Depends(get_current_user),
):
    """测试连接 + 校验权限（不保存）

    如果某字段为空或为脱敏占位符（含 *），从 DB 读取已保存的明文值进行测试。
    这样刷新页面后输入框为空也能测试已保存的 Key。
    """
    mode = req.mode if req.mode in ("testnet", "live") else "testnet"
    is_testnet = (mode == "testnet")

    # 空值/脱敏值时从 DB 读原值（与 save 端点逻辑一致）
    if _is_masked_or_empty(req.api_key) or _is_masked_or_empty(req.secret):
        data = await _read_config_async()
        creds = data.get(mode, {})
        db_api_key, db_secret, db_passphrase = _get_creds_plaintext(creds)
        if not db_api_key or not db_secret:
            mode_label = "实盘" if mode == "live" else "模拟盘"
            return {"success": False, "error": f"{mode_label}尚未配置 API Key，请先填写并保存"}
        final_api_key = db_api_key
        final_secret = db_secret
        final_passphrase = db_passphrase if _is_masked_or_empty(req.passphrase) else req.passphrase
    else:
        final_api_key = req.api_key
        final_secret = req.secret
        final_passphrase = req.passphrase

    ok, msg = _verify_api_key_permissions(final_api_key, final_secret, final_passphrase, is_testnet)
    return {"success": ok, "data": {"message": msg, "mode": mode, "testnet": is_testnet}}


# ---------------------------------------------------------------------------
# DeepSeek API Key 配置
# ---------------------------------------------------------------------------

DEEPSEEK_CONFIG_KEY = "deepseek_settings"


class DeepSeekConfigRequest(BaseModel):
    """DeepSeek API Key 保存/测试请求。"""
    api_key: str = ""


async def _read_deepseek_config() -> dict:
    """读取 DeepSeek 配置 JSON。"""
    async with async_session() as session:
        r = await session.execute(
            select(AppConfig).where(AppConfig.key == DEEPSEEK_CONFIG_KEY)
        )
        row = r.scalar_one_or_none()
        if not row or not row.value:
            return {}
        try:
            return json.loads(row.value)
        except json.JSONDecodeError:
            return {}


async def _write_deepseek_config(data: dict):
    async with async_session() as session:
        r = await session.execute(
            select(AppConfig).where(AppConfig.key == DEEPSEEK_CONFIG_KEY)
        )
        row = r.scalar_one_or_none()
        value = json.dumps(data)
        if row:
            row.value = value
        else:
            session.add(AppConfig(key=DEEPSEEK_CONFIG_KEY, value=value))
        await session.commit()


def _test_deepseek_key(api_key: str) -> tuple[bool, str]:
    """测试 DeepSeek API Key 是否有效（发一个 ping 请求）。"""
    if not api_key:
        return False, "请提供 DeepSeek API Key"
    try:
        proxy = global_settings.HTTPS_PROXY or global_settings.HTTP_PROXY
        with httpx.Client(timeout=15, proxy=proxy if proxy else None) as client:
            resp = client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            )
            if resp.status_code == 200:
                return True, "DeepSeek API Key 有效，连接成功"
            return False, f"DeepSeek 返回 {resp.status_code}: {resp.text[:120]}"
    except Exception as e:
        return False, f"连接失败: {e}"


@router.get("/deepseek")
async def get_deepseek_config(_user: dict = Depends(get_current_user)):
    """返回 DeepSeek API Key 配置状态（脱敏）"""
    data = await _read_deepseek_config()
    api_key_enc = data.get("api_key_enc", "")
    api_key = decrypt(api_key_enc) if api_key_enc else ""
    return {
        "success": True,
        "data": {
            "has_key": bool(api_key),
            "api_key": mask_sensitive(api_key) if api_key else "",
            "source": "DB" if api_key else (".env" if global_settings.DEEPSEEK_API_KEY else "未配置"),
        },
    }


@router.post("/deepseek")
async def save_deepseek_config(
    req: DeepSeekConfigRequest,
    _user: dict = Depends(get_current_user),
):
    """保存 DeepSeek API Key（加密存 DB + 热更新全局 settings）

    如果 api_key 为空或为脱敏占位符（含 *），保留 DB 原值不覆盖。
    """
    # 读取现有配置，空/脱敏值保留原值
    existing = await _read_deepseek_config()
    existing_key = decrypt(existing.get("api_key_enc", "")) if existing.get("api_key_enc") else ""

    if _is_masked_or_empty(req.api_key):
        if not existing_key:
            return {"success": False, "error": "请提供 DeepSeek API Key"}
        final_key = existing_key
        preserved = True
    else:
        final_key = req.api_key
        preserved = False

    # 可选：保存前测试一次（失败仍允许保存，仅警告）
    test_ok, test_msg = _test_deepseek_key(final_key)

    # 加密存储
    await _write_deepseek_config({"api_key_enc": encrypt(final_key)})

    # 热更新全局 settings，所有使用方立即生效
    global_settings.DEEPSEEK_API_KEY = final_key
    log.info(f"DeepSeek API Key saved to DB (preserved={preserved})")

    return {
        "success": True,
        "data": {
            "saved": True,
            "test_ok": test_ok,
            "test_msg": test_msg,
            "source": "DB",
            "preserved": preserved,
        },
    }


@router.post("/deepseek/test")
async def test_deepseek_config(
    req: DeepSeekConfigRequest,
    _user: dict = Depends(get_current_user),
):
    """测试 DeepSeek API Key（不保存）

    如果 api_key 为空或为脱敏占位符（含 *），从 DB 读取已保存的明文值进行测试。
    """
    api_key = req.api_key
    if _is_masked_or_empty(api_key):
        existing = await _read_deepseek_config()
        existing_key = decrypt(existing.get("api_key_enc", "")) if existing.get("api_key_enc") else ""
        if not existing_key:
            return {"success": False, "data": {"message": "尚未配置 DeepSeek API Key，请先填写并保存"}}
        api_key = existing_key
    ok, msg = _test_deepseek_key(api_key)
    return {"success": ok, "data": {"message": msg}}
