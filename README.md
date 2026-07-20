# AI 量化交易系统

> 基于 AI 策略生成 + 回测验证 + 实盘交易的量化交易系统，对接 OKX 交易所，支持模拟盘/实盘热切换。

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-14.2-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

## 项目简介

AI 量化交易系统是面向大资金长期无人值守实盘场景的生产级量化交易平台，核心能力包括：

- **AI 策略生成**：基于 LLM 自动生成交易策略，迭代优化
- **批量回测**：异步回测引擎，支持样本内外分割 + PBO 过拟合检验
- **在线学习**：动态权重分配，策略池自进化
- **实盘交易**：OKX 交易所对接，模拟盘/实盘热切换
- **四层风控**：kill_switch → 金额硬上限 → 白名单 → risk_engine
- **多实例容错**：DB 乐观锁 + 订单补偿链 + 崩溃恢复
- **实时行情**：WebSocket 推送 + tick_cache 合并请求

## 技术栈

### 后端
- **Python 3.13** + FastAPI 0.115 + Uvicorn（4 workers）
- **PostgreSQL 16** + asyncpg（异步驱动）
- **Redis 7**（缓存层，可选）
- **ccxt**（OKX 交易所统一接口）
- **APScheduler**（5 类定时任务）
- **Fernet AES-256-GCM**（密钥加密）

### 前端
- **Next.js 14.2** + React 18.3 + TypeScript
- **Tailwind CSS** + Lucide Icons + Recharts
- **SWR**（数据获取）+ Zustand（状态管理）
- **WebSocket**（实时行情）

### 基础设施
- **Docker Compose**（5 服务编排）
- **Nginx**（反向代理 + gzip + 静态缓存）
- **PostgreSQL Volume**（数据持久化）

## 架构图

```
Internet
    │
  Nginx :80
    ├─ /api/*   →  backend:8000 (uvicorn --workers 4)
    │                │
    │                ├─ PostgreSQL :5432 (持久化)
    │                ├─ Redis :6379 (缓存)
    │                └─ OKX Exchange (ccxt)
    │
    ├─ /ws/*    →  backend:8000 (WebSocket 实时行情)
    │
    └─ /*       →  frontend:80 (Next.js 静态导出)
                      │
                      └─ Nginx 内置 (提供静态文件)
```

## 快速启动

### 方式一：Docker Compose 一键启动（推荐）

```bash
# 1. 克隆项目
git clone <repo-url>
cd ai_quant_trade

# 2. 创建 .env 配置（参考 .env.example）
cp .env.example .env
# 编辑 .env 填入真实密钥

# 3. 启动全栈
docker compose up -d

# 4. 检查服务状态
docker compose ps
curl http://localhost/api/health
```

启动后访问：
- 前端：http://localhost
- API 文档：http://localhost/api/docs
- 健康检查：http://localhost/api/healthz

### 方式二：本地开发

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 前端
cd frontend
npm install --legacy-peer-deps
npm run dev
```

## 环境变量

所有环境变量定义在 `.env.example`，主要变量：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL 连接串 | `postgresql+asyncpg://root:root@db:5432/ai_quant_trade` |
| `REDIS_URL` | Redis 连接串 | `redis://redis:6379/0` |
| `JWT_SECRET_KEY` | JWT 签名密钥（≥32 字符） | `<CHANGE_ME>` |
| `ENCRYPTION_KEY` | Fernet 加密密钥 | `<CHANGE_ME>` |
| `EXCHANGE_API_KEY` | OKX API Key | `<CHANGE_ME>` |
| `EXCHANGE_API_SECRET` | OKX API Secret | `<CHANGE_ME>` |
| `EXCHANGE_PASSPHRASE` | OKX Passphrase | `<CHANGE_ME>` |
| `EXCHANGE_TESTNET` | 是否使用模拟盘 | `true` |
| `MAX_ORDER_AMOUNT_USDT` | 单笔最大金额 | `200.0` |
| `MAX_TOTAL_POSITION_USDT` | 总持仓上限 | `2000.0` |
| `LIVE_SYMBOL_WHITELIST` | 实盘交易对白名单 | `BTC/USDT,ETH/USDT,SOL/USDT` |
| `DISABLE_AI_IN_LIVE` | 实盘禁用 AI 策略 | `true` |

⚠️ **生产环境必须**：
1. 所有 `<CHANGE_ME>` 替换为真实强随机值
2. DB 密码改为强随机串（非 `root:root`）
3. 启用 HTTPS（443 + Let's Encrypt）

## API 文档

启动后端后访问 FastAPI 自动文档：
- Swagger UI：`/api/docs`
- ReDoc：`/api/redoc`

主要 API 端点：

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/health` | GET | 基础健康检查 |
| `/api/healthz` | GET | 详细健康检查（DB/Redis 探测） |
| `/api/metrics` | GET | 运行指标（kill_switch/订单补偿/策略数） |
| `/api/auth/login` | POST | 用户登录 |
| `/api/strategies` | GET/POST | 策略管理 |
| `/api/strategies/{id}/start` | POST | 启动策略 |
| `/api/strategies/{id}/stop` | POST | 停止策略 |
| `/api/trading/order` | POST | 手动下单 |
| `/api/portfolio` | GET | 持仓概览 |
| `/api/backtest` | POST | 回测执行 |
| `/api/ai-lab/iterate` | POST | AI 策略迭代 |
| `/api/kill-switch` | POST | 紧急停止 |
| `/ws/ticker` | WS | 实时行情推送 |

## 测试

```bash
cd backend
# 使用 managed Python 3.13.12
C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe -m pytest -v
```

测试覆盖：
- **单元测试**：crypto / risk / risk_engine / stop_loss / validation
- **集成测试**：trading_service / runner 端到端
- **AI 模块测试**：ai_engine / ai_heartbeat / ai_iterator / feature_engine
- **实盘保护验证**：live_protection_check / e2e_check

## 项目结构

```
ai_quant_trade/
├── backend/                    # 后端 FastAPI 服务
│   ├── api/                    # API 路由（10 个文件）
│   ├── core/                   # 核心模块（crypto/security/risk/kill_switch）
│   ├── db/                     # 数据模型（13 张表）
│   ├── services/               # 业务逻辑层（17 个服务）
│   ├── strategies/             # 策略引擎（grid/ma_cross/rsi/bollinger/custom）
│   ├── tasks/                  # 定时任务（scheduler）
│   ├── tests/                  # 测试套件（21 个文件）
│   ├── alembic/                # 数据库迁移
│   ├── scripts/                # 运维脚本（备份/恢复）
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── frontend/                   # 前端 Next.js 应用
│   ├── src/
│   │   ├── components/         # 公共组件
│   │   ├── pages/              # 页面（13 个）
│   │   ├── types/              # TypeScript 类型定义
│   │   ├── hooks/              # 自定义 Hooks
│   │   ├── store/              # Zustand 状态管理
│   │   └── lib/                # 工具库（api/swr）
│   ├── Dockerfile
│   └── next.config.js
├── nginx/                      # Nginx 配置
│   └── nginx.conf
├── docker-compose.yml          # 开发编排
├── docker-compose.prod.yml     # 生产覆盖配置
├── docker-compose.override.yml # 本地端口覆盖（gitignore）
├── .env.example                # 环境变量模板
└── 生产级升级里程碑.md          # 里程碑文档
```

## 部署

### 生产部署

```bash
# 使用生产覆盖配置
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

生产配置特点：
- 资源限制（backend 2 核 2G、db 1 核 1G）
- `restart: always`
- 日志轮转（10MB × 3 文件）
- 健康检查全覆盖

### 数据库备份

```bash
# 手动备份
docker exec ai_quant_backend bash /app/scripts/backup_db.sh

# 恢复
docker exec ai_quant_backend bash /app/scripts/restore_db.sh /app/backups/ai_quant_trade_YYYYMMDD_HHMMSS.sql.gz
```

建议配置 crontab 每日备份：
```bash
0 3 * * * docker exec ai_quant_backend bash /app/scripts/backup_db.sh
```

## 安全

- **密钥加密**：Fernet AES-256-GCM 加密交易所 Secret
- **JWT 强校验**：弱密钥黑名单 + ≥32 字符 + 生产模式拒绝启动
- **CORS 白名单**：仅允许配置的域名
- **令牌桶限流**：login 10/min、trading 30/min
- **审计日志**：所有交易操作落 audit_logs 表
- **.dockerignore**：防止 .env 泄露进镜像

## 文档

- [生产级升级里程碑](生产级升级里程碑.md) — 项目演进路线图
- [项目全面评价报告](ai_quant_trade/项目全面评价报告_2026-07-20.md) — 7.2/10 评估
- [API 文档](http://localhost/api/docs) — FastAPI Swagger UI

## License

Private — 仅供内部使用
