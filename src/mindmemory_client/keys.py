"""加载 Ed25519 私钥（PEM / OpenSSH）；读取 PEM 文本供 K_seed 派生。"""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def read_openssh_private_key_pem(path: Path) -> str:
    """
    读取私钥文件全文（UTF-8），用于 `k_seed_bytes_from_private_key_openssh`。
    与 `gen_register_bundle` 中 `ssh_private_key` 字符串需逐字节一致（换行风格可能影响哈希，建议与生成脚本相同为 \\n）。
    """
    return path.read_text(encoding="utf-8")


def load_ed25519_private_key(path: Path) -> Ed25519PrivateKey:
    raw = path.read_bytes()
    if raw.startswith(b"-----BEGIN"):
        key = serialization.load_pem_private_key(raw, password=None, backend=default_backend())
    else:
        key = serialization.load_ssh_private_key(raw, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("私钥必须是 Ed25519")
    return key
