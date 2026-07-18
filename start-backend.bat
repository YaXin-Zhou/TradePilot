@echo off
set HTTPS_PROXY=http://127.0.0.1:7890
set HTTP_PROXY=http://127.0.0.1:7890
cd /d D:\wenjian\xiangm\work\ai_quant_trade\backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
