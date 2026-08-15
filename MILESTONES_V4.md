# TradePilot V4 — 稳定实盘 + 快速前端

> **目标**：从「模拟盘可用」推进到「稳定跑实盘」，并让前端快速响应、体验统一为终端极客风。
> **来源**：第二次全面评估（7.0/10）+ 新需求（稳定实盘 + 快速响应前端）。
> **状态**：模拟盘合约交易已跑通（337 测试全绿），本里程碑聚焦「生产就绪」与「体验升级」。

---

## 一、实盘稳定性（P0/P1，上实盘硬门槛）

### A. 阻塞性修复（本地开发就有影响）
- [x] **`strategy_log` 表 SQLite 兼容**：方言自适应（SQLite 用 `INTEGER/TEXT/DATETIME`，PG 保留 `BIGSERIAL/JSONB/TIMESTAMPTZ`）
- [x] **Alembic Windows GBK 编码**：`.ini`/迁移脚本转纯 ASCII（去除非 ASCII 破折号与 BOM）

### B. 上实盘前必须
- [x] **恢复鉴权**：`AUTH_DISABLED` 环境开关（本地 true=免登录，生产 false=JWT+RBAC）
- [x] **CSCV PBO 接进 AI 迭代层**：`_compute_round_pbo` 用多 variant equity_curve 构建收益矩阵算 CSCV PBO
- [ ] **真实多实例验证**：需 4 worker + PostgreSQL 环境（部署时做）
- [ ] **订单补偿链端到端演练**：需真实交易所/DB 故障注入环境（部署时做）

### C. 生产部署（需域名/服务器/凭据）
- [ ] Docker 编排实测（db/redis/backend×4/frontend/nginx 全链路健康）
- [ ] HTTPS（nginx 443 + Let's Encrypt + HSTS）
- [ ] Prometheus/Grafana/Alertmanager 接真实 receiver（告警端到端演练）
- [ ] Redis requirepass + DB/Grafana 强密码
- [ ] 实盘 API Key 轮换 + 最小权限（仅交易、禁提币）

---

## 二、快速响应前端（P1/P2）

### D. 性能
- [ ] SWR 复用与缓存策略统一（减少重复轮询；行情走 WS 推送而非轮询）
- [ ] 图表组件按需加载（Recharts 动态 import，降低首屏体积）
- [ ] 列表/表格虚拟化或分页（持仓/订单/历史数据量大时不卡）
- [ ] 前端构建产物 code-split（Next.js 动态 import 大页面）

### E. 体验统一（终端极客风，参考 `风格.md`）
- [ ] 全局等宽字体（数据/价格/表格对齐），长正文保持易读
- [ ] `$` 提示符 + 状态符号（连接状态/模式标识）
- [ ] ASCII 分隔线组织分区（──┤标题├──）
- [ ] 闪烁光标仅作轻量运行提示，支持 `prefers-reduced-motion`
- [ ] 克制色板：暗底 + 绿(涨/正常) + 红(跌/危险) + 黄(警告)，状态不只靠颜色（加文字/图标）

### F. 响应式与交互
- [ ] 移动端表格横向滚动 + 关键信息卡片化
- [ ] 交易下单区移动端优先（大按钮、防误触二次确认）
- [ ] 错误/加载态统一（skeleton + toast + 空态）

---

## 三、优先级排序

1. **A1 strategy_log SQLite 兼容**（本地唯一还在报错的实质 bug，一行级改动）
2. **B1 恢复鉴权开关**（生产安全底线，本地免登录、生产强鉴权二选一）
3. **E 终端极客风前端**（本次要做的体验升级，纯前端）
4. **D 性能优化**（SWR/代码分割/虚拟化）
5. **B2 CSCV PBO 接入**（统计层收尾）
6. **B3/B4 多实例 + 补偿链演练**（上实盘前的安全演练）
7. **C 生产部署**（需域名/服务器/凭据，最后做）

---

## 四、明确不做

| 项 | 理由 |
|---|---|
| 高频做市/套利 | 非核心诉求（个人小资金值守，聚焦中低频策略） |
| 前端重写为 App Router | 成本高、风险大，Pages Router 够用 |
| 引入重型 UI 框架（shadcn/MUI） | 现有 Tailwind + 自研组件够用，避免依赖膨胀 |

---

_本文档承接 MILESTONES_V3.md，聚焦「生产就绪」与「前端体验」两个维度。_
