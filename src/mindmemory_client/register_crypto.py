"""与 `mindmemory/tools/gen_register_bundle.py` 一致的注册字段与 K_seed 派生。"""

from __future__ import annotations

import base64
import hashlib


def key_fingerprint_from_public_key_ssh(ssh_public_key: str) -> str:
    """
    对 OpenSSH 公钥行中 base64 解码后的公钥 blob 做 SHA-256，返回 64 位小写 hex。
    与 `gen_register_bundle._ssh_pubkey_blob_sha256_hex` 一致。
    """
    parts = ssh_public_key.strip().split()
    if len(parts) < 2:
        raise ValueError("public_key 格式不符合 OpenSSH：缺少 base64 key blob")
    blob_b64 = parts[1]
    blob = base64.b64decode(blob_b64.encode("ascii"))
    return hashlib.sha256(blob).hexdigest()


def k_seed_bytes_from_private_key_openssh(ssh_private_key_pem: str) -> bytes:
    """
    K_seed = SHA256(OpenSSH 私钥 PEM 的 UTF-8 字节)，32 字节。
    用作 AES-256-GCM 密钥（全用户各 Agent 统一，见设计文档 §11）。
    """
    return hashlib.sha256(ssh_private_key_pem.encode("utf-8")).digest()


def encrypted_password_hex_from_private_key_openssh(ssh_private_key_pem: str) -> str:
    """
    `users.encrypted_password` 字段值：hex(SHA256(privkey PEM))，与 gen_register_bundle 一致。
    """
    return hashlib.sha256(ssh_private_key_pem.encode("utf-8")).hexdigest()
