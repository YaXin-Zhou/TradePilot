# TradePilot V6 — 收敛期（Convergence Phase）

> **定位**：停止堆功能，收敛到「能安全、有人值守地跑实盘」。
> **原则**：执行层做减法+加固，砍过拟合复杂度，告警做加法（出事主动推送到人）。
> **来源**：V5 之后的战略复盘结论。

---

## 一、执行层加固（最优先：不亏在 bug 上）

### 1.1 对账脚本修正 + 接入调度器
- [x] `services/reconcile_service.py` 改为合约真源 `RunnerState`（runner 内存持仓 + Strategy.symbol 映射），按名义价值(USDT)对比，规避「张数 vs 币数量」单位差
- [x] 接入 scheduler（每 5 分钟），差异自动告警（`reconcile_and_alert`）
- [x] `scripts/reconcile.py` 改为 CLI 薄封装

### 1.2 启动时持仓对账
- [x] 启动时先 `_load_persistent_state` → `reconcile_and_alert()` 检测「本地 vs 交易所」持仓差异并告警，再恢复策略（避免基于陈旧持仓开跑）
- [x] 采用「检测 + 告警」而非静默自动纠正（自动纠正持仓是亏损重灾区，有人值守手动处理更安全）

### 1.3 runner 下单/平仓补幂等键 + 幽灵单反查
- [x] 新增 `_place_with_client_id`：下单/平仓统一携带 clientOrderId，失败时按 clientOrderId 反查交易所，订单实际存在则视同成功（防幽灵单重复下单）
- [x] `_tick` 开仓 + `_close_position` 平仓均接入

## 二、告警（有人值守的前提）

### 2.1 告警通道配置化 + 通用 Webhook
- [x] `config.py` 的 TELEGRAM_BOT_TOKEN/CHAT_ID 现为硬编码空串，改为读 `.env`
- [x] 新增 `ALERT_WEBHOOK_URL` 通用 Webhook 通道（Telegram 缺省时可用）

### 2.2 关键事件全量接入告警
- [x] kill switch 触发/解除、日亏熔断、对账差异、心跳掉线、策略 error 全部推送到 alert_service（信号/止损/下单失败已接入 runner）

## 三、砍过拟合（AI 挖因子的反噬）

### 3.1 AI 策略工厂默认「仅草稿 + 人工确认」
- [x] `ai_service.py` 自动入库不再自动注册策略池，仅保存为 DRAFT；新增最少交易笔数门槛（`total_trades>=5`），阻断「1 笔交易 + 假夏普」自动入库
- [x] `api/ai_strategy.py` save-to-warehouse 不再自动入池，返回 draft 标记，需人工经 `/pool/{id}/register` 启用

## 四、最小实盘闭环

### 4.1 端到端 testnet → 实盘检查清单
- [ ] 输出一份「上线前检查清单」文档：对账/告警/风控/kill switch/资金上限逐项确认

## 五、AI 自适应重写（替代「AI 挖因子」）

### 5.1 regime 自适应权重模块
- [ ] 固定小因子池（动量/均值回归/波动率/资金费率/基差/OI），新增 `regime_adapt`：按当前 regime 调策略权重/参数，替代随机变体搜索
- [ ] 默认 fail-closed：样本外不通过时回退到空仓/基准

---

## 优先级

1. **2 告警**（有人值守的前提，改动最小、价值最大）
2. **1.1 + 1.2 对账**（资金安全真源对齐）
3. **1.3 幽灵单**（执行层最后一块）
4. **3.1 砍过拟合**（阻断假夏普入池）
5. **5.1 AI 自适应**（把「挖因子」换成「自适应」）
6. **4.1 上线清单**（收尾文档）

---

_本文档承接 MILESTONES_V5.md，标志从「功能建设」转向「收敛实盘」。_
