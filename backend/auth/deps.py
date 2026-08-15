"""FastAPI 鉴权依赖 — v2.1 本地部署：禁用登录，所有端点免登录（默认本地管理员）

说明：用户确认本地部署使用，直接去掉登录功能。
所有 Depends(get_current_user) / Depends(require_admin) 现在都返回一个默认的本地管理员，
不再校验 JWT。保留函数签名，避免改动所有路由。
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from auth.utils import decode_token

# auto_error=False：无 token 也不返回 401
_security = HTTPBearer(auto_error=False)
_optional_security = HTTPBearer(auto_error=False)

# 本地部署默认用户（免登录，视作管理员）
_LOCAL_USER = {"id": "local", "username": "local", "is_admin": True}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    """v2.1: 免登录，直接返回默认本地管理员（不再校验 JWT）"""
    return dict(_LOCAL_USER)


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(_optional_security),
) -> dict | None:
    """v2.1: 免登录，返回默认本地管理员"""
    return dict(_LOCAL_USER)


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """v2.1: 免登录，默认即管理员"""
    return current_user
