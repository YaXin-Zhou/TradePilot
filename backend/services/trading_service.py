"""交易服务层"""
import uuid
from core.exchange import shared_exchange
from core.risk import risk_manager
from core.logger import log


def _get_price(symbol: str) -> float:
    try:
        t = shared_exchange.fetch_ticker(symbol)
        return t.get("last", 0) or 0
    except Exception:
        return 0


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
    ok, msg = await risk_manager.check_order(user_id, symbol, side, amount * price)
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
    ok, msg = await risk_manager.check_order(user_id, symbol, side, amount * est_price)
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
