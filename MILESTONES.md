# AI Quant Trade — 全面升级里程碑 v2.0

> **基准**：2026-07-19 项目评价报告 + 《量化交易系统技术参考 AI 参照版》  
> **目标**：安全基线达标 → 工程基础补强 → 回测验证升级 → AI 策略自动生成/测试/迭代闭环 → 智能风控 → 策略池管理  
> **工期**：核心 2 周冲刺 + 后续持续迭代

---

## 当前项目定位

**状态：** 原型验证通过，核心链路（行情→AI分析→回测→下单）已跑通。安全/工程/验证三个维度存在明显短板。

**关键数据：**
- AI 分析到自动下单闭环已完成，延迟 175ms
- OKX Testnet + DeepSeek API Key 已配置
- 代码 5570 文件（含 node_modules），后端 ~3000 行 Python，前端 ~2500 行 TSX
- 0 单元测试 | 0 lint 配置 | 3 处 P0 安全隐患

---

## 阶段〇：安全基线（Day 1-2，约 6h）

> **没有这一层，其他都是空中楼阁。必须在做任何新功能前完成。**

### 0.1 密钥加密存储

- [ ] 交易所 Secret / Passphrase 用 `cryptography.fernet` AES 加密后写入 DB
- [ ] 加密密钥从环境变量 `ENCRYPTION_KEY` 读取（启动时若无则自动生成 32 字节随机 key）
- [ ] 敏感字段在日志/错误消息中自动脱敏（`***` 替换）
- [ ] `load_db_config.py` 解密逻辑同步更新

**文件：** `backend/db/models.py`、`backend/core/crypto.py`（新建）、`backend/api/settings.py`、`backend/load_db_config.py`

### 0.2 AI API Key 治理

- [ ] DeepSeek API Key 不再从前端传入，改为后端环境变量 `DEEPSEEK_API_KEY`
- [ ] `POST /api/ai/analyze` 移除 `api_key` 参数，引擎从 settings 读取
- [ ] 前端 AI 分析页面移除 Key 输入框，只留策略描述

**文件：** `backend/strategies/ai_strategy.py`、`backend/api/ai_strategy.py`、`frontend/pages/ai-strategy.tsx`

### 0.3 CORS + 基础设施安全

- [ ] CORS `allow_origins` 从 `["*"]` 改为 `["http://localhost:3000", "http://127.0.0.1:3000"]`
- [ ] 生产环境读取 `ALLOWED_ORIGINS` 环境变量
- [ ] JWT Secret 生成策略：`secrets.token_urlsafe(32)` → 写入 `.env`
- [ ] 注册端点增加密码强度校验（最��� 8 位、含数字+字母）
- [ ] Rate Limiting：`slowapi` 中间件，全局 200 req/min + 敏感端点 10 req/min

**文件：** `backend/main.py`、`backend/config.py`、`backend/auth/router.py`、`backend/core/limits.py`（新建）

---

## 阶段一：工程地基（Day 3-5，约 12h）

> **代码能跑 ≠ 能维护。日志、测试、分层是团队协作的前提。**

### 1.1 日志系统

- [x] Python `logging` + `RotatingFileHandler`，日志写入 `logs/` 目录
- [x] 三个级别：INFO（业务事件：下单/成交/策略切换）、WARNING（重试/降级）、ERROR（异常+堆栈）
- [x] `.gitignore` 排除 `logs/`
- [x] 前端 `console.log` 替换为结构化日志（仅在 dev 模式输出）

**文件：** `backend/core/logger.py`（新建）、各处 `print()` 替换

### 1.2 全局错误中间件

- [x] FastAPI `@app.exception_handler` 统一捕获所有未处理异常
- [x] 返回统一格式 `{success: false, error: "内部错误", trace_id: "xxx"}`（不暴露内部细节）
- [x] 自动脱敏：正则匹配 API Key / Secret 模式并替换为 `***`
- [x] 前端 API 客户端的 `request()` 支持 trace_id 回传

**文件：** `backend/core/errors.py`（新建）、`backend/main.py`、`frontend/lib/api.ts`

### 1.3 Service 层重构

```
backend/
├── api/              # HTTP 层：参数校验、响应格式化（薄层）
├── services/         # 业务层：调用 exchange / db / strategies（核心）
│   ├── market_service.py
│   ├── trading_service.py
│   ├── portfolio_service.py
│   ├── strategy_service.py
│   ├── backtest_service.py
│   └── ai_service.py
├── core/             # 基础设施
│   ├── exchange.py
│   ├── risk.py
│   ├── crypto.py
│   ├── logger.py
│   └── errors.py
└── db/               # 数据层（不变）
```

- [x] 将 `api/market.py` 中的业务逻辑迁入 `services/market_service.py`
- [x] 将 `api/trading.py` 中的下单逻辑迁入 `services/trading_service.py`
- [x] 将 `api/backtest.py` 中的回测逻辑迁入 `services/backtest_service.py`
- [x] 将 `api/ai_strategy.py` 中的 AI 调用逻辑迁入 `services/ai_service.py`
- [x] 各 API 路由文件简化为：参数校验 → 调用 service → 构造响应

**工作量最大的一项，预计 4-6h**

### 1.4 核心链路单元测试

- [x] `tests/test_backtest.py`：验证 MA交叉/RSI/布林带回测逻辑，覆盖多空双边+手续费
- [x] `tests/test_ai_engine.py`：Mock DeepSeek 响应，验证 JSON 解析容错（正常/缺失字段/格式错误）
- [x] `tests/test_risk.py`：验证最大持仓、日亏损、订单数限制的边界条件
- [x] `tests/test_crypto.py`：验证加密/解密/脱敏

**预计覆盖 ~50 个测试用例，文件：** `backend/tests/`（新建）

### 1.5 前端状态管理 + 数据层

- [x] 引入 Zustand（~1KB）管理全局状态：`currentSymbol`、`exchangeStatus`、`userPreferences`
- [x] 引入 SWR 替代各页面的 `useEffect + setInterval` 轮询模式
- [x] WebSocket `useRealtime` 保持在 `_app.tsx` 层级，切换页面不断连
- [x] 前端状态持久化：选中的交易对、策略配置写入 `localStorage`，刷新后恢复
- [x] 骨架屏组件：仪表盘/交易/回测三个页面的加载态

**文件：** `frontend/store/`（新建）、`frontend/pages/_app.tsx`、`frontend/components/Skeleton.tsx`（新建）

---

## 阶段二：回测验证体系升级（Day 6-8，约 14h）

> **参照《技术参考》第一章：五重统计学验证 + 三道门槛。这是从"玩具"到"研究工具"的关键跃迁。**

### 2.1 样本内外分割 (PBO 基础)

- [x] 回测引擎增加 IS/OOS 分割：前 70% K 线为样本内，后 30% 为样本外
- [x] 回测结果增加 `sharpe_is` / `sharpe_oos` / `max_drawdown_is` / `max_drawdown_oos`
- [x] PBO 计算：对样本内数据做 N 次 Bootstrap 重采样，计算每个重采样在样本外的 Sharpe
- [x] PBO > 0.5 时前端显示红色警告

**文件：** `backend/services/validation.py`（新建）、`backend/strategies/backtest.py`

### 2.2 BH + DSR 统计检验

- [x] BH（Benjamini-Hochberg）：给定 N 个策略的 P 值列表，按排序动态调整阈值
- [x] DSR（Deflated Sharpe Ratio）：`DSR = Sharpe × sqrt(1 - 1/N)`，N 为尝试策略总数
- [x] 回测历史记录增加 `total_attempts` 计数器，每次回测 +1
- [x] 回测结果面板展示 BH 筛选结果 + DSR 值

**文件：** `backend/services/validation.py`

### 2.3 Newey-West + SPA

- [x] Newey-West 修正：对资金曲线计算异方差自相关稳健的标准误
- [x] 滞后阶数默认 `⌊T^(1/3)⌋`（T 为样本量）
- [x] SPA 检验：Bootstrap 重采样 1000 次，计算策略相对基准的 p-value
- [x] 以上结果均在回测结果面板中可视化展示

**文件：** `backend/services/validation.py`

### 2.4 三道门槛管线

- [x] **Replay 门槛**：基础回放验证 → 确认策略逻辑可复现（现有回测升级版）
- [x] **Scientific 门槛**：运行全部五重检验 → 任一不通过则标记为 "SCIENTIFIC_FAIL"
- [x] **Production 门槛**：在模拟盘连续运行 24H → 检查夏普衰减 < 30%、最大回撤 < 40%
- [x] 策略状态增加 `validation_stage`（replay / scientific / production / passed）
- [x] 前端策略卡片显示当前验证阶段 + 进度条

**文件：** `backend/services/validation_pipeline.py`（新建）、`backend/db/models.py`（Strategy 增加字段）、前端策略页面

---

## 阶段三：AI 策略自动生成 → 测试 → 迭代引擎（Day 9-11，约 15h）

> **这是本次升级的核心创新点。让 AI 不再是"你问它答"，而是"你设目标，它自己试"。**

### 3.1 架构设计

```
用户设定目标
    │
    ▼
┌─────────────────────────────────────┐
│       AI Strategy Iterator          │
│                                     │
│  ① Generate: DeepSeek 生成 N 个     │
│     策略变体（参数空间探索）        │
│          │                          │
│  ② Backtest: 对每个变体执行        │
│     IS/OOS 回测                     │
│          │                          │
│  ③ Validate: 五重统计检验          │
│     + 三道门槛过滤                  │
│          │                          │
│  ④ Rank: 按 Sharpe(IS) × 0.3       │
│     + Sharpe(OOS) × 0.7 排序       │
│          │                          │
│  ⑤ Iterate: Top-K 策略作为下一轮   │
│     prompt 的参考，引导 AI 优化     │
│          │                          │
│  ⑥ Deploy: 通过 Production 门槛    │
│     的策略进入模拟盘               │
└─────────────────────────────────────┘
```

### 3.2 策略生成器 (StrategyGenerator)

- [x] `POST /api/ai/iterate` 端点，接收：
  ```
  {
    "goal": "寻找 BTC/USDT 在震荡市中低风险的网格策略",  // 用户用自然语言描述目标
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "variants": 10,          // 每轮生成多少个变体
    "max_rounds": 5,         // 最多迭代多少轮
    "risk_constraints": {    // 风控约束
      "max_drawdown_pct": 20,
      "min_sharpe": 0.8,
      "max_concentration": 0.3
    }
  }
  ```
- [x] DeepSeek System Prompt 升级为策略生成器模式：
  - 输入：市场数据 + 历史 Top-K 策略表现 + 用户目标 + 风控约束
  - 输出：N 个策略 JSON 数组，每个含 `strategy_type`、`params`、`rationale`
- [x] 支持三种策略类型的参数空间搜索：MA 交叉（快慢周期）、RSI（超买超卖阈值）、布林带（周期+标准差）

**文件：** `backend/services/ai_iterator.py`（新建）、`backend/api/ai_strategy.py`

### 3.3 批量回测引擎 (BatchBacktester)

- [x] 异步批量执行回测：`asyncio.gather` 并发运行 N 个回测任务
- [x] 每个变体独立计算：Sharpe IS/OOS、最大回撤、胜率、盈亏比
- [x] 超时保护：单个回测线程池并发执行
- [x] 进度回调：`POST /api/ai/iterate/status/{task_id}` 返回实时进度

**文件：** `backend/services/ai_iterator.py`

### 3.4 迭代优化循环

- [x] 第 1 轮：AI 根据市场数据 + 用户目标，生成 N 个初始策略
- [x] 回测 → 检验 → 排序 → Top-K（K = N / 5）入选
- [x] 第 2-N 轮：将 Top-K 的表现作为 prompt 上下文，AI 分析"为什么这些胜出"并优化参数
- [x] 收敛条件：连续 2 轮 Top-1 的 Sharpe(OOS) 改进 < 1%
- [x] 每轮结果在 JSON 文件中持久化记录

**DB 新增模型：**
```python
class IterationTask(Base):
    id / user_id / goal / symbol / total_rounds / current_round / status / created_at
    
class IterationRound(Base):
    id / task_id / round_number / variants_count / top_sharpe_is / top_sharpe_oos / ai_analysis / completed_at
    
class StrategyVariant(Base):
    id / round_id / strategy_type / params_json / sharpe_is / sharpe_oos / pbo / dsr / passed_scientific / passed_production / rank
```

**文件：** `backend/services/ai_iterator.py`、`backend/db/models.py`、`backend/api/ai_strategy.py`

### 3.5 前端 AI 实验室页面

- [x] 新建 `/ai-lab` 页面（替换单一 AI 分析页面的旧模式）
- [x] 三栏布局：
  - 左栏：目标输入 + 约束设置 + 启动按钮
  - 中栏：迭代进度（轮次/变体/排序可视化）
  - 右栏：最优策略卡片（参数/曲线/检验结果/一键部署到模拟盘）
- [x] 历史任务列表 + 详情查看

**文件：** `frontend/pages/ai-lab.tsx`（新建）、`frontend/components/` 相关组件

---

## 阶段四：智能风控系统（Day 11-13，约 10h）

> **参照《技术参考》的 Regime 思路：不同市场状态用不同风控参数。自定义风控规则引擎。**

### 4.1 Regime 市场状态识别

- [ ] `MarketRegimeDetector` 类，基于 50 周期 MA 斜率 + ATR 波动率，输出四种状态：
  - `TRENDING_UP`（强势上涨）→ `TRENDING_DOWN`（强势下跌）→ `RANGING_HIGH_VOL`（高波动震荡）→ `RANGING_LOW_VOL`（低波动震荡）
- [ ] 实时计算并缓存（每 5 分钟刷新），通过 `/api/analysis/market-regime` 暴露
- [ ] 前端状态栏显示当前 Regime + 置信度

**文件：** `backend/services/regime_detector.py`（新建）、`backend/api/analysis.py`

### 4.2 风控规则引擎

- [ ] `RiskPolicy` 数据模型：每个 Regime 绑一套风控参数
  ```python
  {
    "regime": "TRENDING_UP",
    "max_position_pct": 0.4,     # 强势上涨允许 40% 仓位
    "max_daily_loss_pct": 5.0,   # 日亏损上限
    "stop_loss_pct": 8.0,        # 止损线
    "min_sharpe_entry": 0.8,     # 新策略最低入场 Sharpe
    "max_correlation": 0.7,      # 策略间最大相关性
    "trailing_stop_pct": 3.0     # 移动止损
  }
  ```
- [ ] 风控引擎在每次下单/策略启动时检查：
  1. 当前 Regime 是否允许该策略类型（如震荡策略不宜在强势趋势中运行）
  2. 仓位是否超限（总仓位 + 单策略仓位）
  3. 日亏损是否触达（触达则暂停所有策略）
  4. 策略间相关性是否过高（过高则自动降低权重）
- [ ] 前端 `/settings/risk` 页面：可视化编辑每个 Regime 的风控参数，支持导入/导出 JSON

**文件：** `backend/services/risk_engine.py`（新建）、`backend/db/models.py`、`frontend/pages/settings/risk.tsx`（新建）

### 4.3 止损升级

- [ ] 硬止损：价格跌破固定百分比 → 市价平仓
- [ ] 移动止损（Trailing Stop）：追踪最高价，回撤 N% 触发
- [ ] 时间止损：持仓超过 N 小时未盈利 → 平仓
- [ ] 波动率止损：ATR × N 为动态止损距离

- [ ] `grid_trading` 修复止损坏逻辑：止损触发 → 取消所有挂单 → **市价卖出所有持仓** → 停止运行

**文件：** `backend/core/risk.py`（重写）、`backend/services/stop_loss.py`（新建）、`D:\wenjian\xiangm\work\grid_trading\grid_bot.py`

---

## 阶段五：策略池管理（Day 12-14 或进入下一迭代周期，约 10h）

> **参照《技术参考》第四章：当策略数量 >10 时，需要在线学习算法管理权重分配。**

### 5.1 StrategyPool 基础架构

- [ ] `StrategyPool` 类管理所有活跃策略及其权重
- [ ] 每个策略记录：`weight`、`running_sharpe`、`drawdown`、`correlation_matrix`
- [ ] 启停管理：手动暂停 / 自动休眠（连续亏损触发）/ 淘汰（Sharpe 归零）
- [ ] 前端策略池仪表盘：表格 + 饼图 + 相关性热力图

**文件：** `backend/services/strategy_pool.py`（新建）

### 5.2 在线学习权重分配

- [ ] 实现 Adaptive Fixed-Share Hedge 算法：
  1. 损失函数归一化（每个策略的损失映射到 [0,1]）
  2. η 学习率自适应（根据最近 N 个周期表现动态调整）
  3. 族内聚合（同类型策略先加权平均），族间 Hedge（族间用指数加权）
- [ ] Sleeping Experts：当某策略的 Regime 不适配时自动休眠（weight → 0.01），不参与资金分配
- [ ] 每天凌晨自动运行权重重分配

**文件：** `backend/services/online_learner.py`（新建）

### 5.3 资金分配执行

- [ ] `PortfolioAllocator`：根据策略池权重 × 总可用资金，分配每个策略的下单额度
- [ ] 再平衡机制：每小时检查偏差 > 5% 则触发渐进式再平衡（非一次性调仓）
- [ ] 前端组合页升级：显示各策略资金占比 + 贡献度分析

**文件：** `backend/services/portfolio_allocator.py`（新建）

---

## 阶段六：强化辅助模块（后续迭代）

> **P2 优先级，在核心闭环稳定后推进。**

### 6.1 弱信号矩阵

- [x] 引入外部数据源：OKX Open Interest（已有 CCXT 接口）、恐惧贪婪指数
- [x] FeatureEngine 从 23 个指标扩展到 50+ 个弱信号
- [x] 对信号矩阵做 PCA 降维 → 保留解释 95% 方差的主成分
- [x] 用降维后的信号矩阵替代原有 ML 特征输入

**参照：** 《技术参考》第二章
**文件：** `backend/services/feature_engine.py`、`backend/services/external_data.py`

### 6.2 Pulse 新闻情绪

- [x] 接入公开新闻源（CryptoPanic RSS / TradingView 热门）
- [x] 用 DeepSeek 做情感分析：bullish / bearish / neutral
- [x] 情绪分数作为辅助信号输入 Regime 检测器

**参照：** 《技术参考》第五章第 2 节
**文件：** `backend/services/news_sentiment.py`

### 6.3 AI 心跳自迭代

- [x] 定时任务（每 6 小时）触发 AI 审查：
  - 读取当前策略池状态（各策略权重/Sharpe/回撤）
  - 对比上一周期的表现
  - 输出调整建议（降权/休眠/淘汰/新策略方向）
- [x] 调整建议经人工审核后执行（非自动执行）

**参照：** 《技术参考》第五章第 3 节，"AI 不能直接实盘交易"
**文件：** `backend/tasks/ai_heartbeat.py`

### 6.4 前端体验提升

- [x] 错误 Toast 分类：网络错误（黄色）/ 交易所错误（橙色）/ 风控拦截（红色）
- [x] 全局通知中心：策略异常、止损触发、迭代完成等事件汇总
- [x] 移动端适配的响应式布局

**文件：** `frontend/components/NotificationCenter.tsx`、`frontend/store/useNotificationStore.ts`、`frontend/lib/toast.ts`

---

## 综合优先级矩阵

| 序号 | 任务 | 阶段 | 工时 | 优先级 | 依赖 |
|------|------|------|------|--------|------|
| 0.1 | 密钥加密存储 | 阶段〇 | 2h | 🔴 P0 | 无 |
| 0.2 | AI Key 治理 | 阶段〇 | 1h | 🔴 P0 | 无 |
| 0.3 | CORS+基础设施安全 | 阶段〇 | 3h | 🔴 P0 | 无 |
| 1.1 | 日志系统 | 阶段一 | 2h | 🟡 P1 | 无 |
| 1.2 | 全局错误中间件 | 阶段一 | 2h | 🟡 P1 | 1.1 |
| 1.3 | Service 层重构 | 阶段一 | 5h | 🟡 P1 | 1.2 |
| 1.4 | 核心链路测试 | 阶段一 | 4h | 🟡 P1 | 1.3 |
| 1.5 | 前端状态+数据层 | 阶段一 | 4h | 🟡 P1 | 无 |
| 2.1 | PBO 样本内外分割 | 阶段二 | 4h | 🟡 P1 | 1.3 |
| 2.2 | BH + DSR | 阶段二 | 4h | 🟡 P1 | 2.1 |
| 2.3 | Newey-West + SPA | 阶段二 | 3h | 🟡 P1 | 2.1 |
| 2.4 | 三道门槛管线 | 阶段二 | 3h | 🟡 P1 | 2.1-2.3 |
| 3.1 | 策略生成器 | 阶段三 | 5h | 🟡 P1 | 1.3 |
| 3.2 | 批量回测 | 阶段三 | 3h | 🟡 P1 | 2.1 |
| 3.3 | 迭代优化循环 | 阶段三 | 4h | 🟡 P1 | 3.1+3.2 |
| 3.4 | AI 实验室前端 | 阶段三 | 3h | 🟡 P1 | 3.1-3.3 |
| 4.1 | Regime 状态识别 | 阶段四 | 3h | 🟡 P1 | 1.3 |
| 4.2 | 风控规则引擎 | 阶段四 | 4h | 🟡 P1 | 4.1 |
| 4.3 | 止损升级 | 阶段四 | 3h | 🟡 P1 | 4.2 |
| 5.1 | 策略池基础 | 阶段五 | 3h | 🟢 P2 | 4.1 |
| 5.2 | 在线学习权重 | 阶段五 | 4h | 🟢 P2 | 5.1 |
| 5.3 | 资金分配执行 | 阶段五 | 3h | 🟢 P2 | 5.2 |
| 6.1 | 弱信号矩阵 | 阶段六 | 4h | 🟢 P2 | ✅ |
| 6.2 | 新闻情绪分析 | 阶段六 | 3h | 🟢 P2 | ✅ |
| 6.3 | AI 心跳自迭代 | 阶段六 | 3h | 🟢 P2 | ✅ |
| 6.4 | 前端体验提升 | 阶段六 | 3h | 🟢 P2 | ✅ |

### 工时汇总

| 阶段 | 内容 | 工时 |
|------|------|------|
| 阶段〇 | 安全基线 | ~6h |
| 阶段一 | 工程地基 | ~17h |
| 阶段二 | 回测验证升级 | ~14h |
| 阶段三 | AI 策略迭代引擎 | ~15h |
| 阶段四 | 智能风控 | ~10h |
| **两周核心合计** | | **~62h**（平均 4.4h/天 × 14 天） |
| 阶段五 | 策略池管理 | ~10h |
| 阶段六 | 辅助模块 | 持续 |

---

## 技术参考可落地点速查

从《量化交易系统技术参考 AI 参照版》中提取、已映射到上述计划：

| 参考技术 | 落地点 | 里程碑位置 |
|----------|--------|------------|
| BH 动态门槛 | `validation.py` — 数组排序后动态调整 α | 阶段二 2.2 |
| DSR 通胀夏普 | `validation.py` — Sharpe × √(1-1/N) | 阶段二 2.2 |
| PBO 过拟合概率 | `validation.py` — IS/OOS Bootstrap | 阶段二 2.1 |
| Newey-West 修正 | `validation.py` — 异方差自相关稳健 SE | 阶段二 2.3 |
| SPA 超越预测能力 | `validation.py` — Bootstrap 重采样 | 阶段二 2.3 |
| 三道门槛 | `validation_pipeline.py` — Replay→Scientific→Production | 阶段二 2.4 |
| Regime 市场状态 | `regime_detector.py` — MA斜率+ATR波动率 | 阶段四 4.1 |
| 自适应风控 | `risk_engine.py` — Regime绑风控参数 | 阶段四 4.2 |
| AI 自迭代 | `ai_iterator.py` — 生成→回测→排序→反馈 | 阶段三 3.1-3.3 |
| Online Expert (AFH) | `online_learner.py` — 族内聚合+族间Hedge | 阶段五 5.2 |
| Sleeping Experts | `online_learner.py` — Regime不适配自动休眠 | 阶段五 5.2 |
| 移动止损 | `stop_loss.py` — Trailing Stop + ATR止损 | 阶段四 4.3 |
| 弱信号矩阵 | `feature_engine.py` — 54维特征 + PCA降维(95%方差) | 阶段六 6.1 |
| 新闻情绪分析 | `news_sentiment.py` — CryptoPanic + DeepSeek情感分类 | 阶段六 6.2 |
| AI心跳审查 | `ai_heartbeat.py` — 6h定时审查+规则/DeepSeek双模式 | 阶段六 6.3 |
| Toast分类通知 | `NotificationCenter.tsx` — 网络/交易所/风控三级分类 | 阶段六 6.4 |

### 明确不做的（理由充分）

| 不做的 | 理由 |
|--------|------|
| AI 直接实盘交易 | 《技术参考》明确警告：不可信任，必须落到程序 |
| 随机森林/神经网络策略池 | 过拟合风险高/数据量不足 |
| Rust 重写 | 现阶段 Python 够用，Rust 是系统稳定后的事 |
| ~~弱信号矩阵（OI/链上）~~ | ✅ Phase 6 已实现 |
| ~~Pulse 新闻情绪~~ | ✅ Phase 6 已实现 |

---

## 每日推进日历（两周冲刺）

### 第一周：安全 + 地基 + 验证
| 日 | 任务 | 产出 |
|----|------|------|
| Mon | 0.1 密钥加密 + 0.2 AI Key 治理 | `crypto.py`、安全基线达标 |
| Tue | 0.3 CORS+RateLimit + 1.1 日志 | 后端安全达标、日志就绪 |
| Wed | 1.2 错误中间件 + 启动 1.3 Service 层 | `errors.py`、Service 层施工中 |
| Thu | 1.3 Service 层完成 + 1.4 开始测试 | Service 层收工、3 个测试文件 |
| Fri | 1.4 测试完成 + 1.5 前端改造 | 50 测试用例、Zustand+SWR 就绪 |
| Sat | 2.1 PBO + 2.2 BH/DSR | 样本内外分割、两项检验可用 |
| Sun | 2.3 Newey-West+SPA + 2.4 三道门槛 | 五重检验完整、管线就绪 |

### 第二周：AI 迭代 + 风控
| 日 | 任务 | 产出 |
|----|------|------|
| Mon | 3.1 策略生成器 + 3.2 批量回测 | AI 生成 10 个策略并回测 |
| Tue | 3.3 迭代优化循环 | 自动迭代闭环跑通 |
| Wed | 3.4 AI 实验室前端 | 新页面可交互 |
| Thu | 4.1 Regime + 4.2 风控引擎 | 四状态识别 + Regime 绑定风控 |
| Fri | 4.3 止损升级 + grid_trading 修复 | 多种止损模式、网格止损修复 |
| Sat | 集成测试 + 端到端 + Bug 修复 | 全链路验证 |
| Sun | 文档 + 清理 + 部署检查 | 交付就绪 |

---

> **核心原则（来自《技术参考》的实战教训）：**
> 1. "宁缺毋滥" — 即使数亿组合无一通过生产级验证，也不降标准
> 2. "AI 不能直接实盘交易" — 最终执行必须落到程序
> 3. "先做 Demo 测试" — 模拟盘目的是验证稳定性，非追求收益
> 4. "置信度只给 0.5" — 即使通过所有检验也要保持谨慎
> 5. "让时间成为朋友" — 量化系统的打磨是长期工程，非短期可成

---

_新建于 2026-07-19，替代旧版 MILESTONES.md_
