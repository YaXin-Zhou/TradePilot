"""统一日志系统 — RotatingFileHandler + 控制台输出 + 敏感信息自动脱敏"""
import logging
import logging.handlers
import os
import re
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 敏感信息脱敏正则
_SENSITIVE_PATTERNS = [
    (re.compile(r"(api_key|secret|passphrase|password|token|key)\s*[:=]\s*['\"]?([^'\"&\s,}]+)['\"]?", re.IGNORECASE), r"\1=***"),
    (re.compile(r"(Bearer\s+)([A-Za-z0-9\-_.]+)"), r"\1***"),
    (re.compile(r"sk-[A-Za-z0-9]+"), "sk-***"),
]


class SensitiveFilter(logging.Filter):
    """日志过滤器：自动脱敏敏感字段"""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in _SENSITIVE_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        if record.args and isinstance(record.args, dict):
            record.args = {k: "***" if any(s in k.lower() for s in ("secret", "password", "token", "key")) else v
                           for k, v in record.args.items()}
        return True


def setup_logger(name: str = "ai_quant") -> logging.Logger:
    """创建并配置 logger 实例

    FIX: uvicorn --workers 4 使用 fork() 创建子进程，子进程继承父进程的文件句柄
    但句柄可能失效。解决方案：每次调用都清除旧 handler 重新创建，确保文件句柄有效。
    """
    logger = logging.getLogger(name)

    # 清除可能从父进程继承的失效 handler（uvicorn multi-worker fix）
    for h in list(logger.handlers):
        try:
            h.close()
        except Exception:
            pass
        logger.removeHandler(h)

    logger.setLevel(logging.INFO)
    logger.propagate = False  # 不向 root logger 传播，避免 uvicorn 重复输出

    # 文件 Handler — 按大小+日期双轮转，单文件最大 10MB，保留 30 个
    file_handler = logging.handlers.RotatingFileHandler(
        filename=LOG_DIR / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    file_handler.addFilter(SensitiveFilter())

    # 错误日志 — 单独文件
    error_handler = logging.handlers.RotatingFileHandler(
        filename=LOG_DIR / "error.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=10,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    error_handler.addFilter(SensitiveFilter())

    # 控制台 Handler — 开发环境
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(levelname)-7s | %(name)s | %(message)s"
    ))
    console_handler.addFilter(SensitiveFilter())

    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)

    return logger


# 模块级 logger 实例
log = setup_logger()
