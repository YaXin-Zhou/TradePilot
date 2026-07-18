"""FastAPI 应用入口"""
import sys
import os
from contextlib import asynccontextmanager

# 确保 backend 在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from db.database import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="AI Quant Trade",
    description="AI 量化交易系统 - OKX",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from api.market import router as market_router
from api.trading import router as trading_router
from api.portfolio import router as portfolio_router
from api.strategies import router as strategies_router
from api.analysis import router as analysis_router

app.include_router(market_router)
app.include_router(trading_router)
app.include_router(portfolio_router)
app.include_router(strategies_router)
app.include_router(analysis_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "exchange": settings.EXCHANGE_NAME, "testnet": settings.EXCHANGE_TESTNET}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
from api.realtime import router as realtime_router
from core.exchange import set_connected, ExchangeClient
from config import settings
import asyncio
app.include_router(realtime_router)

