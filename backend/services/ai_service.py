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

    # 4. 自动回测（使用完整五重验证：IS/OOS拆分 + PBO + DSR + NW + SPA）
    backtest_result = None
    validation = None
    scientific_valid = False
    st = strategy_info.get("type", "")
    sp = strategy_info.get("params", {})
    if st and sp:
        # 参数名归一化：DeepSeek 可能返回 rsi_period/oversold_threshold 等非标准命名
        sp = _normalize_params(st, sp)
        try:
            from services.backtest_service import run_backtest
            bt_result = run_backtest(df, st, 10000, sp, with_validation=True)
            # run_backtest 返回平铺字典：{sharpe_ratio, total_return_pct, ..., validation: {...}, scientific_passed}
            backtest_result = bt_result  # 本身就是 metrics 字典
            validation = bt_result.get("validation", {})
            scientific_valid = bt_result.get("scientific_passed", False)
            log.info(
                f"AI backtest: {st} sharpe_is={backtest_result.get('sharpe_ratio', 0):.3f} "
                f"sharpe_oos={validation.get('sharpe_oos', 0):.3f} "
                f"pbo={validation.get('pbo', 1):.3f} scientific={scientific_valid}"
            )
        except Exception as e:
            log.warning(f"Auto backtest with validation failed: {e}, falling back to basic")
            try:
                bt = BacktestEngine(df, 10000)
                if st == "ma_crossover":
                    backtest_result = bt.run_ma_crossover(sp.get("fast", 10), sp.get("slow", 30))
                elif st == "rsi":
                    backtest_result = bt.run_rsi(sp.get("period", 14), sp.get("oversold", 30), sp.get("overbought", 70))
                elif st == "bollinger":
                    backtest_result = bt.run_bollinger(sp.get("period", 20), sp.get("std_dev", 2.0))
            except Exception as e2:
                log.warning(f"Basic backtest also failed: {e2}")

    # 5. 构造响应（NaN→None 防止 JSON 序列化失败）
    backtest_formatted = _format_backtest_result(backtest_result)
    validation_formatted = _sanitize_json(validation) if validation else None

    # 6. 自动入库：仅科学验证通过（PBO≤0.5 且 OOS夏普>0）的策略才入库
    strategy_id = None
    pool_registered = False
    auto_save_skipped = False
    if st and backtest_formatted and scientific_valid:
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

    if not scientific_valid and st and backtest_formatted:
        auto_save_skipped = True
        log.info(f"AI strategy skipped auto-save: scientific_valid=False for {st}")

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
            "validation": validation_formatted,
            "scientific_valid": scientific_valid,
            "auto_save_skipped": auto_save_skipped,
            "strategy_id": strategy_id,
            "pool_registered": pool_registered,
        },
    }


def _normalize_params(strategy_type: str, params: dict) -> dict:
    """将 AI 返回的参数名归一化为回测引擎期望的命名"""
    # RSI 参数映射
    if strategy_type == "rsi":
        if "rsi_period" in params and "period" not in params:
            params["period"] = params.pop("rsi_period")
        if "oversold_threshold" in params and "oversold" not in params:
            params["oversold"] = params.pop("oversold_threshold")
        if "overbought_threshold" in params and "overbought" not in params:
            params["overbought"] = params.pop("overbought_threshold")
        # 确保默认值
        params.setdefault("period", 14)
        params.setdefault("oversold", 30)
        params.setdefault("overbought", 70)
    # MA 参数映射
    elif strategy_type in ("ma_crossover", "ma_cross", "sma_cross"):
        if "fast_period" in params and "fast" not in params:
            params["fast"] = params.pop("fast_period")
        if "slow_period" in params and "slow" not in params:
            params["slow"] = params.pop("slow_period")
        params.setdefault("fast", 10)
        params.setdefault("slow", 30)
        params["strategy_type"] = "ma_crossover"  # 统一为回测类型名
    # Bollinger 参数映射
    elif strategy_type in ("bollinger", "boll"):
        if "bb_period" in params and "period" not in params:
            params["period"] = params.pop("bb_period")
        if "std_dev" in params and "std_dev" not in params:
            pass
        params.setdefault("period", 20)
        params.setdefault("std_dev", 2.0)
    return params


def _format_backtest_result(backtest_result) -> dict | None:
    """将回测结果（dict 或 dataclass）转为统一字典"""
    if backtest_result is None:
        return None
    # 兼容 dict（run_backtest）和 dataclass（BacktestEngine）
    if isinstance(backtest_result, dict):
        return {
            "total_return_pct": backtest_result.get("total_return_pct", 0),
            "sharpe_ratio": backtest_result.get("sharpe_ratio", 0),
            "total_trades": backtest_result.get("total_trades", 0),
            "win_rate": backtest_result.get("win_rate", 0),
            "max_drawdown_pct": backtest_result.get("max_drawdown_pct", 0),
            "profit_factor": backtest_result.get("profit_factor", 0),
        }
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
