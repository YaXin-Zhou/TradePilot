# 停机 Runbook

> AI 量化交易系统 · 标准停机流程

## 重要原则

**先停策略，再停服务。** 不能在还有挂单/持仓时直接关闭系统。

## 停机步骤

### 1. 停止所有策略

```bash
# 列出运行中策略
curl http://localhost/api/strategies/

# 逐个停止
curl -X POST http://localhost/api/strategies/{strategy_id}/stop
```

### 2. 取消所有挂单

```bash
# 检查是否有未成交订单
curl http://localhost/api/trading/open-orders?symbol=BTC/USDT

# 如有挂单，撤单（可登录 OKX 手动操作）
```

### 3. 确认持仓安全

```bash
# 查看当前持仓
curl http://localhost/api/portfolio/summary

# 如有风险仓位，手动平仓
```

### 4. 对账

```bash
cd backend && python scripts/reconcile.py
# 必须输出 RECONCILE OK 才能停机
```

### 5. 数据库备份

```bash
cd backend && bash scripts/backup_db.sh
```

### 6. 停止服务

```bash
docker compose down
```

验证：
```bash
docker ps -a | grep ai_quant
# 应无输出
```

## 紧急停机（kill_switch）

如果出现异常需要秒级停止交易：

```bash
# 注册用户获取 token
TOKEN=$(curl -s -X POST http://localhost/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"emergency","password":"stop123"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 触发紧急停止
curl -X POST http://localhost/api/trading/emergency-stop \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirm":true}'

# 验证
curl -s http://localhost/api/trading/kill-switch \
  -H "Authorization: Bearer $TOKEN"
# → status: "TRIGGERED"
```

紧急停止后，所有下单请求会被拒绝，已有挂单保持不变（需手动处理）。
