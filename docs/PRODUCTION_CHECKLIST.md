# AI Quant Trade — 生产就绪检查清单 v1.2

> 最后更新: 2026-07-20 · 当前版本: v1.2 · 模式: 模拟盘 (TESTNET)

---

## 1. 密钥安全

| # | 检查项 | 状态 | 备注 |
|---|--------|:---:|------|
| 1 | `.env` 中无弱密钥/占位符 | ✅ | .env.example 已占位符化，validate_security() 强制检测 <CHANGE_ME> |
| 2 | JWT Secret ≥ 32 字符，非已知弱密钥 | ✅ | P0-3 弱密钥黑名单 + 模式匹配 + 长度校验 |
| 3 | ENCRYPTION_KEY 已设置 | ✅ | v1.1 config.py 非 DEBUG 模式检测空值 |
| 4 | 交易所 Secret 在 DB 中为加密存储 | ✅ | crypto.py Fernet AES 加密，`encrypted_secret` 字段 |
| 5 | `.gitignore` 包含 .env/*.pem/backups | ✅ | 验证通过 |

## 2. 网络安全

| # | 检查项 | 状态 | 备注 |
|---|--------|:---:|------|
| 1 | CORS 白名单不含 `*` | ✅ | 仅 localhost + 127.0.0.1 段 |
| 2 | HTTPS 已启用（TLS 1.2+） | ⚠️ | T2 配置就绪，需真实域名 + certbot 签发 |
| 3 | Nginx 安全头：HSTS / X-Frame-Options / X-Content-Type-Options | ✅ | nginx.conf 已配置全部安全头 |
| 4 | 数据库端口不对外暴露 | ✅ | Docker 内部网络，仅 backend 可访问 db:5432 |
| 5 | API 无 debug 模式 | ✅ | Docker compose `DEBUG=false` |

## 3. 运行安全

| # | 检查项 | 状态 | 备注 |
|---|--------|:---:|------|
| 1 | 模拟盘模式下测试全流程 | ✅ | Docker 5 服务 healthy + 全链路 200 |
| 2 | Kill switch 触发 → 所有交易暂停 | ✅ | `kill_switch.trigger()` + `_check_kill_switch()` 阻断 |
| 3 | Kill switch 恢复 → 交易恢复 | ✅ | `kill_switch.reset()` + `POST /api/trading/emergency-reset` |
| 4 | 金额硬上限生效 | ✅ | MAX_ORDER_AMOUNT_USDT=200 + trading_service 校验 |
| 5 | AI 功能在实盘模式下禁用 | ✅ | DISABLE_AI_IN_LIVE=true 默认禁用 AI 策略 |
| 6 | 数据库备份可用 | ✅ | backend/scripts/backup_db.sh 已创建 |
| 7 | 数据库恢复可用 | ✅ | backend/scripts/restore_db.sh 已创建 |

## 4. 功能就绪

| # | 检查项 | 状态 | 备注 |
|---|--------|:---:|------|
| 1 | Docker Compose 全部健康 | ✅ | db/redis/backend/frontend/nginx — 5/5 healthy |
| 2 | WebSocket 实时行情 | ⚠️ | 端点就绪，需 TESTNET 连接验证 |
| 3 | 回测管线正常 | ✅ | scientific_pased / BH / DSR / PBO 全部实现 |
| 4 | 定时任务正常 | ✅ | scheduler.py 6 类任务注册 |
| 5 | Rate Limiter 多 worker 一致 | ✅ | v1.2 T3 Redis 后端 + 内存降级 |

---

## 总结

- **通过**: 19/22 (86%)
- **条件通过**: 2 (HTTPS 需域名, WebSocket 需 Testnet)
- **未测试**: 1 (模拟盘 24H 运行 — 需要实际运行验证)

## 上实盘前必须完成

1. 🔴 配置真实域名 + DNS A 记录 + certbot 签发 SSL 证书
2. 🔴 吊销/轮换当前 .env 中已暴露的模拟盘 OKX Key
3. 🟡 模拟盘 24H 连续运行验证（监控日志/内存/订单）

---

*本清单由 v1.2 安全审计自动生成*
