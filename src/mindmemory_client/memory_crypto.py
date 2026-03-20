"""记忆载荷 AES-256-GCM：nonce(12) ‖ ciphertext ‖ tag，整体 Base64。"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE = 12


def encrypt_memory_payload(plaintext: bytes, key_32: bytes, *, nonce: bytes | None = None) -> bytes:
    """
    返回二进制：`nonce(12) ‖ ciphertext_with_tag`。
    密钥为 K_seed（32 字节），与设计文档 §11 一致。
    """
    if len(key_32) != 32:
        raise ValueError("AES-256 密钥必须为 32 字节（K_seed）")
    n = nonce if nonce is not None else os.urandom(NONCE_SIZE)
    if len(n) != NONCE_SIZE:
        raise ValueError(f"nonce 必须为 {NONCE_SIZE} 字节")
    aes = AESGCM(key_32)
    ct = aes.encrypt(n, plaintext, None)
    return n + ct


def decrypt_memory_payload(blob: bytes, key_32: bytes) -> bytes:
    """解密 `encrypt_memory_payload` 的输出。"""
    if len(key_32) != 32:
        raise ValueError("AES-256 密钥必须为 32 字节（K_seed）")
    if len(blob) < NONCE_SIZE + 16:
        raise ValueError("密文过短")
    n, ct = blob[:NONCE_SIZE], blob[NONCE_SIZE:]
    aes = AESGCM(key_32)
    return aes.decrypt(n, ct, None)


def encrypt_memory_base64(plaintext: bytes, key_32: bytes) -> str:
    """`nonce‖ct‖tag` 再 Base64，便于 API / 文本字段（与 mmem 记忆文件结构约定一致）。"""
    return base64.b64encode(encrypt_memory_payload(plaintext, key_32)).decode("ascii")


def decrypt_memory_base64(b64: str, key_32: bytes) -> bytes:
    raw = base64.b64decode(b64)
    return decrypt_memory_payload(raw, key_32)
