"""生成 Ed25519 OpenSSH 密钥对（与 ``tools/gen_register_bundle.py`` 默认算法一致）。"""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def generate_ed25519_openssh_keypair() -> tuple[str, str]:
    """
    返回 ``(private_key_openssh_pem, public_key_openssh_line)``。
    私钥为 PEM/OpenSSH 文本，无口令保护。
    """
    priv = ed25519.Ed25519PrivateKey.generate()
    ssh_private_key = priv.private_bytes(
        Encoding.PEM,
        PrivateFormat.OpenSSH,
        NoEncryption(),
    ).decode("utf-8")
    ssh_public_key = priv.public_key().public_bytes(
        Encoding.OpenSSH,
        PublicFormat.OpenSSH,
    ).decode("utf-8")
    return ssh_private_key, ssh_public_key
