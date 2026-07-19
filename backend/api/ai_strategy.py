"""AI Strategy API — 薄层：参数校验 → 调用 service → 构造响应"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.deps import get_current_user
from services.ai_service import analyze_market, test_ai_connection

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AnalyzeRequest(BaseModel):
    auto: bool = False
    name: str = ""
    strategy_desc: str = ""
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"


@router.post("/analyze")
async def ai_analyze(req: AnalyzeRequest, _user: dict = Depends(get_current_user)):
    return await analyze_market(
        symbol=req.symbol,
        timeframe=req.timeframe,
        auto=req.auto,
        strategy_desc=req.strategy_desc,
    )


@router.post("/test-connection")
async def test_connection():
    return await test_ai_connection()
