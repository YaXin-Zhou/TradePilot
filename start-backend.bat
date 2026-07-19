@echo off
chcp 65001 >nul 2>&1
title AI Quant Trade - Backend

echo ========================================
echo   AI Quant Trade - Backend Starting...
echo ========================================

REM 设置代理（连 OKX 需要）
set HTTPS_PROXY=http://127.0.0.1:7890
set HTTP_PROXY=http://127.0.0.1:7890

cd /d D:\wenjian\xiangm\work\ai_quant_trade\backend

REM 检查 Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.12+
    pause
    exit /b 1
)

REM 检查 .env
if not exist ".env" (
    echo [WARN] .env not found. Copying from .env.example...
    copy .env.example .env >nul
    echo [WARN] Please edit .env and fill in your API keys, then restart.
    pause
    exit /b 1
)

REM 检查依赖
python -c "import fastapi, ccxt, sqlalchemy" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Dependencies missing. Installing...
    pip install -r requirements.txt
)

echo [INFO] Starting backend on http://localhost:8000
echo [INFO] API docs: http://localhost:8000/docs
echo [INFO] Health check: http://localhost:8000/api/health
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000

if errorlevel 1 (
    echo.
    echo [ERROR] Backend exited with error. Check logs/backend/*.log
    pause
)
