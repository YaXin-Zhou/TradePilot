# 紧急处理 Runbook

> AI 量化交易系统 · 紧急情况处理流程

## 场景 1：Kill Switch 已触发

kill_switch 由系统自动触发（风控异常/连续亏损）或手动触发。

### 检查当前状态

```bash
curl -s http://localhost/api/health
# kill_switch: "TRIGGERED" → 所有交易已冻结
```

### 诊断原因

```bash
docker logs ai_quant_backend --tail 100 | grep -i "kill_switch\|triggered"
```

### 恢复交易

```bash
TOKEN=$(curl -s -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"xxx"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost/api/trading/emergency-reset \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirm":true}'
```

---

## 场景 2：交易所 API 异常

### 症状
- `/api/health/deep` 返回 `exchange.ok: false`
- 下单返回错误
- 余额查询失败

### 步骤

1. 检查 OKX 控制台 API Key 状态
2. 检查网络连通性：`curl https://www.okx.com`
3. 重启后端：`docker compose restart backend`
4. 如仍异常 → 触发 kill_switch，等待交易所恢复

---

## 场景 3：容器崩溃/重启

### 症状
- `docker ps` 显示 `restarting` 或 `exited`
- 前端 502

### 步骤

```bash
# 1. 查看崩溃原因
docker logs ai_quant_backend --tail 100

# 2. 检查资源
docker stats --no-stream

# 3. 如果有磁盘空间问题
docker system prune -f

# 4. 重启
docker compose up -d backend
```

---

## 场景 4：对账差异

### 症状
`reconcile.py` 输出 FAILED

### 步骤

1. **立即触发 kill_switch**
2. 检查差异详情：
   ```bash
   cd backend && python scripts/reconcile.py
   ```
3. 差异类型判断：
   - `Position in exchange but NOT in DB` → 交易执行了但没记录，需手动补入 DB
   - `Position in DB but NOT in exchange` → DB 有脏数据，检查是否重复/错误
   - `Order in DB but NOT in exchange` → 订单状态未同步，手动更新 status
4. 差异补录后对账通过 → 恢复 kill_switch

---

## 场景 5：异常连续亏损

### 症状
某一策略连续亏损 ≥ 5 笔（系统会自动暂停该策略）

### 步骤

1. 确认策略已暂停：
   ```bash
   curl http://localhost/api/strategies/{id}
   # → status: "PAUSED"
   ```
2. 不要立即重启——等待 Regime 转换或市场趋势变化
3. 如需重启：`POST /api/strategies/{id}/resume`

---

## 快速参考卡片

```
┌─────────────────────────────────────────┐
│ 紧急停止    POST /trading/emergency-stop │
│ 恢复交易    POST /trading/emergency-reset│
│ 查看状态    GET  /trading/kill-switch    │
│ 健康检查    GET  /api/health/deep        │
│ 对账检查    python scripts/reconcile.py  │
│ 日志查看    docker logs ai_quant_backend  │
│ 重启服务    docker compose restart backend│
└─────────────────────────────────────────┘
```
