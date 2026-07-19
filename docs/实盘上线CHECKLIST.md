# 实盘上线 Checklist

> AI 量化交易系统 — 从模拟盘到实盘的安全上线指南
>
> 版本：v0.2.0 | 更新：2026-07-19
>
> ⚠️ **实盘有真金白银风险。本文档每一项都必须 100% 通过才能切实盘。**

---

## 一、核心原则

1. **默认拒绝**：风控引擎异常时宁可错杀不可放过
2. **四层保护**：kill_switch → 金额硬上限 → 交易对白名单 → 风控引擎
3. **最小权限**：API Key 只开"交易"权限，禁止"提币"
4. **保守起步**：单笔 ≤ 200 USDT，总持仓 ≤ 2000 USDT
5. **可观测性**：每个动作必须可追溯、可回滚

---

## 二、上线前自检（必须全部 ✅）

### 2.1 代码与测试

- [ ] `git status` 干净，无未提交改动
- [ ] 后端测试全绿：`cd backend && python -m pytest tests/ -q`
  - 期望：`275 passed`
- [ ] 端到端验证通过：`python tests/e2e_check.py`
  - 期望：`ALL E2E TESTS PASSED`
- [ ] 实盘保护验证通过：`python tests/live_protection_check.py`
  - 期望：`ALL LIVE-MODE PROTECTION TESTS PASSED`
- [ ] 前端构建无错：`cd frontend && npm run build`
- [ ] 前端类型检查：`cd frontend && npx tsc --noEmit`

### 2.2 API Key 安全（最重要！）

- [ ] 在 OKX 创建**专用** API Key（不要复用个人交易 Key）
- [ ] 权限设置：
  - [ ] ✅ 读取（Read）
  - [ ] ✅ 交易（Trade）
  - [ ] ❌ 提币（Withdraw）— **绝对禁止**
  - [ ] ❌ 充币（Deposit）— 不需要
- [ ] IP 白名单：绑定服务器 IP（若 IP 不固定，先不放行任何 IP，每次部署后再加）
- [ ] 绑定设备/二次验证已开启
- [ ] **Key 三件套（api_key / secret / passphrase）已妥善保管**，不在 git/日志/聊天记录中

### 2.3 配置文件 `.env`

- [ ] 复制 `.env.example` → `.env`，填入真实值
- [ ] `EXCHANGE_TESTNET=false`（切实盘）
- [ ] `EXCHANGE_API_KEY` / `EXCHANGE_SECRET` / `EXCHANGE_PASSPHRASE` 填入实盘 Key
- [ ] `ENCRYPTION_KEY` 已设置（不是空）：
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- [ ] `JWT_SECRET_KEY` 已替换为随机 32+ 字符串：
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- [ ] `DEBUG=false`（生产模式，强制安全检查）
- [ ] `DATABASE_URL` 指向 PostgreSQL（生产推荐），不是 SQLite
- [ ] `CORS_ORIGINS` 只列前端实际域名，不要用 `*`
- [ ] `HTTPS_PROXY` / `HTTP_PROXY` 配置正确（连 OKX 需要）
- [ ] 风控参数确认：
  - [ ] `MAX_ORDER_AMOUNT_USDT=200.0`
  - [ ] `MAX_TOTAL_POSITION_USDT=2000.0`
  - [ ] `MAX_DAILY_LOSS_PCT=5.0`
- [ ] `LIVE_SYMBOL_WHITELIST=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT`
- [ ] `DISABLE_AI_IN_LIVE=true`

### 2.4 数据库

- [ ] PostgreSQL 已部署且可访问
- [ ] `psql -h <host> -U <user> -d <db> -c "SELECT 1"` 成功
- [ ] 表结构已初始化：`python -m db.init_db`（首次）
- [ ] 备份策略已配置（`backend/scripts/backup.sh` 定时任务）
- [ ] 连接池参数：`pool_pre_ping=true`、`pool_recycle=3600`（已在 `db/database.py` 中）

### 2.5 服务器与网络

- [ ] 服务器时间已同步（NTP）：`timedatectl status`（Linux）
- [ ] 防火墙只放行 80/443，后端端口（8000）不对外
- [ ] 代理（7890 或其他）稳定可达 OKX
- [ ] 服务器内存 ≥ 2GB，磁盘 ≥ 20GB
- [ ] systemd 服务文件已安装：
  - [ ] `deploy/ai-quant-backend.service` → `/etc/systemd/system/`
  - [ ] `deploy/ai-quant-frontend.service` → `/etc/systemd/system/`
- [ ] `systemctl daemon-reload && systemctl enable ai-quant-backend ai-quant-frontend`

### 2.6 前端

- [ ] `next build` 成功
- [ ] `NEXT_PUBLIC_API_URL` 指向生产后端地址（`https://api.yourdomain.com`）
- [ ] `NEXT_PUBLIC_WS_URL` 指向生产 WebSocket（`wss://api.yourdomain.com/ws/ticker`）
- [ ] HTTPS 已配置（Nginx/Caddy 反代 + Let's Encrypt）
- [ ] 首屏加载 < 3s（Lighthouse 验证）

---

## 三、上线流程（按顺序执行）

### 3.1 部署后端

```bash
# 1. 拉代码
cd /opt/ai-quant && git pull

# 2. 安装依赖（建议用 venv）
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. 检查 .env
cat .env | grep -E "EXCHANGE_TESTNET|MAX_ORDER|JWT_SECRET|DEBUG"
# 期望输出：
# EXCHANGE_TESTNET=false
# MAX_ORDER_AMOUNT_USDT=200.0
# JWT_SECRET_KEY=<32+ 字符>
# DEBUG=false

# 4. 初始化 DB（首次）
python -m db.init_db

# 5. 启动
systemctl start ai-quant-backend
systemctl status ai-quant-backend  # 应为 active (running)

# 6. 验证
curl http://127.0.0.1:8000/api/health
# 期望：{"status":"ok","exchange":"okx","testnet":false,"kill_switch":"ARMED"}

curl http://127.0.0.1:8000/api/health/deep
# 期望：exchange.ok=true, exchange.testnet=false, kill_switch=ARMED
```

### 3.2 部署前端

```bash
cd /opt/ai-quant/frontend
npm ci && npm run build
systemctl start ai-quant-frontend
systemctl status ai-quant-frontend
```

### 3.3 首次实盘验证（极小额）

```bash
# 1. 在前端注册账号、登录

# 2. 用前端"紧急停止"按钮，先确认能正常触发+解除

# 3. 用 limit-order 挂一张远低于市价的单：
#    symbol=BTC/USDT, side=buy, amount=0.001, price=10000
#    （amount_usdt=10，远低于 200 上限）
#    勾选 "confirm_live"

# 4. 确认订单出现在 OKX 官网 → 订单管理

# 5. 撤单，确认撤销成功

# 6. 查看 /api/health/deep，确认 strategies.running=0、kill_switch=ARMED
```

---

## 四、上线后监控

### 4.1 实时监控指标

| 指标 | 阈值 | 检查方法 |
|---|---|---|
| 后端进程存活 | 必须运行 | `systemctl status ai-quant-backend` |
| 健康检查 | `status=ok` | `curl /api/health` 每 1min |
| 深度健康 | `exchange.ok=true` | `curl /api/health/deep` 每 5min |
| DB 延迟 | < 100ms | `/api/health/deep` → `checks.database.latency_ms` |
| 交易所延迟 | < 2000ms | `/api/health/deep` → `checks.exchange.latency_ms` |
| kill_switch | ARMED | `/api/trading/kill-switch`（TRIGGERED = 立即人工介入）|
| 日亏损 | < 5% | `MAX_DAILY_LOSS_PCT` |
| 日志错误数 | < 10/min | `tail -f logs/app.log` |

### 4.2 日志位置

```
backend/logs/app.log       # 主日志（RotatingFileHandler, 10MB×30）
backend/logs/error.log     # 错误日志
journalctl -u ai-quant-backend   # systemd 日志
```

### 4.3 告警建议

- `kill_switch` 状态变 TRIGGERED → 立即 Telegram/邮件通知
- `/api/health/deep` 返回 `status != ok` → 通知
- 日亏损 ≥ 4% → 预警；≥ 5% → 自动触发紧急停止
- 后端进程挂掉 → systemd 自动重启（`Restart=always`）

---

## 五、紧急回滚流程

### 5.1 一键紧急停止（最重要）

**触发方式（任选其一）：**

1. **前端**：点击右上角红色"紧急停止"按钮 → 二次确认
2. **API**：
   ```bash
   curl -X POST http://127.0.0.1:8000/api/trading/emergency-stop \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"reason":"manual","confirm":true}'
   ```
3. **直接改文件**（最后手段，API 不可用时）：
   ```bash
   echo '{"status":"TRIGGERED","triggered_at":"...","triggered_by":"manual","reason":"emergency"}' \
     > backend/data/kill_switch.json
   # 后端下次检查会读到 TRIGGERED 状态
   ```

**触发后系统会：**
- ✅ 撤销所有挂单
- ✅ 市价平掉所有持仓
- ✅ 停止所有运行中策略
- ✅ 阻止后续所有下单请求
- ✅ 持久化状态到 `data/kill_switch.json`（重启不丢失）

### 5.2 解除紧急停止

```bash
curl -X POST http://127.0.0.1:8000/api/trading/emergency-reset \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"confirm":true}'
```

⚠️ **解除前必须**：
1. 查明触发原因（看 `kill_switch.json` 的 `reason` 字段）
2. 修复根因
3. 确认账户余额、持仓正常
4. 人工复核后才能解除

### 5.3 回滚到模拟盘

```bash
# 1. 编辑 .env
sed -i 's/EXCHANGE_TESTNET=false/EXCHANGE_TESTNET=true/' backend/.env

# 2. 重启后端
systemctl restart ai-quant-backend

# 3. 验证
curl http://127.0.0.1:8000/api/health | grep testnet
# 期望：testnet=true
```

### 5.4 完全停服

```bash
systemctl stop ai-quant-backend ai-quant-frontend
# 后端停止后，所有策略停止，WS 断开，前端无法交易
# 但 OKX 上的挂单/持仓不会被自动撤销 — 需手动到 OKX 处理
```

---

## 六、日常运维 Checklist

### 每日

- [ ] 查看 `/api/health/deep`，确认所有 check ok
- [ ] 查看 `kill_switch` 状态为 ARMED
- [ ] 查看当日交易记录、PnL
- [ ] 查看日志有无 ERROR/WARNING

### 每周

- [ ] 备份数据库（`backend/scripts/backup.sh`）
- [ ] 检查磁盘空间（日志/数据目录）
- [ ] 复核策略池表现（`/api/strategies/pool/summary`）
- [ ] 检查 OKX API Key 是否被禁用/过期

### 每月

- [ ] 回顾月度 PnL、最大回撤
- [ ] 评估是否需要调整风控参数（`MAX_ORDER_AMOUNT_USDT` 等）
- [ ] 更新依赖（`pip list --outdated`、`npm outdated`）
- [ ] 检查 systemd 日志有无崩溃记录

---

## 七、故障注入测试（建议每月一次）

| 故障场景 | 预期行为 | 测试方法 |
|---|---|---|
| 断网（OKX 不可达）| WS 重连、API 报错、策略暂停 | `iptables -A OUTPUT -d okx.com -j DROP` |
| DB 重启 | 连接池重连、`pool_pre_ping` 生效 | `systemctl restart postgresql` |
| 交易所限流 | API 返回 429、日志 WARNING | 短时间高频请求 |
| 进程崩溃 | systemd 自动重启、状态恢复 | `kill -9 <pid>` |
| kill_switch 触发 | 所有交易冻结 | 前端点紧急停止 |
| 磁盘满 | 日志写入失败但不崩溃 | `dd if=/dev/zero of=/tmp/fill` |

---

## 八、已知限制与注意事项

1. **OKX 模拟盘与实盘差异**：
   - 模拟盘深度薄，大单可能滑点严重
   - 模拟盘不限流，实盘有 IP/账户级限流
   - 模拟盘订单成交快，实盘可能部分成交

2. **风控引擎市场状态**：
   - `RANGING_LOW_VOL` 状态下 CUSTOM 策略被禁（手动下单也会被拒）
   - 这是预期行为，保护用户不在低波动震荡市入场
   - 如需强制下单，需调整 `/api/analysis/risk-policies`

3. **API Key 提币权限警告**：
   - 若 Key 有提币权限，后端启动会 WARNING
   - 强烈建议立即撤销该 Key 重新创建

4. **密码 hash 方案**：
   - v0.2.0 起改用 bcrypt 原生 API + SHA-256 pre-hash
   - 旧用户（passlib hash）登录会失败，需重新注册
   - 这是安全升级，不可逆

5. **WS 连接**：
   - 单 OKX WS 连接 → 多客户端广播（TickerFanOut）
   - 无客户端时停止上游节省资源
   - 指数退避重连：[3, 6, 12, 24, 60]s

---

## 九、签字确认

实盘上线前，请逐项确认并签字：

- [ ] 代码与测试：__________（日期）
- [ ] API Key 安全：__________（日期）
- [ ] 配置文件：__________（日期）
- [ ] 数据库：__________（日期）
- [ ] 服务器与网络：__________（日期）
- [ ] 前端：__________（日期）
- [ ] 首次实盘验证：__________（日期）
- [ ] 监控告警：__________（日期）

**最终批准**：__________（负责人签字） __________（日期）

---

> 📞 **紧急联系**：OKX 客服 https://www.okx.com/support；系统管理员：__________
>
> 📖 **完整文档**：`项目全面评价报告.md`、`量化交易系统技术参考_AI参照版.md`
