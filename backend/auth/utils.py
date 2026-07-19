"""JWT token and password utility functions.

密码哈希方案:
  - 直接使用 bcrypt 原生 API（不再依赖 passlib，避免 passlib 与新版 bcrypt 的兼容性问题）
  - SHA-256 pre-hash 绕过 bcrypt 72 字节密码长度限制（支持中文/长密码）
  - 输出格式与 passlib 兼容（$2b$...），便于将来切换回 passlib 或第三方校验
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from config import settings


# ----------------------------------------------------------------------
# 密码哈希
# ----------------------------------------------------------------------

def _prehash(password: str) -> bytes:
    """SHA-256 预哈希，绕过 bcrypt 72 字节限制。

    bcrypt 算法本身限制密码 ≤ 72 字节。中文密码 UTF-8 编码后很容易超
    （24 个中文字符就 72 字节）。先用 SHA-256 摘要为 32 字节定长，再
    喂给 bcrypt，即可支持任意长度密码。

    注意：此 pre-hash 不会降低安全性 —— SHA-256 抗碰撞，攻击者若想
    暴力破解，仍需对原密码空间进行枚举。
    """
    return hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    """对密码做 bcrypt 哈希。返回 $2b$... 字符串。"""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(_prehash(password), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码。返回 True/False。异常时返回 False（避免异常泄露信息）。"""
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # bcrypt 在 hash 格式非法、salt 无效、类型错误时抛 ValueError/TypeError。
        # 不同 bcrypt 版本异常类名有差异（4.x 有 BcryptError，5.0 仅 ValueError），
        # 统一捕获避免 AttributeError。
        return False


# ----------------------------------------------------------------------
# JWT
# ----------------------------------------------------------------------

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        raise
