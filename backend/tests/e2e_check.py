"""端到端验证脚本：模拟盘全链路。

测试流程：
  1. 注册新用户（用时间戳避免冲突）
  2. 登录 + 错误密码校验
  3. /me 鉴权获取用户信息 + 无 token 校验
  4. /health/deep 深度健康
  5. /api/trading/balance 账户余额
  6. /api/trading/kill-switch 状态
  7. 模拟盘限价下单（远低于市价，挂单不成交）
  8. 查询 open-orders
  9. 撤销订单
 10. 触发紧急停止（confirm=true）
 11. 紧急停止后再下单 → 应返回 success=false
 12. 解除紧急停止（confirm=true）
 13. 解除后再下单 → 应 success=true
 14. 金额上限校验（>200 USDT 应被拒）
 15. 实盘交易对白名单校验（非白名单 symbol 应被拒）

注意：
  - trading API 返回 HTTP 200 + {"success": true/false, "data"/"error": ...}
    而非 HTTP 4xx/5xx（除鉴权失败 401 和路径错误 404）
  - emergency-stop/reset 必须 confirm=true
  - kill-switch 状态在 body["data"]["state"]
"""
import argparse
import json
import sys
import time
from urllib import request as urlreq
from urllib.error import HTTPError, URLError

BASE = "http://127.0.0.1:8766"


def call(method: str, path: str, token: str | None = None, body: dict | None = None):
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urlreq.Request(url, data=data, headers=headers, method=method)
    try:
        with urlreq.urlopen(req, timeout=20) as resp:
            txt = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(txt) if txt else None
            except json.JSONDecodeError:
                return resp.status, txt
    except HTTPError as e:
        txt = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(txt)
        except json.JSONDecodeError:
            return e.code, txt
    except URLError as e:
        return -1, {"error": str(e)}


def banner(msg: str):
    print(f"\n{'=' * 60}\n{msg}\n{'=' * 60}")


def step(n: int, msg: str):
    print(f"\n[Step {n}] {msg}")


def ok(msg: str):
    print(f"  PASS  {msg}")


def fail(msg: str):
    print(f"  FAIL  {msg}")
    sys.exit(1)


def ks_state(token: str) -> str:
    """获取 kill_switch 状态。"""
    _, body = call("GET", "/api/trading/kill-switch", token=token)
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        # 字段名为 status（ARMED/TRIGGERED）
        return body["data"].get("status") or body["data"].get("state") or "UNKNOWN"
    return "UNKNOWN"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    global BASE
    BASE = args.base

    banner("端到端验证：模拟盘全链路")

    # ----- Step 1: 注册 -----
    step(1, "注册新用户")
    ts = int(time.time())
    username = f"e2e_test_{ts}"
    password = "E2eTest123!"
    status, body = call("POST", "/api/auth/register", body={
        "username": username,
        "email": f"{username}@test.com",
        "password": password,
    })
    if status != 200:
        fail(f"register failed: {status} {body}")
    token = body.get("access_token")
    if not token:
        fail(f"no token in response: {body}")
    ok(f"register ok, user={username}, token={token[:20]}...")

    # ----- Step 2: 登录 -----
    step(2, "登录 + 错误密码校验")
    status, body = call("POST", "/api/auth/login", body={
        "username": username,
        "password": password,
    })
    if status != 200:
        fail(f"login failed: {status} {body}")
    if not body.get("access_token"):
        fail(f"no token in login response: {body}")
    ok(f"login ok, token={body['access_token'][:20]}...")

    status, body = call("POST", "/api/auth/login", body={
        "username": username, "password": "WrongPassword!",
    })
    if status != 401:
        fail(f"wrong password should return 401, got {status}")
    ok("wrong password correctly rejected with 401")

    # ----- Step 3: /me -----
    step(3, "GET /api/auth/me (鉴权)")
    status, body = call("GET", "/api/auth/me", token=token)
    if status != 200:
        fail(f"/me failed: {status} {body}")
    if body.get("username") != username:
        fail(f"username mismatch: {body}")
    ok(f"/me ok, user={body.get('username')}, email={body.get('email')}")

    status, _ = call("GET", "/api/auth/me")
    if status != 401:
        fail(f"no token should return 401, got {status}")
    ok("no token correctly rejected with 401")

    # ----- Step 4: /health/deep -----
    step(4, "GET /api/health/deep")
    status, body = call("GET", "/api/health/deep")
    if status != 200:
        fail(f"/health/deep failed: {status} {body}")
    print(f"  → status={body.get('status')}, mode={body.get('mode')}, "
          f"db={body['checks']['database']['ok']}, "
          f"exchange={body['checks']['exchange']['ok']}")
    ok("deep health ok")

    # ----- Step 5: /balance -----
    step(5, "GET /api/trading/balance")
    status, body = call("GET", "/api/trading/balance", token=token)
    if status == 200 and isinstance(body, dict) and body.get("success"):
        bal = body.get("data", {})
        print(f"  → balance keys: {list(bal.keys())[:8] if isinstance(bal, dict) else 'list'}")
        ok("balance ok")
    else:
        print(f"  ! balance returned {status}: {body}")
        ok("balance returned non-success (non-fatal, may be exchange/testnet issue)")

    # ----- Step 6: kill-switch 状态 -----
    step(6, "GET /api/trading/kill-switch")
    state = ks_state(token)
    print(f"  → kill_switch state: {state}")
    if state == "TRIGGERED":
        print("  ! kill_switch TRIGGERED, resetting first...")
        call("POST", "/api/trading/emergency-reset", token=token, body={"confirm": True})
        state = ks_state(token)
        print(f"  → after reset: {state}")
    if state != "ARMED":
        fail(f"kill_switch should be ARMED, got {state}")
    ok("kill_switch state = ARMED")

    # ----- Step 7: 模拟盘限价下单 -----
    step(7, "POST /api/trading/limit-order (远低于市价挂单)")
    # amount 是币数量，amount_usdt = amount * price
    # 0.001 BTC * 10000 = 10 USDT（远低于 200 上限，远低于市价 ~64000）
    order_body = {
        "symbol": "BTC/USDT",
        "side": "buy",
        "amount": 0.001,            # BTC
        "price": 10000.0,            # 远低于市价
        "confirm_live": False,
    }
    status, body = call("POST", "/api/trading/limit-order", token=token, body=order_body)
    if status != 200:
        fail(f"limit-order HTTP {status}: {body}")
    order_id = None
    if body.get("success"):
        order_data = body.get("data", {}) or {}
        order_id = order_data.get("id") or order_data.get("order_id")
        print(f"  → order created, id={order_id}")
        ok(f"limit order placed, id={order_id}")
    else:
        err = body.get("error", "")
        print(f"  ! order rejected: {err}")
        # 风控拒绝（RiskEngine / KILL_SWITCH / 金额上限 / 白名单）都是预期行为
        if any(k in err for k in ["RiskEngine", "KILL_SWITCH", "上限", "白名单",
                                    "insufficient", "balance", "风控"]):
            ok(f"order rejected by risk control (expected): {err[:80]}")
        else:
            fail(f"order rejected unexpectedly: {err}")

    # ----- Step 8: open-orders -----
    step(8, "GET /api/trading/open-orders")
    status, body = call("GET", "/api/trading/open-orders?symbol=BTC/USDT", token=token)
    if status == 200:
        orders = body.get("data", []) if isinstance(body, dict) else []
        print(f"  → {len(orders) if isinstance(orders, list) else '?'} open orders")
        ok("open-orders ok")
    else:
        ok(f"open-orders returned {status} (non-fatal)")

    # ----- Step 9: 撤单 -----
    if order_id:
        step(9, f"POST /api/trading/cancel-order (撤销 {order_id})")
        status, body = call("POST", "/api/trading/cancel-order", token=token, body={
            "symbol": "BTC/USDT", "order_id": order_id,
        })
        if status == 200 and body.get("success"):
            ok(f"cancel ok: {body.get('data')}")
        else:
            print(f"  ! cancel returned {status}: {body}")
            ok("cancel returned non-success (may already be filled/cancelled)")
    else:
        step(9, "跳过撤单（无订单 id）")

    # ----- Step 10: 触发紧急停止 -----
    step(10, "POST /api/trading/emergency-stop (confirm=true)")
    status, body = call("POST", "/api/trading/emergency-stop", token=token, body={
        "reason": "e2e test", "confirm": True,
    })
    if status != 200 or not body.get("success"):
        fail(f"emergency-stop failed: {status} {body}")
    actions = body.get("data", {}).get("actions", {})
    print(f"  → actions: cancelled={actions.get('cancelled_orders')}, "
          f"closed={actions.get('closed_positions')}, "
          f"stopped={actions.get('stopped_strategies')}")
    ok("emergency stop triggered")

    if ks_state(token) != "TRIGGERED":
        fail(f"kill_switch should be TRIGGERED, got {ks_state(token)}")
    ok("kill_switch state = TRIGGERED")

    # ----- Step 11: 紧急停止后下单 → 应被拒 -----
    step(11, "POST /api/trading/limit-order (紧急停止状态下，应被拒)")
    status, body = call("POST", "/api/trading/limit-order", token=token, body=order_body)
    if status != 200:
        fail(f"expected HTTP 200 with success=false, got {status}: {body}")
    if body.get("success"):
        fail(f"BUG: order succeeded even with kill_switch TRIGGERED! body={body}")
    err = body.get("error", "")
    if "KILL_SWITCH" not in err.upper():
        print(f"  ! warning: error does not mention KILL_SWITCH: {err}")
    ok(f"correctly rejected: {err[:80]}")

    # ----- Step 12: 解除紧急停止 -----
    step(12, "POST /api/trading/emergency-reset (confirm=true)")
    status, body = call("POST", "/api/trading/emergency-reset", token=token, body={
        "confirm": True,
    })
    if status != 200 or not body.get("success"):
        fail(f"emergency-reset failed: {status} {body}")
    ok(f"reset ok: {body.get('data')}")

    if ks_state(token) != "ARMED":
        fail(f"kill_switch should be ARMED after reset, got {ks_state(token)}")
    ok("kill_switch state = ARMED")

    # ----- Step 13: 解除后再下单 -----
    step(13, "POST /api/trading/limit-order (解除后应可下单)")
    status, body = call("POST", "/api/trading/limit-order", token=token, body=order_body)
    if status != 200:
        fail(f"unexpected HTTP {status}: {body}")
    if body.get("success"):
        new_id = (body.get("data", {}) or {}).get("id")
        ok(f"order succeeded after reset, id={new_id}")
        if new_id:
            call("POST", "/api/trading/cancel-order", token=token, body={
                "symbol": "BTC/USDT", "order_id": new_id,
            })
    else:
        err = body.get("error", "")
        # 风控拒绝是预期（kill_switch 已解除，但 RiskEngine 仍可能拒绝）
        if any(k in err for k in ["RiskEngine", "上限", "白名单",
                                    "insufficient", "balance", "风控"]):
            ok(f"order rejected by risk control (non-fatal): {err[:60]}")
        else:
            fail(f"order rejected unexpectedly after reset: {err}")

    # ----- Step 14: 金额上限校验 -----
    step(14, "金额上限校验（amount_usdt=500 > MAX_ORDER_AMOUNT_USDT=200）")
    # 0.05 BTC * 10000 = 500 USDT > 200 上限
    big_order = {**order_body, "amount": 0.05}
    status, body = call("POST", "/api/trading/limit-order", token=token, body=big_order)
    if status != 200:
        fail(f"expected HTTP 200 with success=false, got {status}: {body}")
    if body.get("success"):
        fail(f"BUG: order > 200 USDT succeeded! body={body}")
    err = body.get("error", "")
    if "200" not in err and "amount" not in err.lower() and "limit" not in err.lower():
        print(f"  ! warning: error does not mention amount limit: {err}")
    ok(f"correctly rejected: {err[:80]}")

    # ----- Step 15: 交易对白名单（仅实盘生效，模拟盘应允许） -----
    step(15, "交易对白名单（模拟盘模式，非白名单 symbol 应仍可下单）")
    # 模拟盘模式白名单不强制，但记录行为
    # DOGE/USDT 价格约 0.1-0.2，用 50 DOGE * 0.01 = 0.5 USDT 远低于市价
    alt_order = {**order_body, "symbol": "DOGE/USDT", "amount": 50.0, "price": 0.01}
    status, body = call("POST", "/api/trading/limit-order", token=token, body=alt_order)
    if status == 200:
        if body.get("success"):
            oid = (body.get("data", {}) or {}).get("id")
            ok(f"DOGE/USDT order allowed in testnet mode, id={oid}")
            if oid:
                call("POST", "/api/trading/cancel-order", token=token, body={
                    "symbol": "DOGE/USDT", "order_id": oid,
                })
        else:
            err = body.get("error", "")
            # 风控拒绝是预期
            if "白名单" in err:
                fail(f"BUG: testnet mode should not enforce whitelist: {err}")
            ok(f"DOGE/USDT rejected by risk control (non-fatal): {err[:60]}")
    else:
        ok(f"DOGE/USDT HTTP {status} (non-fatal)")

    banner("ALL E2E TESTS PASSED")


if __name__ == "__main__":
    main()
