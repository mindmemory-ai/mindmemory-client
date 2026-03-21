from mindmemory_client.keygen import generate_ed25519_openssh_keypair
from mindmemory_client.private_key_backup import (
    decrypt_private_key_backup_openssh,
    encrypt_private_key_backup_openssh,
)


def test_backup_roundtrip():
    pem, _pub = generate_ed25519_openssh_keypair()
    blob = encrypt_private_key_backup_openssh(pem, "correct-horse-battery-staple-99")
    out = decrypt_private_key_backup_openssh(blob, "correct-horse-battery-staple-99")
    assert out == pem
