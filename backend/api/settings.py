"""Settings API - persistent config storage"""
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from db.database import async_session
from db.models import AppConfig
from auth.deps import get_current_user

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
    return {
        "success": True,
        "data": {
            "api_key": data.get("api_key", ""),
            "secret": "***" if data.get("secret") else "",
            "has_secret": bool(data.get("secret")),
            "passphrase": "***" if data.get("passphrase") else "",
            "has_passphrase": bool(data.get("passphrase")),
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
        value = json.dumps({
            "api_key": req.api_key,
            "secret": req.secret,
            "passphrase": req.passphrase,
            "testnet": req.testnet,
        })
        if row:
            row.value = value
        else:
            session.add(AppConfig(key="exchange_settings", value=value))
        await session.commit()

    return {"success": True}
