"""密钥加密/解密模块 — 基于 Fernet (AES-128-CBC + HMAC)"""
import os
import base64
from cryptography.fernet import Fernet


def _generate_key() -> bytes:
    """生成一个新的 Fernet 密钥（32 字节 urlsafe-base64）"""
    return Fernet.generate_key()


def _load_or_create_key() -> bytes:
    """从环境变量 ENCRYPTION_KEY 加载密钥，若无则自动生成并写回 .env"""
    key_str = os.getenv("ENCRYPTION_KEY", "")
    if key_str and len(key_str) >= 32:
        # 确保是标准的 44 字符 urlsafe-b64 格式
        try:
            b = key_str.encode() if isinstance(key_str, str) else key_str
            return base64.urlsafe_b64encode(base64.urlsafe_b64decode(b))
        except Exception:
            pass

    # 自动生成
    new_key = _generate_key()
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    _persist_key(env_path, new_key.decode())
    os.environ["ENCRYPTION_KEY"] = new_key.decode()
    print(f"[crypto] Generated new encryption key, saved to .env")
    return new_key


def _persist_key(env_path: str, key: str):
    """将 ENCRYPTION_KEY 写入 .env 文件"""
    lines = []
    found = False
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        pass

    for i, line in enumerate(lines):
        if line.startswith("ENCRYPTION_KEY=") or line.startswith("# ENCRYPTION_KEY="):
            lines[i] = f"ENCRYPTION_KEY={key}\n"
            found = True
            break

    if not found:
        lines.append(f"\n# Auto-generated encryption key\nENCRYPTION_KEY={key}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


# 模块级单例
_fernet: Fernet | None = None


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt(plaintext: str) -> str:
    """加密字符串，返回 base64 编码的密文"""
    if not plaintext:
        return ""
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """解密字符串，返回明文。若密文为空或解密失败，返回空字符串"""
    if not ciphertext:
        return ""
    try:
        return get_fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        return ""


def mask_sensitive(value: str, keep_chars: int = 4) -> str:
    """脱敏：保留前 N 位，其余替换为 ***"""
    if not value:
        return ""
    if len(value) <= keep_chars:
        return "***"
    return value[:keep_chars] + "***"
