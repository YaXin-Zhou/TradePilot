"""crypto 模块测试 — 加密/解密/脱敏"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.crypto import encrypt, decrypt, mask_sensitive


class TestEncryptDecrypt:
    """加密解密基本功能"""

    def test_roundtrip_normal(self):
        plain = "test_api_secret_12345"
        enc = encrypt(plain)
        assert enc != plain
        assert decrypt(enc) == plain

    def test_roundtrip_special_chars(self):
        plain = "aB3!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        enc = encrypt(plain)
        assert decrypt(enc) == plain

    def test_roundtrip_chinese(self):
        plain = "交易密码测试_123"
        enc = encrypt(plain)
        assert decrypt(enc) == plain

    def test_roundtrip_long_string(self):
        plain = "x" * 1000
        enc = encrypt(plain)
        assert decrypt(enc) == plain

    def test_encrypt_empty(self):
        assert encrypt("") == ""

    def test_decrypt_empty(self):
        assert decrypt("") == ""

    def test_decrypt_invalid(self):
        assert decrypt("not_valid_ciphertext!!") == ""

    def test_different_inputs_different_outputs(self):
        """相同明文多次加密应产生不同密文（Fernet 含随机 IV）"""
        enc1 = encrypt("secret")
        enc2 = encrypt("secret")
        assert enc1 != enc2  # 含时间戳+随机IV
        assert decrypt(enc1) == decrypt(enc2) == "secret"


class TestMaskSensitive:
    """敏感信息脱敏"""

    def test_mask_normal(self):
        assert mask_sensitive("abcdefghijk") == "abcd***"

    def test_mask_short(self):
        assert mask_sensitive("abc") == "***"

    def test_mask_empty(self):
        assert mask_sensitive("") == ""

    def test_mask_exact_4(self):
        assert mask_sensitive("abcd") == "***"
