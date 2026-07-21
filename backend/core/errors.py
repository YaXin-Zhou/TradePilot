"""全局错误处理中间件 — 统一错误格式 + 敏感信息脱敏 + trace_id"""
import uuid
import traceback
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from core.logger import log
from core.crypto import mask_sensitive


async def global_error_handler(request: Request, call_next):
    """FastAPI 中间件：统一捕获所有未处理异常"""
    trace_id = str(uuid.uuid4())[:8]

    try:
        response = await call_next(request)
        return response
    except HTTPException as http_exc:
        # FastAPI 自身的 HTTP 异常（401/404/429 等）— 不改格式
        log.warning(f"[{trace_id}] HTTP {http_exc.status_code}: {http_exc.detail} | {request.method} {request.url.path}")
        raise
    except Exception as exc:
        # 未预料的异常 — 统一格式化
        error_detail = str(exc)[:500]
        log.error(
            f"[{trace_id}] Unhandled exception | {request.method} {request.url.path} | {type(exc).__name__}: {error_detail}\n"
            f"{traceback.format_exc()}"
        )

        # 对用户返回脱敏后的通用错误（不暴露内部细节）
        safe_detail = mask_sensitive(error_detail)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"内部服务器错误: {safe_detail}"[:200],
                "trace_id": trace_id,
            },
        )


async def sanitize_exception_handler(request: Request, exc: Exception):
    """备用异常处理器 — 兜底捕获"""
    trace_id = str(uuid.uuid4())[:8]
    log.critical(f"[{trace_id}] Uncaught exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "内部服务器错误", "trace_id": trace_id},
    )
