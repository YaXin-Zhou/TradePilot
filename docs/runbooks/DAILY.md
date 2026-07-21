# 日常检查 Runbook

> AI 量化交易系统 · 每日运维检查清单（每天早晚各一次）

## 快速检查

```bash
# 一键检查脚本（复制粘贴执行）
echo "=== $(date) 每日检查 ==="
echo "1. 容器状态:" && docker ps --format "{{.Names}}: {{.Status}}"
echo "2. 应用健康:" && curl -s http://localhost/api/health
echo "3. 应用错误:" && curl -s http://localhost/api/metrics | python -c "import sys,json;d=json.load(sys.stdin);print(f'errors={d[\"recent_errors\"]} queue={d[\"pending_order_records\"]} strats={d[\"active_strategies\"]}')"
echo "4. 资源:" && docker stats --no-stream --format "{{.Name}}: {{.MemUsage}}"
echo "5. 对账:" && cd backend && python scripts/reconcile.py 2>&1 | tail -1
echo "=== 检查完成 ==="
```

## 逐项检查清单

| # | 检查项 | 命令 | 正常标准 |
|---|--------|------|------|
| 1 | 容器状态 | `docker ps` | 全部 healthy |
| 2 | 应用健康 | `curl /api/health` | `"status":"ok"` |
| 3 | 深度健康 | `curl /api/health/deep` | `exchange.ok:true, database.ok:true` |
| 4 | 应用错误 | `curl /api/metrics` | `recent_errors:0, pending:0` |
| 5 | 内存 | `docker stats --no-stream` | Backend < 1.2GB |
| 6 | 对账 | `python scripts/reconcile.py` | `RECONCILE OK` |
| 7 | DB 备份 | `bash scripts/backup_db.sh` | 生成 .sql.gz |
| 8 | 策略状态 | `curl /api/strategies/pool/summary` | 预期数量 running |
| 9 | 盈亏 | `curl /api/portfolio/performance?days=1` | 在预期范围 |
| 10 | 日志异常 | `docker logs --since 24h ai_quant_backend \| grep ERROR` | 0 或已知可忽略 |

## 异常记录

| 时间 | 异常描述 | 处理 | 解决 |
|------|----------|------|:---:|
| | | | |
| | | | |

## 每日简报模板

```
AI Quant Trade 每日简报
日期: YYYY-MM-DD
模式: TESTNET / LIVE

· 运行时长: XXh
· 活跃策略: X 个
· 当日成交: X 笔
· 当日盈亏: ±X USDT
· 对账: OK
· 错误: 0
· 异常: 无
```
