"""FastAPI dependencies for JWT authentication"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from auth.utils import decode_token

_security = HTTPBearer()
_optional_security = HTTPBearer(auto_error=False)


def _payload_to_user(payload: dict) -> dict:
    return {
        "id": payload.get("sub"),
        "username": payload.get("name", ""),
        "is_admin": bool(payload.get("is_admin", False)),
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    token = credentials.credentials
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return _payload_to_user(payload)


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(_optional_security),
) -> dict | None:
    """可选鉴权：无 token 返回 None（用于注册引导等场景）"""
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
    """管理员权限校验（v2.0: 交易/密钥管理/紧急停止等敏感操作仅管理员可用）"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin privilege required")
    return current_user
