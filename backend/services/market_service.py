"""行情数据服务层"""
import core.exchange as exmod
from core.logger import log


def _get_exchange():
    """动态获取 shared_exchange 实例（避免热重建后引用过期）"""
    return exmod.shared_exchange


def get_ticker(symbol: str) -> tuple[dict, bool]:
    """获取行情。返回 (data, is_mock)。

    v5: 交易所失败时返回空 dict + is_mock=True，不再生成随机假数据，
    前端据 is_mock 显示「连接异常/模拟模式」，而非伪造价格。
    """
    try:
        ticker = _get_exchange().fetch_ticker(symbol)
        return ticker, False
    except Exception as e:
        log.warning(f"Ticker fetch failed for {symbol}: {e}")
        return {}, True


def get_ohlcv(symbol: str, timeframe: str, limit: int) -> tuple[list, bool]:
    """获取 K 线。返回 (data, is_mock)。

    v5: 失败返回空列表 + is_mock=True，不生成假 K 线。
    """
    try:
        df = _get_exchange().fetch_ohlcv(symbol, timeframe, limit)
        return df.to_dict(orient="records"), False
    except Exception as e:
        log.warning(f"OHLCV fetch failed for {symbol}: {e}")
        return [], True


def get_orderbook(symbol: str, limit: int) -> tuple[dict, bool]:
    """获取订单簿。返回 (data, is_mock)。

    v5: 失败返回空 dict + is_mock=True，不生成假深度。
    """
    try:
        ob = _get_exchange().fetch_orderbook(symbol, limit)
        return ob, False
    except Exception as e:
        log.warning(f"Orderbook fetch failed for {symbol}: {e}")
        return {}, True
