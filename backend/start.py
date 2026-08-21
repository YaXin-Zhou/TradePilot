import uvicorn
import sys
sys.path.insert(0, r'D:\wenjian\xiangm\work\ai_quant_trade\backend')
from main import app
uvicorn.run(app, host='0.0.0.0', port=8090)
