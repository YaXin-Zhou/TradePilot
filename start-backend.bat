@echo off
cd /d D:\wenjian\xiangm\work\ai_quant_trade\backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
