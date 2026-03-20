"""与 gen_register_bundle.py 输出一致。"""

import hashlib

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from mindmemory_client.register_crypto import (
    encrypted_password_hex_from_private_key_openssh,
    key_fingerprint_from_public_key_ssh,
    k_seed_bytes_from_private_key_openssh,
)


def _bundle_like_gen_script():
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
    parts = ssh_public_key.strip().split()
    blob = __import__("base64").b64decode(parts[1].encode("ascii"))
    expected_fp = hashlib.sha256(blob).hexdigest()
    expected_ep = hashlib.sha256(ssh_private_key.encode("utf-8")).hexdigest()
    return ssh_private_key, ssh_public_key, expected_fp, expected_ep


def test_key_fingerprint_matches_reference():
    pem, pub, expected_fp, _ = _bundle_like_gen_script()
    assert key_fingerprint_from_public_key_ssh(pub) == expected_fp


def test_k_seed_and_encrypted_password_match_reference():
    pem, _, _, expected_ep = _bundle_like_gen_script()
    assert encrypted_password_hex_from_private_key_openssh(pem) == expected_ep
    assert k_seed_bytes_from_private_key_openssh(pem).hex() == expected_ep
