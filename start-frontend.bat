@echo off
chcp 65001 >nul 2>&1
title AI Quant Trade - Frontend

echo ========================================
echo   AI Quant Trade - Frontend Starting...
echo ========================================

cd /d D:\wenjian\xiangm\work\ai_quant_trade\frontend

REM 检查 node
where npx >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 22+
    pause
    exit /b 1
)

REM 检查 node_modules
if not exist "node_modules" (
    echo [WARN] node_modules not found. Installing...
    npm install --legacy-peer-deps
)

REM 检查 .next 构建产物
if not exist ".next" (
    echo [WARN] Build not found. Building...
    npm run build
)

echo [INFO] Starting frontend on http://localhost:3000
echo.

npx next start -p 3000

if errorlevel 1 (
    echo.
    echo [ERROR] Frontend exited with error.
    pause
)
