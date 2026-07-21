# 启动 Runbook

> AI 量化交易系统 · 标准启动流程

## 前置条件

- Docker Desktop 已安装并运行
- `.env` 文件已配置（API Key / JWT Secret / Encryption Key）

## 启动步骤

### 1. 启动全部服务

```bash
cd ai_quant_trade
docker compose up -d
```

预期输出：
```
Container ai_quant_db Running
Container ai_quant_redis Running
Container ai_quant_backend Started
Container ai_quant_frontend Started
Container ai_quant_nginx Started
```

### 2. 等待健康检查通过

```bash
watch -n 5 "docker ps --format '{{.Names}}: {{.Status}}'"
```

90 秒内所有容器应变为 `(healthy)`：
```
ai_quant_backend: Up ... (healthy)
ai_quant_nginx: Up ... (healthy)
ai_quant_frontend: Up ... (healthy)
ai_quant_db: Up ... (healthy)
ai_quant_redis: Up ... (healthy)
```

### 3. 验证核心功能

```bash
# 系统健康
curl http://localhost/api/health
# → {"status":"ok","exchange":"okx","testnet":true,...}

# 深度健康（含交易所）
curl http://localhost/api/health/deep
# → checks.exchange.ok = true

# 交易所对账
cd backend && python scripts/reconcile.py
# → RECONCILE OK

# 前端
curl -o /dev/null -s -w "%{http_code}" http://localhost
# → 200
```

### 4. 启动策略（模拟盘）

```bash
# 创建策略
curl -X POST http://localhost/api/strategies/ \
  -H "Content-Type: application/json" \
  -d '{"name":"btc_grid","type":"grid","symbol":"BTC/USDT",
       "config":{"lower_price":75000,"upper_price":95000,"grid_count":20,
                 "order_amount":10,"stop_loss_pct":5}}'

# 启动策略
curl -X POST http://localhost/api/strategies/btc_grid/start
```

### 5. 确认运行

```bash
# 查看策略状态
curl http://localhost/api/strategies/pool/summary

# 查看持仓
curl http://localhost/api/portfolio/summary
```

## 异常处理

| 症状 | 诊断 | 处理 |
|------|------|------|
| backend unhealthy | `docker logs ai_quant_backend --tail 50` | 检查 DB 连接、Alembic 迁移 |
| exchange offline | `.env` 确认 API Key 正确 | 检查 OKX 控制台 Key 状态 |
| 端口冲突 | `netstat -an \| grep 8000` | 修改 `.env` PORT |
