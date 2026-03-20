"""加载 Ed25519 私钥（PEM / OpenSSH）。"""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def load_ed25519_private_key(path: Path) -> Ed25519PrivateKey:
    raw = path.read_bytes()
    if raw.startswith(b"-----BEGIN"):
        key = serialization.load_pem_private_key(raw, password=None, backend=default_backend())
    else:
        key = serialization.load_ssh_private_key(raw, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("私钥必须是 Ed25519")
    return key
