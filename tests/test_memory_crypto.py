"""AES-GCM 记忆载荷往返。"""

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from mindmemory_client.memory_crypto import decrypt_memory_base64, encrypt_memory_base64
from mindmemory_client.register_crypto import k_seed_bytes_from_private_key_openssh


def test_roundtrip_base64():
    priv = ed25519.Ed25519PrivateKey.generate()
    pem = priv.private_bytes(
        Encoding.PEM,
        PrivateFormat.OpenSSH,
        NoEncryption(),
    ).decode("utf-8")
    key = k_seed_bytes_from_private_key_openssh(pem)
    plain = b'{"hello":"world"}'
    b64 = encrypt_memory_base64(plain, key)
    out = decrypt_memory_base64(b64, key)
    assert out == plain
