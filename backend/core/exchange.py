"""
OKX 交易所客户端 - 基于 CCXT 封装

Phase 8 修复：
  - 修复 _connected 状态 bug（成功操作后误设为 False）
  - 指数退避重连（3s→6s→12s→24s→60s 上限）
  - 所有操作成功后正确标记 connected
"""
import ccxt
import os
import time
from typing import Optional

import pandas as pd


class ExchangeError(Exception):
    pass


class ExchangeClient:
    """统一交易所接口，默认 OKX"""

    # 指数退避重连间隔（秒），上限 60s
    _RECONNECT_INTERVALS = [1, 2, 4, 8, 15, 30, 60]

    def __init__(
        self,
        exchange_name: str = "okx",
        api_key: str = "",
        secret: str = "",
        passphrase: str = "",
        testnet: bool = True,
    ):
        exchange_class = getattr(ccxt, exchange_name)
        params = {
            "enableRateLimit": True,
            "timeout": 8000,
            "options": {"defaultType": "swap"},
        }
        # Auto-detect proxy from env vars
        proxy_url = (
            settings.HTTPS_PROXY or settings.HTTP_PROXY or
            os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or
            os.environ.get("https_proxy") or os.environ.get("http_proxy") or
            ""
        )
        if proxy_url:
            params["proxies"] = {"http": proxy_url, "https": proxy_url}
            params["timeout"] = 15000
        if api_key and secret:
            params["apiKey"] = api_key
            params["secret"] = secret
            if passphrase:
                params["password"] = passphrase

        self._exchange = exchange_class(params)
        if testnet:
            self._exchange.set_sandbox_mode(True)
            # OKX 模拟盘用同一个域名(okx.com)，通过 x-simulated-trading header 区分
            # 不需要改 URL——okx.cab 在国内不可达
            log.info(f"ExchangeClient: sandbox mode enabled for {exchange_name}")
        self._markets_loaded = False
        self._testnet = testnet
        self._connected = False
        self._name = exchange_name
        self._last_attempt = 0.0
        self._reconnect_idx = 0  # 指数退避索引


    # ---- Connection lifecycle ----

    def connect_with_retry(self, max_retries: int = 3) -> bool:
        """启动时主动连接，短间隔重试（1s/2s/4s）。

        返回 True 表示连接成功，False 表示全部失败。
        """
        import time as _t
        for attempt in range(max_retries):
            try:
                self._exchange.load_markets()
                self._markets_loaded = True
                self._connected = True
                self._reconnect_idx = 0
                self._last_attempt = _t.time()
                log.info(f"ExchangeClient: connected on attempt {attempt + 1}/{max_retries}")
                return True
            except Exception as e:
                wait = 2 ** attempt
                log.warning(f"ExchangeClient: attempt {attempt + 1}/{max_retries} failed ({e}), retry in {wait}s")
                _t.sleep(wait)
        self._last_attempt = _t.time()
        log.error("ExchangeClient: all startup connection attempts failed")
        return False

    def _ensure_markets(self):
        if self._markets_loaded:
            return
        try:
            self._exchange.load_markets()
            self._markets_loaded = True
            self._connected = True
            log.debug(f"ExchangeClient: markets loaded from {self._exchange.hostname}")
        except Exception as e:
            # FIX: 不重置 _last_attempt，避免干扰 _try_reconnect 的指数退避
            self._markets_loaded = False
            self._connected = False
            log.warning(f"ExchangeClient: load_markets failed from {self._exchange.hostname}: {e}")

    def _try_reconnect(self) -> bool:
        """尝试重连，指数退避。返回当前是否连接"""
        if self._connected:
            return True
        now = time.time()
        # 当前退避间隔
        interval = self._RECONNECT_INTERVALS[min(self._reconnect_idx, len(self._RECONNECT_INTERVALS) - 1)]
        if now - self._last_attempt >= interval:
            original_timeout = self._exchange.timeout
            try:
                # 加 5 秒超时，防止 DNS 查询无限等待
                self._exchange.timeout = min(5000, original_timeout)
                self._exchange.load_markets()
                self._markets_loaded = True
                self._connected = True
                self._reconnect_idx = 0  # 重置退避
                return True
            except Exception as e:
                # 快速失败，记录但不抛出
                from core.logger import log
                log.debug(f"Exchange reconnect attempt {self._reconnect_idx + 1} failed: {type(e).__name__}")
                self._last_attempt = now
                self._reconnect_idx = min(self._reconnect_idx + 1, len(self._RECONNECT_INTERVALS) - 1)
            finally:
                # FIX: 恢复原始 timeout，避免永久降低后续请求的 timeout
                self._exchange.timeout = original_timeout
        return self._connected

    def _mark_success(self):
        """操作成功后调用"""
        self._connected = True
        self._reconnect_idx = 0

    def _mark_failure(self):
        """操作失败后调用"""
        self._connected = False
        self._last_attempt = time.time()

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_connected(self) -> bool:
        """是否已连接（修复 BUG-6：main.py 访问 _connected 私有属性）"""
        return self._connected

    @property
    def is_testnet(self) -> bool:
        return self._testnet

    def fetch_ticker(self, symbol: str) -> dict:
        self._try_reconnect()
        if not self._connected:
            raise ConnectionError("offline")
        try:
            t = self._exchange.fetch_ticker(symbol)
            self._mark_success()  # FIX: 成功后标记连接正常（原代码错误地设为 False）
            return {
                "symbol": symbol,
                "bid": float(t.get("bid", 0)),
                "ask": float(t.get("ask", 0)),
                "last": float(t.get("last", 0)),
                "high": float(t.get("high", 0)),
                "low": float(t.get("low", 0)),
                "volume": float(t.get("baseVolume", 0)),
                "quote_volume": float(t.get("quoteVolume", 0)),
                "change_pct": float(t.get("percentage", 0)),
                "timestamp": t.get("timestamp", 0),
            }
        except Exception as e:
            self._mark_failure()
            raise ConnectionError(f"offline: {e}")

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200):
        self._try_reconnect()
        if not self._connected:
            raise ConnectionError("offline")
        try:
            ohlcv = self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(
                ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df["symbol"] = symbol
            self._mark_success()  # FIX
            return df
        except Exception as e:
            self._mark_failure()
            raise ConnectionError(f"offline: {e}")

    def fetch_orderbook(self, symbol: str, limit: int = 20) -> dict:
        self._try_reconnect()
        if not self._connected:
            raise ConnectionError("offline")
        try:
            ob = self._exchange.fetch_order_book(symbol, limit)
            self._mark_success()  # FIX
            return {
                "bids": [[float(p), float(v)] for p, v in ob.get("bids", [])],
                "asks": [[float(p), float(v)] for p, v in ob.get("asks", [])],
                "timestamp": ob.get("timestamp", 0),
            }
        except Exception as e:
            self._mark_failure()
            raise ConnectionError(f"offline: {e}")

    def fetch_balance(self, currency: Optional[str] = None) -> dict:
        self._ensure_markets()
        self._try_reconnect()
        if not self._connected:
            raise ConnectionError('offline')
        try:
            bal = self._exchange.fetch_balance()
            self._mark_success()  # FIX
            if currency:
                c = bal.get(currency, {})
                return {
                    "currency": currency,
                    "free": float(c.get("free", 0) or 0),
                    "used": float(c.get("used", 0) or 0),
                    "total": float(c.get("total", 0) or 0),
                }
            result = {}
            for cur, _ in bal.get("total", {}).items():
                total = float(bal.get(cur, {}).get("total", 0) or 0)
                if total > 0:
                    result[cur] = {
                        "free": float(bal.get(cur, {}).get("free", 0) or 0),
                        "used": float(bal.get(cur, {}).get("used", 0) or 0),
                        "total": total,
                    }
            return result
        except Exception as e:
            self._mark_failure()
            raise ConnectionError(f"offline: {e}")

    def _to_price(self, symbol: str, price: float) -> float:
        self._ensure_markets()
        return float(self._exchange.price_to_precision(symbol, price))

    def _to_amount(self, symbol: str, amount: float) -> float:
        self._ensure_markets()
        return float(self._exchange.amount_to_precision(symbol, amount))

    def create_limit_order(self, symbol: str, side: str, amount: float, price: float) -> Optional[dict]:
        self._ensure_markets()
        price = self._to_price(symbol, price)
        amount = self._to_amount(symbol, amount)
        try:
            order = self._exchange.create_limit_order(symbol, side, amount, price)
            self._mark_success()
            return {
                "id": order.get("id"),
                "symbol": symbol,
                "side": side,
                "price": float(order.get("price") or price),
                "amount": float(order.get("amount") or amount),
                "filled": float(order.get("filled") or 0),
                "cost": float(order.get("cost") or 0),
                "status": order.get("status", "open"),
                "timestamp": order.get("timestamp"),
            }
        except Exception as e:
            self._mark_failure()
            raise ExchangeError(f"下单失败: {e}")

    def create_market_order(self, symbol: str, side: str, amount: float) -> Optional[dict]:
        self._ensure_markets()
        try:
            order = self._exchange.create_market_order(symbol, side, amount)
            self._mark_success()
            return {
                "id": order.get("id"),
                "symbol": symbol,
                "side": side,
                "price": float(order.get("price") or 0),
                "amount": float(order.get("amount") or amount),
                "filled": float(order.get("filled") or 0),
                "cost": float(order.get("cost") or 0),
                "status": order.get("status", "closed"),
                "timestamp": order.get("timestamp"),
            }
        except Exception as e:
            self._mark_failure()
            raise ExchangeError(f"市价单失败: {e}")

    def fetch_order(self, order_id: str, symbol: str) -> Optional[dict]:
        self._ensure_markets()
        try:
            o = self._exchange.fetch_order(order_id, symbol)
            self._mark_success()
            return {
                "id": o.get("id"),
                "symbol": symbol,
                "side": o.get("side"),
                "price": float(o.get("price", 0)),
                "amount": float(o.get("amount", 0)),
                "filled": float(o.get("filled", 0)),
                "cost": float(o.get("cost", 0)),
                "status": o.get("status"),
                "timestamp": o.get("timestamp"),
            }
        except Exception as e:
            self._mark_failure()
            return None

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            self._exchange.cancel_order(order_id, symbol)
            self._mark_success()
            return True
        except Exception as e:
            self._mark_failure()
            log.warning(f"cancel_order failed: {order_id} {symbol}: {e}")
            return False

    def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """撤销所有挂单（或指定交易对）。返回撤销数量"""
        self._ensure_markets()
        try:
            if symbol:
                orders = self._exchange.fetch_open_orders(symbol)
            else:
                orders = self._exchange.fetch_open_orders()
            cancelled = 0
            for o in orders:
                try:
                    self._exchange.cancel_order(o["id"], o.get("symbol", symbol or ""))
                    cancelled += 1
                except Exception as e:
                    log.warning(f"cancel_all: failed to cancel {o.get('id')}: {e}")
            self._mark_success()
            return cancelled
        except Exception as e:
            self._mark_failure()
            log.error(f"cancel_all_orders failed: {e}")
            return 0

    def fetch_open_orders(self, symbol: str) -> list[dict]:
        self._ensure_markets()
        try:
            orders = self._exchange.fetch_open_orders(symbol)
            self._mark_success()
            return [
                {
                    "id": o.get("id"),
                    "side": o.get("side"),
                    "price": float(o.get("price", 0)),
                    "amount": float(o.get("amount", 0)),
                    "filled": float(o.get("filled", 0)),
                    "status": o.get("status"),
                }
                for o in orders
            ]
        except Exception as e:
            self._mark_failure()
            log.warning(f"fetch_open_orders failed: {e}")
            return []

    def fetch_my_trades(self, symbol: str, limit: int = 50) -> list[dict]:
        self._ensure_markets()
        self._try_reconnect()
        if not self._connected:
            return []
        try:
            trades = self._exchange.fetch_my_trades(symbol, limit=limit)
            self._mark_success()
            return [
                {
                    "id": t.get("id"),
                    "side": t.get("side"),
                    "price": float(t.get("price", 0)),
                    "amount": float(t.get("amount", 0)),
                    "cost": float(t.get("cost", 0)),
                    "fee": float(t.get("fee", {}).get("cost", 0)) if t.get("fee") else 0,
                    "timestamp": t.get("timestamp"),
                }
                for t in trades
            ]
        except Exception as e:
            # API 参数/业务错误不应影响连接状态（仅网络错误才 mark_failure）
            err_str = str(e)
            if "offline" in err_str.lower() or "timeout" in err_str.lower() or "connection" in err_str.lower():
                self._mark_failure()
            log.warning(f"fetch_my_trades failed: {e}")
            return []

    def test_connection(self) -> tuple[bool, str, int]:
        """测试连通性，返回 (ok, message, latency_ms)"""
        import time as _t
        self._ensure_markets()
        start = _t.time()
        ok = self._try_reconnect()
        latency = int((_t.time() - start) * 1000)
        if ok:
            return True, "connected", latency
        return False, "offline", latency


# Single shared exchange instance for all API modules
from config import settings
from core.logger import log

shared_exchange = ExchangeClient(
    exchange_name=settings.EXCHANGE_NAME,
    api_key=settings.EXCHANGE_API_KEY,
    secret=settings.EXCHANGE_SECRET,
    passphrase=settings.EXCHANGE_PASSPHRASE,
    testnet=settings.EXCHANGE_TESTNET,
)


def get_shared() -> ExchangeClient:
    """动态获取 shared_exchange 实例。

    用于热重建场景：settings API 保存新 API Key 后会替换 shared_exchange，
    旧引用（模块加载时的快照）会失效。所有模块应改用此函数获取实例。
    """
    return shared_exchange
