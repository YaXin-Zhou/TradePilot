"""AI 策略服务层 — 市场数据获取、特征计算、AI 分析、策略回测分发、自动入库"""
import math
import uuid
from datetime import datetime
import httpx
from core.exchange import shared_exchange as _exchange
from config import settings
from core.logger import log
from strategies.ai_strategy import AIStrategyEngine
from strategies.backtest import BacktestEngine
from ml.features import FeatureEngine

# 模块级单例
_fe = FeatureEngine()


def _sanitize_json(obj):
    """递归替换 NaN/Inf 为 None，确保 JSON 可序列化"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    return obj


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
    name: str = "",
    user_id: str = "",
) -> dict:
    """分析市场并返回 AI 信号 + 策略建议 + 回测结果（自动入库到策略表+策略池）"""

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

    # 5. 构造响应（NaN→None 防止 JSON 序列化失败）
    backtest_formatted = _format_backtest_result(backtest_result)

    # 6. 自动入库：策略 → 策略表 + 策略池
    strategy_id = None
    pool_registered = False
    if st and backtest_formatted:
        try:
            from services.strategy_service import save_ai_strategy
            from services.strategy_pool import strategy_pool

            # 自动生成策略名称
            auto_name = name or f"AI-{st}-{symbol.replace('/', '')}-{datetime.now().strftime('%m%d%H%M')}"

            # 保存到策略表
            save_result = await save_ai_strategy(
                name=auto_name,
                strategy_type=st,
                symbol=symbol,
                config=sp,
                backtest=backtest_formatted,
                description=strategy_info.get("strategy_description", ""),
                user_id=user_id,
            )
            if save_result.get("success"):
                strategy_id = save_result["data"]["id"]
                # 注册到策略池
                strategy_pool.register(strategy_id, auto_name, st)
                pool_registered = True
                log.info(f"AI 策略自动入库+入池: {strategy_id} ({auto_name})")
        except Exception as e:
            log.warning(f"AI 策略自动入库失败（不影响主流程）: {e}")

    return {
        "success": True,
        "data": {
            "signal": signal.type.value,
            "confidence": round(signal.confidence, 4) if not math.isnan(signal.confidence) else None,
            "reason": signal.reason,
            "price": signal.price if not (isinstance(signal.price, float) and math.isnan(signal.price)) else None,
            "current_price": ticker.get("last", 0),
            "indicators": _sanitize_json(indicators),
            "strategy_type": st,
            "strategy_description": strategy_info.get("strategy_description", ""),
            "market_assessment": strategy_info.get("market_assessment", ""),
            "strategy_params": sp,
            "backtest": _sanitize_json(backtest_formatted),
            "strategy_id": strategy_id,
            "pool_registered": pool_registered,
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
