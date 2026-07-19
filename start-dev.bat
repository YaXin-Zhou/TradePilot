@echo off
chcp 65001 >nul 2>&1
title AI Quant Trade - Dev Mode

echo ========================================
echo   AI Quant Trade - Dev Mode (热重载)
echo   Backend: http://localhost:8000
echo   Frontend: http://localhost:3000
echo ========================================
echo.

cd /d D:\wenjian\xiangm\work\ai_quant_trade

REM 启动后端（新窗口）
start "AI Quant Backend" cmd /c "start-backend.bat"

REM 等待 2 秒
timeout /t 2 /nobreak >nul

REM 启动前端（当前窗口，dev 模式热重载）
cd /d D:\wenjian\xiangm\work\ai_quant_trade\frontend
echo [INFO] Starting frontend in dev mode...
set NEXT_PUBLIC_API_URL=http://localhost:8000
set NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/ticker
npx next dev -p 3000
