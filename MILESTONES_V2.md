# TradePilot v2.0 合约版 — 里程碑与修复路线图

> **版本**：v2.0.0（2026-07-21）
> **定位**：只跑 OKX 永续合约（swap），不再混用现货语义。
> **来源**：基于《深度全面评估报告》（综合 4.5/10，自评 7.2 被高估）的推荐行动路线。
> **原则**：先让系统「能起、能停、能止损、单位正确」，再补资金安全，最后补统计可信度与工程化。

---

## 0. 本次版本（v2.0.0）已交付

### 0.1 现货 → 合约统一（✅ 已完成）
| 改动 | 文件 |
|---|---|
| 新增 `fetch_positions()`（合约持仓真源） | `core/exchange.py` |
| `create_market_order` 支持 `reduce_only` | `core/exchange.py` |
| 持仓/资产跟踪改合约口径（双向持仓、名义价值、未实现盈亏、杠杆） | `services/portfolio_service.py` |
| 平仓改 reduce-only（多→卖、空→买） | `api/portfolio.py` |
| 紧急停止平仓改 `fetch_positions` + reduce-only | `services/trading_service.py` |
| API Key 权限校验 `defaultType` spot → swap | `api/settings.py` |
| 对账脚本改合约持仓 | `scripts/reconcile.py` |

### 0.2 阻断性 P0 修复（✅ 已完成）
| 缺陷 | 修复 |
|---|---|
| `EXCHANGE_TRADE_MODE` 未定义 → `/api/health` 500 → Docker 栈起不来 | `config.py` 新增属性 |
| 止损 `sm.config.stop_price` AttributeError → 永不平仓 | `runner.py:527` → `result.stop_price` |
| 紧急停止撤单被自身 kill_switch 拦截 | `trading_service.py` 直接调交易所撤单 |
| kill_switch 卖单放行 = 合约开空绕过冻结 | 移除卖单放行，平仓走 reduce-only |

---

## 1. 阶段二 — 资金安全（P1，最高优先级）

> 目标：让「四层风控」和「审计/幂等」真正生效，而非死代码。

### 1.1 接回硬上限 + 白名单 + 风控
- [x] `_check_amount_limit` 恢复 `MAX_ORDER_AMOUNT_USDT` / `MAX_TOTAL_POSITION_USDT` 硬上限，并在 `place_market_order`/`place_limit_order` 入口强制调用
- [x] `_check_symbol_whitelist` 接入下单路径（实盘白名单）
- [x] 删除死代码 `_check_risk_engine`（或真正接入，异常时**默认拒绝**而非放行）

### 1.2 幂等真正生效
- [x] 幂等键改为 uuid 唯一值，通过 `clientOrderId` 传给 OKX
- [x] `Order.idempotency_key` 加 `unique=True`，下单前 `_find_existing_order` 查重
- [x] 超时/失败后用 `clientOrderId` 反查交易所（`_reconcile_order_by_client_id`）再决定是否落库

### 1.3 自动策略统一走审计/落库
- [x] `runner` 下单/平仓后调用 `record_strategy_order` 写入 `orders` + `audit_logs`
- [x] 让订单补偿链（重试→补偿审计→内存队列→30s 补偿）覆盖自动交易

### 1.4 风控五维真正生效
- [x] runner 传入真实 `daily_pnl`（由 Trade 表汇总），日亏损熔断不再恒 0
- [x] runner 传入 `strategy_returns`/`pool_returns`（best-effort 取自策略池），相关性检查不再恒跳过
- [x] 无回测策略不再默认 Sharpe=1.0（改从 Strategy 表取，无回测默认 0 交由门槛拦截）

### 1.5 其他资金安全
- [x] `_get_daily_realized_loss` 补实现（当前未定义，开启日亏损即 NameError）
- [x] `account_id` 真正路由到 `exchange_registry`，创建失败抛错而非静默回退主账户
- [x] runner 乐观锁改 `SELECT ... FOR UPDATE`（PG 行级锁），防多实例重复交易
- [x] 平仓后保留剩余仓位（部分成交不再整体丢失）

### 1.6 权限模型
- [x] 关闭开放注册（首个用户自动成为管理员，后续需管理员邀请）
- [x] 引入 `is_admin` + `require_admin`，对交易、`emergency-reset`、settings、API Key 管理强制管理员权限

---

## 2. 阶段三 — 统计可信度（P1，让 AI 结论可信）

> 目标：修好 PBO/SPA/DSR/NW，消除前视偏差，让 AI 产物可交易。

### 2.1 统计检验校正
- [ ] PBO 改为 CSCV（Combinatorially Symmetric Cross-Validation），或换 `quantstats`/`vectorbt`（当前实现退化，建议换成熟库）
- [ ] SPA 改为正确的 stationary bootstrap + studentized max 统计量（当前恒 p≈0，建议换成熟库）
- [ ] DSR 采用 Bailey & López de Prado 真实公式（含偏度/峰度/试验次数，当前是伪公式）
- [x] Newey-West 标准误补 `1/√T` 因子
- [ ] `scientific_passed` 纳入 DSR、NW t、真实 BH p 值（PBO/SPA 修复后一并整改）
- [x] Sharpe 年化因子修正：1h K 线 `sqrt(24*365)`（此前误用 365 低估 4.9 倍）

### 2.2 消除前视偏差
- [x] 回测信号用前一根 K 线（MA/RSI/布林带均 shift(1)），杜绝当前收盘价信号在当前收盘价成交

### 2.3 AI 闭环闭合
- [x] 补 `ml.models.train_model` 函数（scheduler 每 24h 引用但函数不存在）
- [x] `ai_heartbeat` 字段名对齐 `PoolStrategy`（`strategy_id/sharpe/max_drawdown` → `id/running_sharpe/running_max_dd` + summary 键名）
- [ ] AI 迭代用滚动/前进式窗口 + purge/embargo，避免 OOS 泄漏（待做）
- [x] 交易所断连时**禁止**用随机模拟数据做「科学验证」（is_mock 时中止迭代）
- [x] `ma_cross.py`/`bollinger.py` 的 `analyze()` 补真实实现（当前恒 HOLD）
- [x] 修复 `GridStrategy` 构造签名不匹配（`runner.py` vs `grid.py`）

### 2.4 在线学习接线
- [ ] `online_learner.update()` 挂入定时任务，权重喂给 `strategy_pool.weight` / `portfolio_allocator`
- [ ] `strategy_pool.update_performance()` 接入生产循环，让自动休眠/淘汰/相关性真正生效
- [ ] 清理死代码：`signal_matrix`、`onchain_data`、`validation_pipeline` 的桩函数

---

## 3. 阶段四 — 工程化与部署（P1/P2）

> 目标：让 CI 真变红、Windows 能本地开发、生产能起 HTTPS。

### 3.1 CI 真正有效
- [x] 删除 `ci.yml` 里所有 `|| true`（pytest/npm test 失败即红）
- [x] 移除 `--timeout` 参数（依赖缺失导致测试从未真正跑）
- [x] 统一 Python 版本为 3.13

### 3.2 部署与跨平台
- [x] `database.py` 的 `import fcntl` 加 Windows 兜底（无 fcntl 时跳过文件锁）
- [x] `scheduler.py` 的 `OR IGNORE` → `ON CONFLICT DO NOTHING`（PostgreSQL，SQLite 保留 OR IGNORE）
- [x] 锁定 `pandas<2.0`（兼容 pandas-ta 0.4.71b0）
- [ ] HTTPS 真正生效：挂载 `nginx.ssl.conf` 或用 envsubst 模板注入 DOMAIN
- [ ] DB/Redis 弱凭据改必填占位 + 端口默认不发布宿主；Redis 加 `requirepass`

### 3.3 前端契约
- [x] 补 `/api/analysis/train` 路由（后端补上，前端按钮恢复可用）
- [x] 修复 `r.success && r.data` 信封判断（trading.tsx 手动风控 + strategies.tsx 策略池）
- [x] 补 10 个 i18n 缺失 key（trade.symbol/trading.orderbook/strat.*/analysis.*）
- [x] 持仓页 `positions.tsx`/`types/portfolio.ts` 适配合约字段（v2.0 已完成）
- [x] 挂回 `/backtest` 导航（清理重复 AI 页待做）
- [ ] 重写 Vitest/Playwright 为真实组件断言（当前全是内联假组件 + 过期 spec）

### 3.4 可观测性
- [ ] Alertmanager 配置真实 receiver（企业微信/邮件/Slack），告别空壳 `log-output`
- [x] `/api/exchange/test-connection` 加管理员鉴权（`/api/metrics`、`/api/health/deep` 留给 Prometheus 内网抓取）
- [x] Redis 日志脱敏（只打印 host，不泄漏含密码 URL）

---

## 4. 优先级矩阵

| 序号 | 任务 | 阶段 | 优先级 | 工时估 |
|---|---|---|---|---|
| 1.1 | 硬上限/白名单/风控接回 | 二 | 🔴 P1 | 3h |
| 1.2 | 幂等 + clientOrderId | 二 | 🔴 P1 | 3h |
| 1.3 | 自动策略走审计落库 | 二 | 🔴 P1 | 4h |
| 1.4 | 风控五维生效 | 二 | 🔴 P1 | 3h |
| 1.6 | RBAC + 关开放注册 | 二 | 🔴 P1 | 3h |
| 2.1 | 统计检验校正 | 三 | 🔴 P1 | 8h |
| 2.2 | 消除前视偏差 | 三 | 🔴 P1 | 2h |
| 2.3 | AI 闭环闭合 | 三 | 🟠 P1 | 6h |
| 3.1 | CI 真正有效 | 四 | 🟠 P1 | 1h |
| 3.2 | 跨平台 + HTTPS | 四 | 🟠 P1 | 4h |
| 1.5 | 账户路由/锁/对账 | 二 | 🟡 P2 | 6h |
| 2.4 | 在线学习接线 | 三 | 🟡 P2 | 4h |
| 3.3 | 前端契约 | 四 | 🟡 P2 | 6h |
| 3.4 | 可观测性 | 四 | 🟢 P3 | 3h |

---

## 5. 上实盘前的硬性验收（P0/P1 全绿才可切换）

- [ ] `docker compose up -d` 后 `/api/health` 返回 200（当前 500）
- [ ] 触发止损 → 观察日志与持仓，确认**真实平仓**（当前崩溃）
- [ ] 触发紧急停止 → 挂单数归 0、持仓归 0（当前撤单恒 0）
- [ ] 手动下单被白名单 + 硬上限拦截（当前全放行）
- [ ] 重复请求不产生重复下单（当前幂等空转）
- [ ] 未授权用户无法注册/交易/解除紧急停止（当前开放注册无 RBAC）
- [ ] 回测/AI 迭代的 `scientific_passed` 结论可复现（当前 PBO/SPA 退化）

---

## 6. 明确不做（理由）

| 不做 | 理由 |
|---|---|
| 同时支持现货 + 合约双模式 | 语义双轨是本次所有 bug 的根源，先只做合约 |
| AI 直接实盘交易 | 执行必须落到程序，AI 只出建议 |
| 随机森林/神经网络策略池 | 过拟合风险高、数据量不足 |
| Rust 重写 | Python 现阶段够用，稳定后再考虑 |

---

_新建于 2026-07-21，替代旧 MILESTONES.md 作为 v2.0 合约版路线图。_
