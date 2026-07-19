"""交易服务层 — Phase 7.2 接入新风控引擎（regime_detector + risk_engine）

主路径：regime_detector.detect() → risk_engine.full_check()
兜底路径：core.risk.risk_manager.check_order()（当新引擎异常时）
"""
import asyncio
import uuid
from core.exchange import shared_exchange
from core.risk import risk_manager  # 兜底用
from core.logger import log
from services.risk_engine import risk_engine
from services.regime_detector import regime_detector, MarketRegime
from db.models import StrategyType


def _get_price(symbol: str) -> float:
    try:
        t = shared_exchange.fetch_ticker(symbol)
        return t.get("last", 0) or 0
    except Exception:
        return 0


async def _detect_regime(symbol: str) -> MarketRegime:
    """获取当前市场状态，失败默认 RANGING_LOW_VOL（最保守的震荡态）"""
    try:
        df = await asyncio.to_thread(shared_exchange.fetch_ohlcv, symbol, "1h", 200)
        if df is None or df.empty:
            return MarketRegime.RANGING_LOW_VOL
        ohlcv = df.to_dict("records")
        result = regime_detector.detect(ohlcv, symbol)
        return result.regime
    except Exception as e:
        log.warning(f"Regime detect failed for {symbol}: {e}, default to RANGING_LOW_VOL")
        return MarketRegime.RANGING_LOW_VOL


async def _get_total_capital() -> float:
    """获取总资金（USDT），失败默认 10000"""
    try:
        bal, _ = await get_balance()
        return bal.get("USDT", {}).get("total", 10000.0)
    except Exception:
        return 10000.0


async def _enhanced_risk_check(user_id: str, symbol: str, side: str,
                                amount_usdt: float) -> tuple[bool, str]:
    """主路径：regime_detector + risk_engine.full_check
    兜底：旧 risk_manager.check_order（当新引擎异常时）

    手动下单视为 CUSTOM 策略，跳过入场 Sharpe 门槛（sharpe_oos=999）。
    """
    if amount_usdt <= 0:
        return False, "Amount must be positive"

    try:
        regime = await _detect_regime(symbol)
        total_capital = await _get_total_capital()
        result = risk_engine.full_check(
            regime=regime,
            strategy_type=StrategyType.CUSTOM.value,
            sharpe_oos=999.0,  # 手动下单不检查 Sharpe
            total_capital=total_capital,
            current_position=0.0,
            new_amount=amount_usdt,
            strategy_position=0.0,
            daily_pnl=0.0,
            user_id=user_id,
        )
        if not result.passed:
            return False, f"[RiskEngine:{regime.value}] {result.reason}"
        return True, ""
    except Exception as e:
        log.warning(f"Enhanced risk check failed, fallback to legacy: {e}")
        return await risk_manager.check_order(user_id, symbol, side, amount_usdt)


async def get_balance() -> tuple[dict, bool]:
    try:
        bal = shared_exchange.fetch_balance()
        return bal, False
    except Exception as e:
        log.warning(f"Balance fetch failed: {e}")
        return {
            "USDT": {"free": 9850.42, "used": 150.00, "total": 10000.42},
            "BTC": {"free": 0.1158, "used": 0.0150, "total": 0.1308},
            "ETH": {"free": 2.5, "used": 0, "total": 2.5},
        }, True


async def place_limit_order(user_id: str, symbol: str, side: str, amount: float, price: float) -> tuple[dict | None, str | None, bool]:
    """下限量单。返回 (order, error_msg, is_mock)"""
    ok, msg = await _enhanced_risk_check(user_id, symbol, side, amount * price)
    if not ok:
        return None, msg, False
    try:
        order = shared_exchange.create_limit_order(symbol, side, amount, price)
        log.info(f"Limit order placed: {side} {amount} {symbol} @ {price}")
        return order, None, False
    except Exception as e:
        log.warning(f"Limit order failed (mock fallback): {e}")
        return {
            "id": str(uuid.uuid4())[:8],
            "symbol": symbol, "side": side,
            "price": price, "amount": amount,
            "filled": 0, "status": "open",
        }, None, True


async def place_market_order(user_id: str, symbol: str, side: str, amount: float) -> tuple[dict | None, str | None, bool]:
    """下市价单。返回 (order, error_msg, is_mock)"""
    est_price = _get_price(symbol)
    ok, msg = await _enhanced_risk_check(user_id, symbol, side, amount * est_price)
    if not ok:
        return None, msg, False
    try:
        order = shared_exchange.create_market_order(symbol, side, amount)
        log.info(f"Market order placed: {side} {amount} {symbol}")
        return order, None, False
    except Exception as e:
        log.warning(f"Market order failed (mock fallback): {e}")
        return {
            "id": str(uuid.uuid4())[:8],
            "symbol": symbol, "side": side,
            "amount": amount, "filled": amount,
            "price": 0, "status": "closed",
        }, None, True


def get_open_orders(symbol: str) -> tuple[list, bool]:
    try:
        orders = shared_exchange.fetch_open_orders(symbol)
        return orders, False
    except Exception:
        return [], True


def get_trade_history(symbol: str, limit: int = 50) -> tuple[list, bool]:
    try:
        trades = shared_exchange.fetch_my_trades(symbol, limit)
        return trades, False
    except Exception:
        return [], True
