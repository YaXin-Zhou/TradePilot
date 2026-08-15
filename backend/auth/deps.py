"""FastAPI 鉴权依赖 — 支持免登录开关

- AUTH_DISABLED=true（默认，本地开发）：所有端点免登录，返回默认本地管理员
- AUTH_DISABLED=false（生产/公网）：JWT 校验 + RBAC（is_admin 管理员权限）
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from auth.utils import decode_token
from config import settings

_security = HTTPBearer(auto_error=not settings.AUTH_DISABLED)
_optional_security = HTTPBearer(auto_error=False)

# 本地部署默认用户（免登录，视作管理员）
_LOCAL_USER = {"id": "local", "username": "local", "is_admin": True}


def _payload_to_user(payload: dict) -> dict:
    return {
        "id": payload.get("sub"),
        "username": payload.get("name", ""),
        "is_admin": bool(payload.get("is_admin", False)),
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    """免登录模式返回默认管理员；否则校验 JWT。"""
    if settings.AUTH_DISABLED:
        return dict(_LOCAL_USER)
    token = credentials.credentials
    try:
        payload = decode_token(token)
        if payload.get("sub") is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return _payload_to_user(payload)


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(_optional_security),
) -> dict | None:
    """免登录模式返回默认管理员；否则可选 JWT（无 token 返回 None）。"""
    if settings.AUTH_DISABLED:
        return dict(_LOCAL_USER)
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("sub") is None:
            return None
    except JWTError:
        return None
    return _payload_to_user(payload)


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """免登录模式默认即管理员；否则校验 is_admin。"""
    if settings.AUTH_DISABLED:
        return current_user
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin privilege required")
    return current_user
