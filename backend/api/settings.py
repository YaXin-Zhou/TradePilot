"""Settings API - persistent config storage (with encryption)"""
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from db.database import async_session
from db.models import AppConfig
from auth.deps import get_current_user
from core.crypto import encrypt, decrypt, mask_sensitive

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ExchangeConfigRequest(BaseModel):
    api_key: str = ""
    secret: str = ""
    passphrase: str = ""
    testnet: bool = True


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
    async with async_session() as session:
        result = await session.execute(
            select(AppConfig).where(AppConfig.key == "exchange_settings")
        )
        row = result.scalar_one_or_none()
        # 加密存储敏感字段；api_key 保留明文用于显示，secret/passphrase 必须加密
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

    return {"success": True}
