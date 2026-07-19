"""投资组合服务层 — 余额查询、交易历史、绩效分析"""
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from core.exchange import ExchangeClient
from config import settings
from db.models import Trade, Strategy
from db.database import async_session

_exchange = ExchangeClient(
    exchange_name=settings.EXCHANGE_NAME,
    api_key=settings.EXCHANGE_API_KEY,
    secret=settings.EXCHANGE_SECRET,
    passphrase=settings.EXCHANGE_PASSPHRASE,
    testnet=settings.EXCHANGE_TESTNET,
)


def _mock_trades(count: int = 100) -> list[dict]:
    """生成模拟交易历史"""
    trades = []
    now = datetime.now(timezone.utc)
    for i in range(count):
        buy = 85000 + random.uniform(-2000, 2000)
        sell = buy * (1 + random.uniform(-0.02, 0.03))
        qty = random.uniform(0.001, 0.05)
        pnl = (sell - buy) * qty
        trades.append({
            "id": f"trade_{i}",
            "symbol": "BTC/USDT",
            "buy_price": round(buy, 2),
            "sell_price": round(sell, 2),
            "quantity": round(qty, 6),
            "profit": round(pnl, 4),
            "profit_pct": round((sell - buy) / buy * 100, 2),
            "opened_at": (now - timedelta(hours=i * 3)).isoformat(),
            "closed_at": (now - timedelta(hours=i * 3 - 1)).isoformat(),
        })
    return trades


async def get_portfolio_summary() -> dict:
    """获取投资组合摘要（余额 + 统计 + mock 回退）"""
    try:
        balance = _exchange.fetch_balance()
        ticker = _exchange.fetch_ticker(settings.DEFAULT_SYMBOL)
        total_usdt = balance.get("USDT", {}).get("total", 0)
        btc_balance = balance.get("BTC", {}).get("total", 0)
        estimated_total = total_usdt + btc_balance * ticker["last"]

        async with async_session() as session:
            total_trades = await session.scalar(select(func.count(Trade.id)))
            total_pnl = await session.scalar(select(func.coalesce(func.sum(Trade.profit), 0)))
            active_strategies = await session.scalar(
                select(func.count(Strategy.id)).where(Strategy.status == "running")
            )

        return {
            "success": True,
            "data": {
                "total_value_usdt": round(estimated_total, 2),
                "usdt_balance": round(total_usdt, 2),
                "btc_balance": round(btc_balance, 6),
                "btc_price": round(ticker["last"], 2),
                "total_trades": total_trades or 0,
                "total_pnl": round(float(total_pnl or 0), 4),
                "active_strategies": active_strategies or 0,
            },
        }
    except Exception:
        return {
            "success": True,
            "data": {
                "total_value_usdt": 11150.28,
                "usdt_balance": 9850.42,
                "btc_balance": 0.1308,
                "btc_price": 86500.00,
                "total_trades": 127,
                "total_pnl": 28.4556,
                "active_strategies": 2,
            },
            "_mock": True,
        }


async def get_trade_history(limit: int = 100) -> dict:
    """获取交易历史（DB 优先 + mock 回退）"""
    async with async_session() as session:
        result = await session.execute(
            select(Trade).order_by(Trade.closed_at.desc()).limit(limit)
        )
        trades = result.scalars().all()
        if trades:
            return {
                "success": True,
                "data": [
                    {
                        "id": t.id, "symbol": t.symbol,
                        "buy_price": t.buy_price, "sell_price": t.sell_price,
                        "quantity": t.quantity, "profit": t.profit,
                        "profit_pct": t.profit_pct,
                        "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                    }
                    for t in trades
                ],
            }
    return {"success": True, "data": _mock_trades(limit), "_mock": True}


async def get_performance() -> dict:
    """获取绩效分析（PnL 计算 + 曲线 + mock 回退）"""
    async with async_session() as session:
        result = await session.execute(select(Trade).order_by(Trade.closed_at.asc()))
        trades = result.scalars().all()
        if trades:
            total_pnl = sum(t.profit for t in trades)
            wins = sum(1 for t in trades if t.profit > 0)
            win_rate = wins / len(trades) * 100 if trades else 0
            cumulative = 0.0
            pnl_curve = []
            for t in trades:
                cumulative += t.profit
                pnl_curve.append({
                    "date": t.closed_at.isoformat() if t.closed_at else None,
                    "pnl": cumulative,
                })
            return {
                "success": True,
                "data": {
                    "total_pnl": round(total_pnl, 4),
                    "total_trades": len(trades),
                    "win_rate": round(win_rate, 2),
                    "wins": wins,
                    "losses": len(trades) - wins,
                    "pnl_curve": pnl_curve,
                },
            }

    # Mock 回退
    mock_trades = _mock_trades(50)
    cumulative = 0.0
    pnl_curve = []
    for t in reversed(mock_trades):
        cumulative += t["profit"]
        pnl_curve.append({"date": t["closed_at"], "pnl": round(cumulative, 4)})
    wins = sum(1 for t in mock_trades if t["profit"] > 0)
    return {
        "success": True,
        "data": {
            "total_pnl": round(sum(t["profit"] for t in mock_trades), 4),
            "total_trades": len(mock_trades),
            "win_rate": round(wins / len(mock_trades) * 100, 2) if mock_trades else 0,
            "wins": wins,
            "losses": len(mock_trades) - wins,
            "pnl_curve": pnl_curve,
        },
        "_mock": True,
    }
