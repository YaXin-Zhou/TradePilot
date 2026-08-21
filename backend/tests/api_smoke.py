"""API 烟雾测试：覆盖所有 GET 端点 + 部分 POST 端点。
对每个端点发送请求，记录状态码和响应大小。
不验证业务逻辑，只验证端点可达 + 无 500 错误。
"""
import json
import time
from urllib import request as urlreq
from urllib.error import HTTPError, URLError

BASE = "http://127.0.0.1:8090"

# (method, path, body|None, 需要鉴权, 描述)
ENDPOINTS = [
    # health（无需鉴权）
    ("GET", "/api/health", None, False, "基础健康"),
    ("GET", "/api/health/deep", None, False, "深度健康"),
    # auth
    ("GET", "/api/auth/me", None, True, "当前用户"),
    # market（无需鉴权）
    ("GET", "/api/market/ticker?symbol=BTC/USDT", None, False, "行情"),
    ("GET", "/api/market/ohlcv?symbol=BTC/USDT&timeframe=1h&limit=10", None, False, "K线"),
    ("GET", "/api/market/orderbook?symbol=BTC/USDT&limit=5", None, False, "订单簿"),
    # trading
    ("GET", "/api/trading/balance", None, True, "余额"),
    ("GET", "/api/trading/open-orders?symbol=BTC/USDT", None, True, "挂单"),
    ("GET", "/api/trading/trades?symbol=BTC/USDT&limit=10", None, True, "成交记录"),
    ("GET", "/api/trading/kill-switch", None, True, "紧急停止状态"),
    # strategies
    ("GET", "/api/strategies/", None, True, "策略列表"),
    ("GET", "/api/strategies/pool/summary", None, True, "策略池摘要"),
    ("GET", "/api/strategies/pool/correlation", None, True, "策略池相关性"),
    ("GET", "/api/strategies/learner/weights", None, True, "学习器权重"),
    ("GET", "/api/strategies/learner/state", None, True, "学习器状态"),
    ("GET", "/api/strategies/heartbeat/last", None, True, "心跳最新"),
    ("GET", "/api/strategies/heartbeat/history?limit=5", None, True, "心跳历史"),
    # analysis
    ("GET", "/api/analysis/market-regime?symbol=BTC/USDT", None, True, "市场状态"),
    ("GET", "/api/analysis/risk-policies", None, True, "风控策略"),
    ("GET", "/api/analysis/weak-signals?symbol=BTC/USDT", None, True, "弱信号"),
    ("GET", "/api/analysis/feature-names", None, True, "特征名"),
    ("GET", "/api/analysis/fear-greed", None, True, "恐慌贪婪指数"),
    ("GET", "/api/analysis/open-interest?symbol=BTC/USDT", None, True, "持仓量"),
    ("GET", "/api/analysis/news-sentiment?symbol=BTC/USDT", None, True, "新闻情绪"),
    # portfolio
    ("GET", "/api/portfolio/summary", None, True, "组合摘要"),
    ("GET", "/api/portfolio/trades?limit=10", None, True, "组合成交"),
    ("GET", "/api/portfolio/performance?days=30", None, True, "组合表现"),
    # backtest
    ("GET", "/api/backtest/history", None, True, "回测历史"),
    ("GET", "/api/backtest/stats", None, True, "回测统计"),
    # exchange
    ("GET", "/api/exchange/status", None, True, "交易所状态"),
    # settings
    ("GET", "/api/settings/exchange", None, True, "交易所设置"),
]


def register() -> str:
    ts = int(time.time())
    body = {
        "username": f"smoke_{ts}",
        "email": f"smoke_{ts}@t.com",
        "password": "SmokeTest123!",
    }
    req = urlreq.Request(
        f"{BASE}/api/auth/register",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = json.loads(urlreq.urlopen(req, timeout=10).read())
    return resp["access_token"]


def call(method: str, path: str, token: str | None, body: dict | None = None):
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urlreq.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urlreq.urlopen(req, timeout=15)
        return resp.status, resp.read()
    except HTTPError as e:
        return e.code, e.read()
    except URLError as e:
        return -1, str(e).encode()
    except Exception as e:
        return -2, str(e).encode()


def main():
    print("=" * 70)
    print("API 烟雾测试：覆盖所有 GET 端点")
    print("=" * 70)

    token = register()
    print(f"\n注册用户成功，token={token[:20]}...\n")

    results = []
    for method, path, _, need_auth, desc in ENDPOINTS:
        status, body = call(method, path, token if need_auth else None)
        size = len(body)
        # 截取前 80 字符用于诊断
        preview = body[:80].decode("utf-8", errors="replace").replace("\n", " ")
        results.append((method, path, status, size, desc, preview))

    # 输出结果
    print(f"{'METHOD':<6} {'STATUS':<8} {'SIZE':<8} {'DESC':<16} PATH")
    print("-" * 110)
    pass_count = 0
    fail_count = 0
    warn_count = 0
    for method, path, status, size, desc, preview in results:
        marker = "✓" if 200 <= status < 300 else ("⚠" if status in (401, 403, 404) else "✗")
        if marker == "✓":
            pass_count += 1
        elif marker == "⚠":
            warn_count += 1
        else:
            fail_count += 1
        print(f"{method:<6} {status:<8} {size:<8} {desc:<16} {path}")
        if marker != "✓":
            print(f"       └─ {preview}")

    print("-" * 110)
    print(f"总计: {pass_count} 通过, {warn_count} 警告(4xx), {fail_count} 失败(5xx/网络)")
    print()
    if fail_count > 0:
        print("FAIL  存在 5xx 或网络错误的端点")
    else:
        print("PASS  所有端点可达，无 5xx 错误")


if __name__ == "__main__":
    main()
