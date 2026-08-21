# TradePilot 上线前检查清单（Go-Live Checklist）

> 用于从 TESTNET（模拟盘）切到 LIVE（实盘）前的逐项确认。**每一项都确认通过后再切实盘。**
> 定位：个人小资金、有人值守。

---

## 1. 环境与密钥

- [ ] `.env` 已配置真实 OKX API Key / Secret / Passphrase（非 `<CHANGE_ME>` 占位符）
- [ ] `EXCHANGE_TESTNET=false`（确认要切实盘）
- [ ] `JWT_SECRET_KEY` 为 ≥32 字符强随机串（`python -c "import secrets; print(secrets.token_urlsafe(32))"`）
- [ ] `AUTH_DISABLED=false`（公网/实盘必须强鉴权，本地单机可保留 true）
- [ ] `ENCRYPTION_KEY` 已设置（Fernet 加密凭据）
- [ ] 确认无 `DEBUG=true`（生产应 `DEBUG=false`，避免 reload / 弱密钥放行）

## 2. 资金与风险上限（务必核对，默认值可能不适合你）

- [ ] `MAX_ORDER_AMOUNT_USDT`（单笔上限，默认 200）已按你的资金规模调整
- [ ] `MAX_TOTAL_POSITION_USDT`（总持仓上限，默认 2000）已确认
- [ ] `MAX_DAILY_LOSS_PCT`（日亏损熔断线，默认 5%）已确认
- [ ] `LIVE_SYMBOL_WHITELIST`（实盘交易对白名单）已确认只含你要交易的币
- [ ] `STOP_LOSS_PCT` / `TRAILING_STOP_PCT` 已按策略确认

## 3. 告警（有人值守的前提，必须配好）

- [ ] `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` 已配置（或用 `ALERT_WEBHOOK_URL`）
- [ ] 发一条测试消息确认能收到（触发 kill switch 或手动调 alert_service）
- [ ] 确认关键事件已接入：信号 / 止损 / 下单失败 / kill switch / 日亏熔断 / 对账差异 / 心跳掉线

## 4. 对账与数据真实性

- [ ] 后端启动日志出现 `RECONCILE OK`（启动对账通过，本地持仓 == 交易所持仓）
- [ ] 调度器每 5 分钟对账正常运行（`reconcile` 任务已注册）
- [ ] 确认无 mock 假数据（行情/回测/余额返回真实数据，失败返回错误而非随机值）

## 5. Kill Switch 与崩溃恢复

- [ ] 触发一次 kill switch → 确认撤单/平仓/停策略生效 → 再解除
- [ ] 重启后端 → 确认 RUNNING 策略能恢复（锁过期后自动拉起）
- [ ] 确认幽灵单反查生效（下单失败后按 clientOrderId 能查到实际订单）

## 6. 端到端最小闭环

- [ ] TESTNET 跑通至少 1 个策略：开仓 → 持仓可见 → 平仓 → Trade 落库 → 日志/绩效正确
- [ ] 前端仪表盘「最近成交」显示真实成交（非空/非假数据）
- [ ] 策略日志显示 created / started / heartbeat / order 等事件

## 7. 首次实盘（最小金额起步）

- [ ] 首笔实盘用最小金额（如 $10~20），确认下单/成交/持仓/平仓全链路正确
- [ ] 观察 24h，确认对账、告警、日结单都正常后再逐步加仓

---

## 常见坑位提醒

| 坑 | 表现 | 应对 |
|----|------|------|
| 单位错误 | 下单金额 vs 张数搞混 | 用 `MAX_ORDER_AMOUNT_USDT` 硬上限兜底，首笔小单验证 |
| 幽灵单 | 超时但已成交，本地当失败重下 | 已加 clientOrderId 反查，确认日志无 `order exception` 后未重复下单 |
| 持仓不同步 | 本地以为有仓但交易所没有 | 启动对账 + 每 5 分钟对账告警 |
| 告警静默 | 出事了没通知 | 上线前必须发测试告警确认收到 |

---

_配合 `MILESTONES_V6.md` 使用。任何一项打勾前，都不要切实盘。_
