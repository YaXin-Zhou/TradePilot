# Changelog

本项目所有重要变更记录。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## [Unreleased] — Production v1.1（优化版里程碑 N1-N6）

### Added
- **N2**: 项目 `README.md`（项目入口、快速启动、架构图、环境变量说明）
- **N2**: `CHANGELOG.md`（本文件）
- **N2**: 优化版里程碑 `生产级升级里程碑.md` v2（替换原 M1-M6 文档）
- **N3**: `backend/scripts/backup_db.sh` 数据库备份脚本
- **N3**: `backend/scripts/restore_db.sh` 数据库恢复脚本
- **N4**: Alembic 数据库迁移框架引入
- **N5**: `/api/metrics` 运行指标端点
- **N5**: `/api/healthz` 详细健康检查
- **N6**: `frontend/src/types/` 类型定义目录

### Changed
- **N3**: `.env.example` 所有敏感值改为 `<CHANGE_ME>` 占位符
- **N3**: 启动时检测密钥占位符并 log.warning

---

## [1.0.0] — 2026-07-19 — Production v1.0（生产级升级 + P0/P1 修复）

### Added — M1-M6 生产级升级

#### M1 · 数据库扩表（commit 61b866f）
- 新增 `AuditLog` 表（审计日志）
- 新增 `ExchangeCredential` 表（多账户密钥加密存储）
- 新增 `RunnerState` 表（策略状态 DB 持久化 + 乐观锁）
- `Order.account_id` 字段，支持多账户

#### M2 · 核心基础设施（commit ea649dc）
- 新增 `core/tick_cache.py`（TTL 0.5s 行情缓存，消除重复 REST 调用）
- 新增 `core/exchange_registry.py`（多租户交易所实例池）
- `trading_service._get_price()` 改为 async + 调 tick_cache

#### M3 · 交易服务强一致性（commit e513dcf）
- 下单后写 `orders` 表 + `audit_logs` 表（双写原子事务）
- 幂等键防止网络抖动重复下单
- `place_market_order()` 新增 `account_id` 参数

#### M4 · Runner 生产加固（commit 8f77e13）
- `runner_state.json` 迁入 `RunnerState` 表（DB 行级锁）
- 多实例锁：`INSTANCE_ID = hostname:pid`
- 单 tick 内 `fetch_ticker` 调用 ≤ 1

#### M5 · 生产部署（commit af06a3c）
- Docker Compose 5 服务编排（db/redis/backend/frontend/nginx）
- Nginx 反向代理（/api/ + /ws/ + /）
- `docker-compose.prod.yml` 生产覆盖（资源限制 + restart always）
- Python 3.13 统一
- `.env.example` 环境变量模板

#### M6 · 前端类型安全（commit a2e4b00）
- `tsconfig.json` 启用 `strict: true`
- `BacktestParams` 接口定义

### Fixed — P0 缺口修复（3 项）

#### P0-2 · PostgreSQL 枚举补值（commit c72409e）
- `init_db` 自动 `ALTER TYPE ADD VALUE`（MA_CROSS/RSI/BOLLINGER/AI_GENERATED）
- AUTOCOMMIT 模式 + `IF NOT EXISTS` 幂等

#### P0-3 · JWT 安全校验绕过修复（commit 7e1767d）
- `validate_security` 改为弱密钥黑名单 + 长度≥32 + 模式匹配
- `.env.example` 移除弱密钥

#### P0-1 · kill_switch + risk_engine 迁入 DB（commit e93d741）
- 新增 `KillSwitchStateRecord` + `RiskPolicyRecord` 表
- 内存为读源 + fire-and-forget 异步 DB 写
- 调度器每 5 秒 `refresh_from_db` 多 worker 同步
- JSON 文件自动迁移到 `.migrated`

### Fixed — P1 缺口修复（5 项）

#### P1-2 · DB 写入失败补偿链路（commit 3a297fd）
- `trading_service` 重试 + 补偿审计（result=db_persist_failed）+ 内存队列
- 调度器每 30s `flush_pending_order_records` 补偿
- 超 5 分钟过期告警
- `runner._persist_fail_count ≥ 3` 发 WARNING

#### P1-1 · 消除 Mock 回退（commit 734e911）
- `portfolio_service` 完全重写
- 故障返回 `success=False` + 错误信息
- 删除 `_mock_trades()` 和 `import random`

#### P1-4 · 统一策略类型（commit 734e911）
- `start_strategy` 改调 `_build_strategy_obj`
- 后者新增 CUSTOM/ML_SIGNAL/AI_GENERATED 回退 CustomStrategy

#### P1-5 · 解密日志（commit 734e911）
- `crypto.decrypt` 失败 `log.error` 记录密文前缀 + 错误

#### P1-3 · JSON 持久化迁入 DB（commit 2160405）
- `online_learner` / `strategy_pool` / `ai_iterator` 复用 P0-1 模式
- 新增 `OnlineLearnerStateRecord` / `StrategyPoolRecord` / `IterationTaskRecord` 三表

### Changed
- 清理已迁移的 JSON 文件（commit 8dac733）

---

## [0.8.0] — 2026-07-15 — Phase 8 实盘就绪

### Added
- Phase 8 实盘就绪：四层保护 + 紧急停止 + 稳定性与性能优化（commit 5743fc4）
- 双套 API Key 配置（模拟盘 + 实盘独立存储）（commit 10e42b3）
- 设置页新增 DeepSeek API Key 配置（commit 476e6f3）

### Fixed
- 修复未登录时页面无限闪烁（SWR 401 循环）（commit 3583cd8）
- 修复 CORS 预检被拒导致前端 Failed to fetch（commit e2ef3d2）
- 修复 login.tsx 硬编码端口（commit 5572ad9）
- 补全 analysis indicators/predict 端点（commit aa6c150）
- 修复脱敏值回显导致误以为 Key 丢失 + save 留空保留原值（commit 6b2207c）
- test 端点空值/脱敏值时从 DB 读原值（commit 61c658c）

---

## [0.7.0] — 2026-07-10 — Phase 7 集成断层修复 + 工程加固

### Added
- Phase 7 集成断层修复 + 工程加固（commit 91af5e0）
  - 统一 StrategyType 枚举
  - 修复 trading_service / runner 集成断层
  - 添加集成测试
  - CI/CD + Lint 配置
  - 质量修复（JWT/Mock/异常吞噬/临时文件）

---

## [0.6.0] — 2026-07-05 — Phase 6 强化辅助模块

### Added
- 弱信号矩阵 + FeatureEngine 扩展
- 新闻情绪分析（Pulse）
- AI 心跳自迭代定时任务
- 前端 UX 优化（Toast + Notification + Responsive）（commit 11c39f2）

---

## [0.5.0] — 2026-06-28 — Phase 5 策略池管理

### Added
- StrategyPool 策略池基础架构
- OnlineLearner 在线学习权重分配
- PortfolioAllocator 资金分配执行（commit 63a2e78）

---

## [0.4.0] — 2026-06-20 — Phase 4 智能风控系统

### Added
- RegimeDetector 市场状态识别
- RiskEngine 风控规则引擎
- StopLoss 止损升级（commit 9da14dc）

---

## [0.3.0] — 2026-06-10 — Phase 3 AI 策略自动生成

### Added
- StrategyGenerator AI 策略生成引擎
- BatchBacktester 异步批量回测引擎
- Iteration Loop 生成→回测→检验→排序→反馈闭环
- API endpoint + DB models
- 前端 AI 实验室页面（commit ccfbe9e）

---

## [0.2.0] — 2026-05-25 — Phase 1+2 工程地基 + 回测验证

### Added
- 日志系统（logging + RotatingFileHandler）
- 全局错误中间件
- Service 层重构
- 核心链路单元测试
- 前端状态管理 + 数据层
- 样本内外分割 + PBO 过拟合概率
- BH 动态门槛 + DSR 通胀夏普
- Newey-West 修正 + SPA 检验
- 三道门槛管线（commit 17bebc4）

---

## [0.1.0] — 2026-05-10 — 项目初始化

### Added
- 项目骨架搭建
- 基础交易功能（OKX 对接）
- 前端基础页面
