@echo off
cd /d D:\wenjian\xiangm\work\ai_quant_trade\frontend
echo Cleaning .next cache...
rmdir /s /q .next 2>nul
echo Building frontend...
call npx next build
echo Starting frontend...
npx next start -p 3000
echo Done.

