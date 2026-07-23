# AI Quant Trade — Backend Dockerfile v1.1
# Python 3.13 + 多 worker + 优雅关闭
FROM python:3.13-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 代码
COPY . .

# 数据目录
RUN mkdir -p /app/data /app/logs

# 端口
EXPOSE 8000

# 健康检查（v1.3: start_period 90s，单 worker + fcntl 文件锁避免多 worker Alembic 竞态）
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
    CMD python -c "from http.client import HTTPConnection; c=HTTPConnection('127.0.0.1',8000,timeout=5); c.request('GET','/api/health'); r=c.getresponse(); exit(0 if r.status==200 else 1)"

# 启动 — v1.4: 单 worker（FastAPI 异步足够，避免多 worker fork 导致交易所连接/logger/scheduler 状态不一致）
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "30"]
