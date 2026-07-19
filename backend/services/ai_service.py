"""AI 策略服务层 — 市场数据获取、特征计算、AI 分析、策略回测分发"""
import httpx
from core.exchange import shared_exchange as _exchange
from config import settings
from core.logger import log
from strategies.ai_strategy import AIStrategyEngine
from strategies.backtest import BacktestEngine
from ml.features import FeatureEngine

# 模块级单例
_fe = FeatureEngine()


def _get_ai_engine() -> AIStrategyEngine | None:
    """从后端配置创建 AI 引擎，Key 不可用时返回 None"""
    key = settings.DEEPSEEK_API_KEY
    if not key:
        return None
    return AIStrategyEngine(api_key=key)


async def analyze_market(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    auto: bool = False,
    strategy_desc: str = "",
) -> dict:
    """分析市场并返回 AI 信号 + 策略建议 + 回测结果"""

    engine = _get_ai_engine()
    if engine is None:
        return {"success": False, "error": "DeepSeek API Key 未配置，请在 .env 中设置 DEEPSEEK_API_KEY"}

    # 1. 获取市场数据
    ticker = _exchange.fetch_ticker(symbol)
    df = _exchange.fetch_ohlcv(symbol, timeframe, limit=100)
    df_feat = _fe.compute_features(df)

    if df_feat.empty:
        return {"success": False, "error": "No market data"}

    # 2. 提取技术指标
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

    # 3. AI 信号分析
    if auto:
        signal, strategy_info = await engine.auto_analyze({"ticker": ticker, "indicators": indicators})
    else:
        signal, strategy_info = await engine.analyze(strategy_desc, {"ticker": ticker, "indicators": indicators})

    # 4. 自动回测（根据 AI 推荐的策略类型）
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
        except Exception as e:
            log.warning(f"Auto backtest failed: {e}")

    # 5. 构造响应
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
            "backtest": _format_backtest_result(backtest_result),
        },
    }


def _format_backtest_result(backtest_result) -> dict | None:
    """将 BacktestResult 转为字典"""
    if backtest_result is None:
        return None
    return {
        "total_return_pct": backtest_result.total_return_pct,
        "sharpe_ratio": backtest_result.sharpe_ratio,
        "total_trades": backtest_result.total_trades,
        "win_rate": backtest_result.win_rate,
        "max_drawdown_pct": backtest_result.max_drawdown_pct,
        "profit_factor": backtest_result.profit_factor,
    }


async def test_ai_connection() -> dict:
    """测试后端 DeepSeek API Key 是否有效"""
    key = settings.DEEPSEEK_API_KEY
    if not key:
        return {"success": False, "error": "DEEPSEEK_API_KEY 未配置"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            )
            if resp.status_code == 200:
                return {"success": True, "data": {"status": "connected"}}
            return {"success": False, "error": f"API returned {resp.status_code}"}
    except Exception as e:
        log.warning(f"AI connection test failed: {e}")
        return {"success": False, "error": str(e)[:100]}
