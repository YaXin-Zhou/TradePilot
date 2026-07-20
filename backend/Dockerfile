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

# 健康检查（v1.1: 127.0.0.1 避免 IPv6 解析问题）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

# 启动 — v1.1: 添加 timeout-graceful-shutdown 确保 Docker stop 优雅退出
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--timeout-graceful-shutdown", "30"]
