"""AI Strategy API"""
from fastapi import APIRouter
from pydantic import BaseModel

from strategies.backtest import BacktestEngine
from strategies.ai_strategy import AIStrategyEngine
from core.exchange import shared_exchange as _exchange
from ml.features import FeatureEngine
from config import settings

router = APIRouter(prefix="/api/ai", tags=["ai"])



_fe = FeatureEngine()


class AnalyzeRequest(BaseModel):
    api_key: str
    auto: bool = False
    name: str = ""
    strategy_desc: str
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"


@router.post("/analyze")
async def ai_analyze(req: AnalyzeRequest):
    try:
        ticker = _exchange.fetch_ticker(req.symbol)
        df = _exchange.fetch_ohlcv(req.symbol, req.timeframe, limit=100)
        df_feat = _fe.compute_features(df)
        if df_feat.empty:
            return {"success": False, "error": "No market data"}
        latest = df_feat.iloc[-1]
        indicators = {
            "rsi": round(float(latest.get("rsi_14", 50)), 2),
            "macd": round(float(latest.get("macd", 0)), 4),
            "macd_signal": round(float(latest.get("macd_signal", 0)), 4),
            "bb_upper": round(float(latest.get("bb_upper", 0)), 2),
            "bb_lower": round(float(latest.get("bb_lower", 0)), 2),
            "ema_9": round(float(latest.get("ema_9", 0)), 2),
            "ema_21": round(float(latest.get("ema_21", 0)), 2),
            "ema_50": round(float(latest.get("ema_50", 0)), 2),
            "atr": round(float(latest.get("atr_14", 0)), 2),
            "volume_ratio": round(float(latest.get("volume_ratio", 0)), 2),
        }
        engine = AIStrategyEngine(api_key=req.api_key)
        if req.auto:
            signal, strategy_info = await engine.auto_analyze({"ticker": ticker, "indicators": indicators})
        else:
            signal, strategy_info = await engine.analyze(req.strategy_desc, {"ticker": ticker, "indicators": indicators})
        # Auto backtest with AI-recommended strategy
        backtest_result = None
        st = strategy_info.get("type", "")
        sp = strategy_info.get("params", {})
        if st and sp:
            try:
                bt = BacktestEngine(df, 10000)
                if st == "ma_crossover":
                    backtest_result = bt.run_ma_crossover(sp.get("fast", 10), sp.get("slow", 30))
                elif st == "rsi":
                    backtest_result = bt.run_rsi(sp.get("period", 14), sp.get("oversold", 30), sp.get("overbought", 70))
                elif st == "bollinger":
                    backtest_result = bt.run_bollinger(sp.get("period", 20), sp.get("std_dev", 2.0))
            except Exception:
                pass
        return {
            "success": True,
            "data": {
                "signal": signal.type.value,
                "confidence": round(signal.confidence, 4),
                "reason": signal.reason,
                "price": signal.price,
                "current_price": ticker.get("last", 0),
                "indicators": indicators,
                "strategy_type": st,
                "strategy_description": strategy_info.get("strategy_description", ""),
                "market_assessment": strategy_info.get("market_assessment", ""),
                "strategy_params": sp,
                "backtest": {
                    "total_return_pct": backtest_result.total_return_pct if backtest_result else None,
                    "sharpe_ratio": backtest_result.sharpe_ratio if backtest_result else None,
                    "total_trades": backtest_result.total_trades if backtest_result else None,
                    "win_rate": backtest_result.win_rate if backtest_result else None,
                    "max_drawdown_pct": backtest_result.max_drawdown_pct if backtest_result else None,
                    "profit_factor": backtest_result.profit_factor if backtest_result else None,
                } if backtest_result else None,
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


@router.post("/test-connection")
async def test_connection(data: dict):
    api_key = data.get("api_key", "")
    if not api_key:
        return {"success": False, "error": "No API key"}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            )
            if resp.status_code == 200:
                return {"success": True, "data": {"status": "connected"}}
            return {"success": False, "error": f"API returned {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)[:100]}
