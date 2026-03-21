"""
与 ``mindmemory/mmem/private_key_backup.py`` 一致的私钥备份格式（Fernet + PBKDF2）。
服务端仅存储 JSON 字符串，不解密。
"""

from __future__ import annotations

import base64
import json

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def encrypt_private_key_backup_openssh(private_key_openssh: str, passphrase: str) -> str:
    """将 OpenSSH 私钥 PEM 加密为可存储的 JSON 字符串。"""
    import os

    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
        backend=default_backend(),
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    f = Fernet(key)
    token = f.encrypt(private_key_openssh.encode("utf-8"))
    payload = {
        "v": 1,
        "alg": "fernet+pbkdf2-sha256",
        "iterations": 390_000,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "ciphertext_b64": base64.b64encode(token).decode("ascii"),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decrypt_private_key_backup_openssh(blob_json: str, passphrase: str) -> str:
    """解密私钥备份。"""
    payload = json.loads(blob_json)
    if payload.get("v") != 1:
        raise ValueError("不支持的备份版本")
    salt = base64.b64decode(payload["salt_b64"].encode("ascii"))
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=int(payload.get("iterations", 390_000)),
        backend=default_backend(),
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    f = Fernet(key)
    token = base64.b64decode(payload["ciphertext_b64"].encode("ascii"))
    return f.decrypt(token).decode("utf-8")
